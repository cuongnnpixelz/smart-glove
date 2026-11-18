"""Experimental causal GRU/CTC training from whole recordings and token lists."""
import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn.utils.rnn import pad_sequence
from SmartSignLanguage.sequence_model_5 import FLEX_COLUMNS, legacy

LABELS = ['<blank>', 'TOI', 'CAM_ON', 'BAN', 'KHOE', 'CHAO']
VAL = {'20261111T065341Z_0c930f2a'}
TEST = {'20261111T070400Z_a5d293b4', '20261105T090338Z_5c1463ca',
        '20261109T095855Z_f0b06c25'}


def features(rows, ref):
    keys = (*FLEX_COLUMNS, 'ACCx', 'ACCy', 'ACCz', 'GYRx', 'GYRy', 'GYRz', *legacy.BODY_COLUMNS)
    x = np.asarray([[float(r[k]) for k in keys] for r in rows])
    t = np.asarray([float(r['timestamp']) for r in rows]) / 1000
    if len(t) < 4 or not np.isfinite(x).all() or np.any(np.diff(t) <= 0) or np.any(np.diff(t) > .021):
        raise ValueError('Invalid or interrupted recording')
    flex = np.array([np.median(x[max(0,i-4):i+1,:5], axis=0) for i in range(len(x))])
    for i, k in enumerate(FLEX_COLUMNS):
        c = ref['flex_calibration'][k]
        flex[:, i] = (flex[:, i]-c['open'])/(c['closed']-c['open'])
    velocity = np.zeros_like(flex)
    velocity[1:] = np.diff(flex, axis=0)/np.diff(t)[:,None]
    f = np.column_stack((flex, (x[:,5:8]-x[:,11:14])/ref['gravity'],
                         x[:,8:11]-ref['gyro_bias'], x[:,11:14], velocity))
    # Average successive 40 ms blocks, not normalized sentence duration.
    n = len(f)//4*4
    return f[:n].reshape(-1,4,19).mean(axis=1).astype('float32')


class Network(nn.Module):
    def __init__(self):
        super().__init__()
        self.gru = nn.GRU(19, 48, num_layers=2, dropout=.15, batch_first=True)
        self.head = nn.Linear(48, len(LABELS))

    def forward(self, x):
        return self.head(self.gru(x)[0]).log_softmax(-1)


def decode(ids):
    out, previous = [], None
    for i in ids:
        if i != previous and i != 0:
            out.append(LABELS[i])
        previous = i
    return out


def errors(expected, actual):
    # Return substitutions, deletions, insertions from minimum edit alignment.
    dp = [[(0,0,0)]*(len(actual)+1) for _ in range(len(expected)+1)]
    for i in range(1,len(expected)+1): dp[i][0] = (0,i,0)
    for j in range(1,len(actual)+1): dp[0][j] = (0,0,j)
    for i in range(1,len(expected)+1):
        for j in range(1,len(actual)+1):
            if expected[i-1] == actual[j-1]: dp[i][j] = dp[i-1][j-1]
            else:
                candidates = []
                for cell, axis in ((dp[i-1][j-1],0),(dp[i-1][j],1),(dp[i][j-1],2)):
                    v = list(cell); v[axis] += 1; candidates.append(tuple(v))
                dp[i][j] = min(candidates, key=sum)
    return dp[-1][-1]


def load(path):
    manifest = json.loads(path.read_text(encoding='utf-8'))
    wanted = {r['key']:r for r in manifest['trials']}
    grouped, refs = defaultdict(list), {}
    for source in manifest['sources']:
        p = Path(source['path']); rp = p.with_name('imu_reference.json')
        if hashlib.sha256(p.read_bytes()).hexdigest() != source['sha256'] or hashlib.sha256(rp.read_bytes()).hexdigest() != source['reference_sha256']:
            raise ValueError(f'Source changed: {p}')
        ref = json.loads(rp.read_text(encoding='utf-8'))
        with p.open(encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                key = row['session_id']+'/'+str(int(float(row['trial_id'])))
                if key in wanted:
                    grouped[key].append(row); refs[key] = ref
    if set(grouped) != set(wanted): raise ValueError('Missing trials')
    return [dict(meta, x=features(grouped[key], refs[key])) for key,meta in wanted.items()]


def evaluate(model, data):
    model.eval(); results = []
    with torch.no_grad():
        for r in data:
            pred = decode(model(r['tensor'][None])[0].argmax(-1).tolist())
            results.append({'key':r['key'], 'kind':r['kind'], 'expected':r['tokens'],
                            'predicted':pred, 'errors':errors(r['tokens'],pred)})
    totals = np.sum([r['errors'] for r in results],axis=0).tolist()
    words = sum(len(r['expected']) for r in results)
    return {'trials':len(results), 'exact':sum(r['expected']==r['predicted'] for r in results),
            'substitutions_deletions_insertions':totals, 'reference_words':words,
            'wer':sum(totals)/max(words,1), 'predictions':results}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=Path('.runtime/continuous_words/dataset_v1.json'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=100)
    args = p.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    torch.set_num_threads(2); torch.manual_seed(42); random.seed(42); np.random.seed(42)
    data = load(args.data)
    train = [r for r in data if r['session'] not in VAL|TEST]
    val = [r for r in data if r['session'] in VAL]
    test = [r for r in data if r['session'] in TEST]
    a = np.concatenate([r['x'] for r in train]); mean=a.mean(0); std=a.std(0).clip(.01)
    for r in data: r['tensor']=torch.tensor((r['x']-mean)/std)
    model=Network(); optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    lossfn=nn.CTCLoss(blank=0,zero_infinity=False)
    best=float('inf'); history=[]; args.output.mkdir(parents=True)
    print(f'Train={len(train)} validation={len(val)} test={len(test)}; disjoint sessions',flush=True)
    for epoch in range(1,args.epochs+1):
        random.shuffle(train); model.train(); losses=[]
        for start in range(0,len(train),24):
            batch=train[start:start+24]
            x=pad_sequence([r['tensor'] for r in batch],batch_first=True)
            target=torch.tensor([LABELS.index(w) for r in batch for w in r['tokens']],dtype=torch.long)
            loss=lossfn(model(x).transpose(0,1),target,
                        torch.tensor([len(r['tensor']) for r in batch]),
                        torch.tensor([len(r['tokens']) for r in batch]))
            if not torch.isfinite(loss): raise ValueError('Nonfinite CTC loss')
            optimizer.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),5); optimizer.step()
            losses.append(loss.item())
        score=evaluate(model,val); history.append({'epoch':epoch,'loss':float(np.mean(losses)),'validation_wer':score['wer']})
        if score['wer'] < best:
            best=score['wer']; best_epoch=epoch
            torch.save({'state_dict':model.state_dict(),'mean':mean.tolist(),'std':std.tolist(),
                        'labels':LABELS,'schema':'causal-gru-ctc-five-flex-v1'},args.output/'model.pt')
        if epoch%10==0: print(history[-1],flush=True)
    checkpoint=torch.load(args.output/'model.pt',weights_only=True); model.load_state_dict(checkpoint['state_dict'])
    report={'schema':checkpoint['schema'],'best_epoch':best_epoch,'train_trials':len(train),
            'validation_sessions':sorted(VAL),'test_sessions':sorted(TEST),
            'validation':evaluate(model,val),'test':evaluate(model,test),
            'train_diagnostic':evaluate(model,train),'history':history,
            'limitations':['Experimental, not validated live; no automatic sentence endpoint implemented.',
                          'Validation contains isolated words only; continuous test contains TOI KHOE and one NONE only.',
                          'Other continuous phrases have only one session; no independent test for them.',
                          'No test of unseen word combinations; no inference-time phrase whitelist.'],
            'dataset_sha256':hashlib.sha256(args.data.read_bytes()).hexdigest()}
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:{a:b for a,b in report[k].items() if a!='predictions'} for k in ['validation','test','train_diagnostic']},indent=2),flush=True)


if __name__=='__main__': main()

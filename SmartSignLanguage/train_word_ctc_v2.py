"""Controlled CTC experiment: mixed validation and real background context.

Existing test sessions have been inspected previously: report is diagnostic,
not a fresh blind estimate of deployment accuracy.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import numpy as np
import torch
from torch import nn
from torch.nn.utils.rnn import pad_sequence
from .train_word_ctc import load, Network, LABELS, VAL, TEST, evaluate


def split(data):
    train, validation, test = [], [], []
    groups = defaultdict(list)
    for r in data:
        if r['session'] in TEST: test.append(r)
        elif r['session'] in VAL: validation.append(r)
        else: groups[(r['session'],r['label'])].append(r)
    for (_,label), group in sorted(groups.items()):
        group.sort(key=lambda r:int(r['key'].split('/')[-1]))
        # Additional phrase validation is same-session, explicitly reported.
        if group[0]['kind']=='continuous' and label!='NONE':
            validation.extend(group[::5])
            train.extend(r for i,r in enumerate(group) if i%5)
        else: train.extend(group)
    return train, validation, test


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=Path('.runtime/continuous_words/dataset_v1.json'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=220)
    p.add_argument('--variant', choices=['robust-context','standard-short-context'],default='robust-context')
    args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    torch.set_num_threads(2);torch.manual_seed(123);random.seed(123);np.random.seed(123)
    data=load(args.data);train,val,test=split(data)
    values=np.concatenate([r['x'] for r in train])
    mean=np.median(values,axis=0).astype('float32')
    std=((np.percentile(values,90,axis=0)-np.percentile(values,10,axis=0))/2.563).clip(.03).astype('float32')
    if args.variant=='standard-short-context':
        mean=values.mean(axis=0);std=values.std(axis=0).clip(.01)
    for r in data:r['tensor']=torch.tensor((r['x']-mean)/std)
    # Real background features from TRAIN only. Synthetic concatenations are
    # boundary augmentation, not evidence of natural coarticulation accuracy.
    background=[r['tensor'] for r in train if not r['tokens']]
    model=Network();optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.0001)
    criterion=nn.CTCLoss(blank=0,reduction='none')
    best=float('inf');history=[];args.output.mkdir(parents=True)
    print(f'Train {len(train)}, validation {len(val)}, diagnostic test {len(test)}',flush=True)
    for epoch in range(1,args.epochs+1):
        model.train();random.shuffle(train);losses=[]
        for start in range(0,len(train),24):
            batch=train[start:start+24];inputs=[]
            for r in batch:
                x=r['tensor'].clone()
                if r['tokens']:
                    donor=random.choice(background)
                    context=5 if args.variant=='standard-short-context' else 20
                    before=random.randint(0,min(context,len(donor)))
                    after=random.randint(0,min(context,len(donor)))
                    x=torch.cat((donor[:before],x,donor[:after]))
                inputs.append(x)
            targets=torch.tensor([LABELS.index(w) for r in batch for w in r['tokens']],dtype=torch.long)
            lengths=torch.tensor([len(x) for x in inputs]); sizes=torch.tensor([len(r['tokens']) for r in batch])
            logp=model(pad_sequence(inputs,batch_first=True)).transpose(0,1)
            losses_per_item=criterion(logp,targets,lengths,sizes)
            # Average empty/background loss over its frames, preventing a long
            # NONE recording from dominating a short labeled sequence.
            divisor=torch.where(sizes>0,sizes,lengths).float()
            if args.variant=='standard-short-context':divisor=sizes.clamp(min=1).float()
            loss=(losses_per_item/divisor).mean()
            if not torch.isfinite(loss):raise ValueError('Nonfinite training loss')
            optimizer.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),5);optimizer.step()
            losses.append(loss.item())
        score=evaluate(model,val)
        item={'epoch':epoch,'loss':float(np.mean(losses)),'validation_wer':score['wer']}
        history.append(item)
        if score['wer']<best:
            best=score['wer'];best_epoch=epoch
            torch.save({'schema':'causal-gru-ctc-five-flex-v1','state_dict':model.state_dict(),
                        'labels':LABELS,'mean':mean.tolist(),'std':std.tolist()},args.output/'model.pt')
        if epoch%20==0:print(item,flush=True)
    checkpoint=torch.load(args.output/'model.pt',weights_only=True);model.load_state_dict(checkpoint['state_dict'])
    report={'variant':args.variant,'best_epoch':best_epoch,'train_keys':[r['key'] for r in train],
            'validation_keys':[r['key'] for r in val],'test_keys':[r['key'] for r in test],
            'validation':evaluate(model,val),'test':evaluate(model,test),'train_diagnostic':evaluate(model,train),
            'history':history,'dataset_sha256':hashlib.sha256(args.data.read_bytes()).hexdigest(),
            'limitations':['Previously inspected test sessions: diagnostic comparison, not fresh blind test.',
                          'Phrase validation is same-session trial holdout; word validation is separate session.',
                          'Rest context uses artificial concatenation of training background; not natural signing.',
                          'No proof of unseen combinations or live recognition. No test-based checkpoint selection.']}
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:{a:b for a,b in report[k].items() if a!='predictions'} for k in ['validation','test','train_diagnostic']},indent=2),flush=True)


if __name__=='__main__':main()

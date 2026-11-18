"""Evaluate sequence alignment before offering another glove recognizer."""
import argparse
import json
from pathlib import Path
import joblib
from .train_word_ctc import load, errors
from .train_word_ctc_v2 import split
from .sequence_hmm import WordHMM


def evaluate(model,records):
    results=[]
    for r in records:
        pred,times,_=model.decode(r['x'])
        results.append({'key':r['key'],'kind':r['kind'],'expected':r['tokens'],
                        'predicted':pred,'starts_ms':times,'errors':errors(r['tokens'],pred)})
    n=sum(len(r['expected']) for r in results)
    return {'exact':sum(r['expected']==r['predicted'] for r in results),'trials':len(results),
            'wer':sum(sum(r['errors']) for r in results)/max(n,1),'predictions':results}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    data=load(Path('.runtime/continuous_words/dataset_v1.json'));train,val,test=split(data)
    labels=sorted({w for r in train for w in r['tokens']})
    model=WordHMM(labels).fit(train)
    scores=[]
    for weight in [.5,1.,2.]:
        for penalty in [0.,2.,4.]:
            model.emission_weight=weight;model.entry_penalty=penalty
            report=evaluate(model,val)
            scores.append((report['wer'],weight,penalty))
    _,model.emission_weight,model.entry_penalty=min(scores)
    args.output.mkdir(parents=True)
    joblib.dump(model,args.output/'model.joblib')
    report={'method':'word-state HMM, transcript-constrained alignment, unrestricted word loop',
            'train_trials':len(train),'validation':evaluate(model,val),'test':evaluate(model,test),
            'training_diagnostic':evaluate(model,train),'validation_grid':scores,
            'train_keys':[r['key'] for r in train],'validation_keys':[r['key'] for r in val],
            'test_keys':[r['key'] for r in test],
            'limitations':['Previously inspected test sessions: diagnostic only.',
                          'Phrase validation shares sessions with training; isolated validation uses separate session.',
                          'No live validation; no phrase whitelist; no promise of unseen combinations.']}
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:{a:b for a,b in report[k].items() if a!='predictions'} for k in ['validation','test','training_diagnostic']},indent=2))


if __name__=='__main__':main()

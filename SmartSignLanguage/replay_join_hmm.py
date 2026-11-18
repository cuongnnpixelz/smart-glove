"""Replay a captured stream through online HMM; no unlabeled accuracy claims."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import joblib
from .predict_join_hmm import SensorFrames
from .sequence_hmm import OnlineWordHMM


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session',type=Path,required=True)
    p.add_argument('--model',type=Path,default=Path('SmartSignLanguage/models/word_hmm_u4_phrases_full_v1/model.joblib'))
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    model=joblib.load(args.model);decoder=OnlineWordHMM(model)
    ref=json.loads((args.session/'reference.json').read_text());builder=SensorFrames(ref)
    snapshot=(args.session/'stream.jsonl').read_bytes();events=[];errors=Counter();partial=0;start=None
    for line in snapshot.splitlines():
        try:item=json.loads(line)
        except ValueError:partial+=1;continue
        if item.get('event')=='manual_reset':builder.reset();decoder.reset()
        if 'row'not in item:continue
        row=item['row']
        if start is None:start=row['timestamp']
        try:
            frame=builder.push(row)
            if frame is None:continue
            event=decoder.push(frame,row['timestamp'])
            if event['words']:events.append({'seconds':(row['timestamp']-start)/1000,'words':event['words']})
        except ValueError as exc:
            errors[str(exc)]+=1;builder.reset();decoder.reset()
    result={'session':str(args.session),'snapshot_sha256':hashlib.sha256(snapshot).hexdigest(),
            'model_sha256':hashlib.sha256(args.model.read_bytes()).hexdigest(),
            'word_events':events,'error_counts':dict(errors),'partial_lines':partial,
            'accuracy':None,'note':'No time-aligned intended gestures; emitted words are NOT verified correct.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('events',len(events),'invalid rows/interruptions',sum(errors.values()))
    print(json.dumps(events[:25],indent=2))


if __name__=='__main__':main()

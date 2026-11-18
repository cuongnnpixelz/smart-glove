"""Replay captured glove streams; never infer accuracy without gesture labels."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import torch
from .predict_word_ctc import LiveCTC
from .ctc_utterance import UtteranceCTC, rest_profile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--logs',type=Path,default=Path('.runtime/ctc_live'))
    parser.add_argument('--model',type=Path,default=Path('SmartSignLanguage/models/word_ctc_u4_phrases_v1/model.pt'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); torch.set_num_threads(2)
    checkpoint=torch.load(args.model,map_location='cpu',weights_only=True)
    reports=[]
    for folder in sorted(args.logs.iterdir()):
        path=folder/'stream.jsonl'
        if not path.exists():continue
        snapshot=path.read_bytes()
        entries=[]; partial=0
        for line in snapshot.splitlines():
            try: entries.append(json.loads(line))
            except ValueError: partial+=1
        rows=[e['row'] for e in entries if 'row' in e]
        if len(rows)<100:continue
        ref=json.loads((folder/'reference.json').read_text())
        info=json.loads((folder/'model.json').read_text())
        item={'session':folder.name,'snapshot_sha256':hashlib.sha256(snapshot).hexdigest(),
              'rows':len(rows),'partial_lines':partial,'seconds':(rows[-1]['timestamp']-rows[0]['timestamp'])/1000,
              'ground_truth':None,'accuracy':None,
              'rest_source':'saved_profile' if 'rest_profile'in info else 'first_second_estimate_not_signer_verified'}
        try:rest=info.get('rest_profile') or rest_profile(rows[:100],ref)
        except ValueError as error:
            item['cannot_replay']=str(error);reports.append(item);continue
        loaded=LiveCTC(checkpoint,ref)
        detector=UtteranceCTC(loaded.model,loaded.mean,loaded.std,ref,rest)
        events=[]; old=[]
        for entry in entries:
            if entry.get('event')=='manual_reset':detector.reset()
            if 'row' not in entry:continue
            prediction=entry.get('prediction')
            if prediction and 'preview'in prediction:old.append(prediction['preview'])
            try:event=detector.push(entry['row'])
            except ValueError as error:event={'state':'ERROR','reason':str(error)}
            if event:events.append(event)
        item.update(events=events,counts=dict(Counter(e['state'] for e in events)),
                    old_preview_changes=sum(a!=b for a,b in zip(old,old[1:])),
                    unfinished_state=detector.state)
        reports.append(item)
    output={'model_sha256':hashlib.sha256(args.model.read_bytes()).hexdigest(),
            'note':'Replay measures behavior only. Missing sign/timing annotations prevent word accuracy claims.',
            'logs':reports}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2),encoding='utf-8')
    for r in reports:print(json.dumps({k:v for k,v in r.items() if k!='events'}))


if __name__=='__main__':main()

"""Compare greedy and beam decoding on fixed splits (diagnostic reused test)."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from .train_word_ctc import load, LABELS, TEST, VAL, errors, decode
from .predict_word_ctc import LiveCTC
from .ctc_decode import prefix_beam, alignment_peaks


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();torch.set_num_threads(2)
    checkpoint=torch.load(args.model/'model.pt',weights_only=True)
    loaded=LiveCTC(checkpoint,{})
    results=[]
    data=load(Path('.runtime/continuous_words/dataset_v1.json'))
    with torch.inference_mode():
        for r in data:
            if r['session'] not in VAL|TEST:continue
            x=torch.tensor((r['x']-loaded.mean)/loaded.std)[None]
            lp=loaded.model(x)[0].numpy()
            beam=prefix_beam(lp)
            greedy=decode(lp.argmax(-1).tolist());pred=[LABELS[i] for i in beam[0][0]]
            results.append({'key':r['key'],'kind':r['kind'],'split':'test' if r['session']in TEST else 'validation',
                            'expected':r['tokens'],'greedy':greedy,'beam':pred,
                            'peaks':alignment_peaks(lp,beam[0][0]),
                            'beam_margin':beam[0][1]-beam[1][1],
                            'greedy_errors':errors(r['tokens'],greedy),'beam_errors':errors(r['tokens'],pred)})
    summary={}
    for split in ['validation','test']:
        selected=[r for r in results if r['split']==split]
        for decoder in ['greedy','beam']:
            summary[split+'_'+decoder]={'exact':sum(r[decoder]==r['expected'] for r in selected),
                 'trials':len(selected),'wer':sum(sum(r[decoder+'_errors']) for r in selected)/sum(len(r['expected']) for r in selected)}
    args.output.write_text(json.dumps({'summary':summary,'predictions':results},indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()

"""CTC prefix beam search with no sentence whitelist or language-model bias."""
import math
import numpy as np


def logadd(a,b):
    if a == -math.inf:return b
    if b == -math.inf:return a
    hi,lo=max(a,b),min(a,b)
    return hi+math.log1p(math.exp(lo-hi))


def prefix_beam(log_probs, width=10):
    beams={(): (0.,-math.inf)}
    for frame in np.asarray(log_probs):
        nxt={}
        def add(prefix, axis, score):
            values=list(nxt.get(prefix,(-math.inf,-math.inf)))
            values[axis]=logadd(values[axis],score);nxt[prefix]=tuple(values)
        for prefix,(pb,pn) in beams.items():
            total=logadd(pb,pn)
            add(prefix,0,total+float(frame[0]))
            for label in range(1,len(frame)):
                value=float(frame[label])
                if prefix and prefix[-1]==label:
                    add(prefix,1,pn+value)
                    add(prefix+(label,),1,pb+value)
                else:add(prefix+(label,),1,total+value)
        beams=dict(sorted(nxt.items(),key=lambda kv:logadd(*kv[1]),reverse=True)[:width])
    return [(p,logadd(*v)) for p,v in sorted(beams.items(),key=lambda kv:logadd(*kv[1]),reverse=True)]


def alignment_peaks(log_probs, tokens):
    """Peak softmax scores on the best valid CTC alignment of selected tokens."""
    if not tokens:return []
    lp=np.asarray(log_probs);states=[0]
    for token in tokens:states.extend([token,0])
    scores=np.full(len(states),-np.inf);scores[0]=lp[0,0];scores[1]=lp[0,states[1]]
    back=np.zeros((len(lp),len(states)),dtype=int)
    for t in range(1,len(lp)):
        nxt=np.full(len(states),-np.inf)
        for s,label in enumerate(states):
            predecessors=[s]
            if s:predecessors.append(s-1)
            if s>1 and label and label!=states[s-2]:predecessors.append(s-2)
            best=max(predecessors,key=lambda v:scores[v])
            nxt[s]=scores[best]+lp[t,label];back[t,s]=best
        scores=nxt
    s=max([len(states)-1,len(states)-2],key=lambda v:scores[v])
    if not np.isfinite(scores[s]):return [0.]*len(tokens)
    peaks=[0.]*len(tokens)
    for t in range(len(lp)-1,-1,-1):
        if s%2:peaks[s//2]=max(peaks[s//2],float(np.exp(lp[t,states[s]])))
        s=back[t,s]
    return peaks

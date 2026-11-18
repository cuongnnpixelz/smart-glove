"""Experimental left-to-right word models with unrestricted word-loop decoding."""
import numpy as np


def viterbi(emissions, transitions, initial, finals):
    score=initial+emissions[0]
    back=np.zeros(emissions.shape,dtype=np.int32)
    for t in range(1,len(emissions)):
        candidates=score[:,None]+transitions
        back[t]=np.argmax(candidates,axis=0)
        score=candidates[back[t],np.arange(len(score))]+emissions[t]
    last=max(finals,key=lambda s:score[s])
    if not np.isfinite(score[last]):raise ValueError('No complete alignment')
    best=float(score[last]);path=[last]
    for t in range(len(emissions)-1,0,-1):path.append(int(back[t,path[-1]]))
    return np.array(path[::-1]),best


class WordHMM:
    def __init__(self, labels, states=5, feature_count=19):
        self.labels=list(labels);self.states=states
        self.feature_count=feature_count
        self.size=1+len(labels)*states
        self.emission_weight=1.;self.entry_penalty=0.

    def word_states(self,label):
        first=1+self.labels.index(label)*self.states
        return list(range(first,first+self.states))

    def emission(self,x):
        z=(x[:,:self.feature_count]-self.center)/self.scale
        delta=z[:,None,:]-self.means[None,:,:]
        # Diagonal Gaussian emissions. Normalized over feature count to keep
        # insertion/transition costs meaningful with correlated sensor channels.
        return -.5*np.mean(delta**2/self.variances+np.log(2*np.pi*self.variances),axis=2)*self.emission_weight

    def forced(self,x,tokens):
        sequence=[0]
        for token in tokens:sequence+=self.word_states(token)+[0]
        count=len(sequence);a=np.full((count,count),-np.inf)
        for i,state in enumerate(sequence):
            a[i,i]=np.log(.84)
            if i+1<count:a[i,i+1]=np.log(.16)
            if i+2<count and sequence[i+1]==0:a[i,i+2]=np.log(.08)
        initial=np.full(count,-np.inf);initial[0]=np.log(.5)
        if count>1:initial[1]=np.log(.5)
        finals=[count-1] if count==1 else [count-1,count-2]
        path,score=viterbi(self.emission(x)[:,sequence],a,initial,finals)
        return np.asarray(sequence)[path],score

    def fit(self,data,iterations=12):
        all_x=np.concatenate([r['x'][:,:self.feature_count] for r in data])
        self.center=all_x.mean(0);self.scale=all_x.std(0).clip(.03)
        buckets=[[] for _ in range(self.size)]
        for r in data:
            z=(r['x'][:,:self.feature_count]-self.center)/self.scale
            if not r['tokens']:buckets[0].extend(z)
            elif r['kind']=='isolated':
                # Only initialization of isolated-word latent states. Phrase
                # boundaries are always learned with transcript-constrained DP.
                for state,part in zip(self.word_states(r['tokens'][0]),np.array_split(z,self.states)):
                    buckets[state].extend(part)
        if any(not b for b in buckets):raise ValueError('Missing isolated words or background for initialization')
        self.means=np.array([np.mean(b,axis=0) for b in buckets])
        self.variances=np.array([np.var(b,axis=0).clip(.05) for b in buckets])
        for _ in range(iterations):
            buckets=[[] for _ in range(self.size)]
            for r in data:
                path,_=self.forced(r['x'],r['tokens'])
                z=(r['x'][:,:self.feature_count]-self.center)/self.scale
                for state in np.unique(path):buckets[state].extend(z[path==state])
            for state,bucket in enumerate(buckets):
                if len(bucket)>=3:
                    self.means[state]=np.mean(bucket,axis=0)
                    self.variances[state]=np.var(bucket,axis=0).clip(.05)
        return self

    def graph(self):
        a=np.full((self.size,self.size),-np.inf)
        initial=np.full(self.size,-np.inf);initial[0]=np.log(.5)
        a[0,0]=np.log(.9);finals=[0]
        starts=[self.word_states(label)[0] for label in self.labels]
        for label in self.labels:
            states=self.word_states(label);finals.append(states[-1])
            initial[states[0]]=np.log(.5/len(self.labels))-self.entry_penalty
            a[0,states[0]]=np.log(.1/len(self.labels))-self.entry_penalty
            for state in states:
                a[state,state]=np.log(.84)
                if state!=states[-1]:a[state,state+1]=np.log(.16)
            a[states[-1],0]=np.log(.08)
            for start in starts:a[states[-1],start]=np.log(.08/len(starts))-self.entry_penalty
        return a,initial,finals,starts

    def decode(self,x):
        a,initial,finals,starts=self.graph()
        path,score=viterbi(self.emission(x),a,initial,finals)
        words=[];segments=[];previous=0
        for t,state in enumerate(path):
            if state in starts and (t==0 or state!=previous):
                words.append(self.labels[(state-1)//self.states]);segments.append(t*40)
            previous=state
        return words,segments,score


class OnlineWordHMM:
    """Commit only a common completed-word prefix across all surviving states.

    No label blacklist, fixed sentence list, or per-word rest gate. States carry
    temporal progress. Repeated labels require another complete state traversal.
    """
    def __init__(self,model,fallback_commit_ms=None):
        self.model=model
        self.fallback_commit_ms=fallback_commit_ms
        self.transitions,self.initial,self.finals,self.starts=model.graph()
        self.reset()

    def reset(self):
        self.scores=None
        self.paths=[[] for _ in range(self.model.size)]
        self.last_stamp=None
        self.pending_candidate=None

    def push(self,feature,timestamp):
        if self.last_stamp is not None and not 0 < timestamp-self.last_stamp <=80:
            self.reset();raise ValueError('Interrupted feature stream')
        self.last_stamp=timestamp
        emission=self.model.emission(np.asarray(feature)[None])[0]
        if self.scores is None:
            self.scores=self.initial+emission
        else:
            candidates=self.scores[:,None]+self.transitions
            predecessors=np.argmax(candidates,axis=0)
            next_scores=candidates[predecessors,np.arange(self.model.size)]+emission
            paths=[]
            for state,previous in enumerate(predecessors):
                path=list(self.paths[previous])
                if np.isfinite(next_scores[state]) and state in self.finals[1:] and previous!=state:
                    path.append((self.model.labels[(state-1)//self.model.states],timestamp))
                paths.append(path)
            self.paths=paths;self.scores=next_scores
        self.scores-=np.max(self.scores)
        active_states=np.flatnonzero(np.isfinite(self.scores))
        active=[self.paths[i] for i in active_states]
        common=[]
        for items in zip(*active):
            if len({item[0] for item in items})!=1:break
            common.append((items[0][0],max(item[1] for item in items)))
        forced_commit=False
        if common:
            self.paths=[path[len(common):] for path in self.paths]
            self.pending_candidate=None
        elif self.fallback_commit_ms is not None:
            best_state=int(np.argmax(self.scores))
            best_path=self.paths[best_state]
            if best_path:
                candidate=best_path[0]
                if candidate!=self.pending_candidate:
                    self.pending_candidate=candidate
                if timestamp-candidate[1]>=self.fallback_commit_ms:
                    common=[candidate]
                    for state,path in enumerate(self.paths):
                        if path and path[0][0]==candidate[0]:
                            self.paths[state]=path[1:]
                        else:
                            self.scores[state]=-np.inf
                            self.paths[state]=[]
                    self.pending_candidate=None
                    forced_commit=True
            else:
                self.pending_candidate=None
        # Don't silently commit an arbitrary branch if ambiguity grows.
        if max(map(len,self.paths))>40:
            self.reset();raise ValueError('Too many unresolved words; discarded ambiguous segment')
        return {'words':[word for word,_ in common],
                'word_times':[stamp for _,stamp in common],
                'forced_commit':forced_commit,
                'background_best':int(np.argmax(self.scores))==0,
                'pending':any(self.paths),
                'pending_best':bool(self.paths[int(np.argmax(self.scores))])}

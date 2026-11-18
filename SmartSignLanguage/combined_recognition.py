"""Conservative experimental arbitration; no cross-model confidence comparison."""
from copy import deepcopy
from collections import Counter

if __package__:
    from .sequence_model_5 import SequenceModel
else:
    from sequence_model_5 import SequenceModel


class CombinedModel:
    def __init__(self, phrase, models):
        paths=[p.parent for p in models.glob('sequence_5_100hz_*/manifest.json')
               if (p.parent/'model.joblib').exists()]
        if not paths:
            raise ValueError('Chua co model tu/chu 5 ngon')
        folder=max(paths,key=lambda p:(p/'manifest.json').stat().st_mtime_ns)
        self.word=SequenceModel(folder)
        self.phrase=phrase
        self.durations=sorted(set(phrase.durations+[5.0]))
        self.manifest={'labels':sorted(set(phrase.manifest['labels']+self.word.manifest['labels']))}
        print(f'MODEL TU/CHU: {folder}',flush=True)
        print('THU NGHIEM: giu tu/chu tu sau khi dua tay len den het luot. '
              'Cau: lam tron cau nhu luc thu. Xung dot hai model se KHONG chon bua.',flush=True)

    def predict_episode(self, rows, reference):
        phrases={self.phrase.predict(rows[:round(s*100)],reference)
                 for s in self.phrase.durations}-{'NONE'}
        physical=deepcopy(reference)
        physical.update(trial_seconds=1.5,sample_count=150)
        # Only real contiguous 1.5-second windows, after the initial raising motion.
        windows=[rows[start:start+150] for start in (50,150,250)]
        votes=Counter(self.word.predict(w,physical) for w in windows)
        words={label for label,n in votes.items() if label!='NONE' and n>=2}
        candidates=phrases|words
        if len(candidates)==1:
            return {'state':'RESULT','label':next(iter(candidates))}
        if not candidates:
            return {'state':'NONE'}
        return {'state':'WAIT','reason':'CHUA PHAN BIET RO | CAU: '+
                ', '.join(sorted(phrases))+' | TU/CHU: '+', '.join(sorted(words))+
                '. Nghi tay roi thu lai; khong xuat ket qua.'}

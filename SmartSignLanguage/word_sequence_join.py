"""Conservative joining of timestamped word predictions, independent of vocabulary.

Overlapping windows are correlated: duration is a debounce rule, not confidence
or proof that a complete sign was performed. A stable misclassification can pass.
"""


class StableWordSequence:
    def __init__(self, labels, stable_ms=1000, none_ms=1500):
        self.labels = set(labels)
        if 'NONE' not in self.labels:
            raise ValueError('Can model co NONE de tach luot va lap lai cung tu')
        self.stable_ms, self.none_ms = stable_ms, none_ms
        self.reset()

    def reset(self):
        self.words = []
        self.candidate = self.since = self.last_stamp = self.last_word = None
        self.count = 0

    def update(self, label, timestamp):
        if label not in self.labels:
            raise ValueError('Nhan ngoai model')
        if self.last_stamp is not None and not 0 < timestamp-self.last_stamp <= 500:
            self.reset()
            raise ValueError('Du doan bi gian doan; khong ghep qua khoang mat du lieu')
        self.last_stamp = timestamp
        if label != self.candidate:
            self.candidate, self.since, self.count = label, timestamp, 1
            return {'state':'PENDING','candidate':label}
        self.count += 1
        duration = timestamp-self.since
        if label == 'NONE':
            if duration >= self.none_ms and self.words:
                words = list(self.words)
                self.words.clear()
                self.last_word = None
                return {'state':'FINAL','words':words}
            return None
        if duration < self.stable_ms or self.count < 5 or label == self.last_word:
            return None
        self.words.append(label)
        self.last_word = label
        return {'state':'WORD','label':label,'words':list(self.words),
                'stable_ms':duration,'observations':self.count}

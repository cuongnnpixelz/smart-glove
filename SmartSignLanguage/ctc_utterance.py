"""Fixed-origin gesture turns. Rest ends a turn, never separates its words.

Motion/pose thresholds are experimental physical gates, not recognition accuracy.
CTC blank is deliberately not used as a rest detector.
"""
from collections import deque
import numpy as np
import torch
from .train_word_ctc import features, LABELS
from .sequence_model_5 import FLEX_COLUMNS, legacy
from .ctc_decode import prefix_beam, alignment_peaks


def pose(row, reference):
    flex = []
    for key in FLEX_COLUMNS:
        c = reference['flex_calibration'][key]
        flex.append((row[key]-c['open'])/(c['closed']-c['open']))
    body = np.array([row[k] for k in legacy.BODY_COLUMNS])
    gravity = (np.array([row[k] for k in ('ACCx','ACCy','ACCz')])-body)/reference['gravity']
    gyro = np.array([row[k] for k in ('GYRx','GYRy','GYRz')])-reference['gyro_bias']
    return np.array(flex), gravity, float(np.linalg.norm(gyro)), float(np.linalg.norm(body))


def rest_profile(rows, reference):
    raw = np.array([[r[k] for k in FLEX_COLUMNS] for r in rows])
    if not np.isfinite(raw).all() or np.any(raw <= 8) or np.any(raw >= 4087):
        raise ValueError('Flex loi/bao hoa khi lay tu the nghi')
    values = [pose(r, reference) for r in rows]
    if len(values) < 50:
        raise ValueError('Can it nhat 0.5 giay tu the nghi')
    if np.percentile([v[2] for v in values],95) > .25:
        raise ValueError('Tay con chuyen dong khi lay tu the nghi')
    flex = np.stack([v[0] for v in values])
    if not np.isfinite(np.concatenate([np.r_[v[0],v[1],v[2],v[3]] for v in values])).all():
        raise ValueError('Du lieu khong huu han khi lay tu the nghi')
    # Match the calibration's P90 noise measure instead of max-min: one
    # transient ADC sample must not invalidate an otherwise quiet pose.
    spread = np.percentile(flex,95,axis=0)-np.percentile(flex,5,axis=0)
    quarter = max(1,len(flex)//4)
    drift = np.abs(np.median(flex[-quarter:],axis=0)-np.median(flex[:quarter],axis=0))
    for i,key in enumerate(FLEX_COLUMNS):
        if spread[i] > .4 or drift[i] > .20:
            raise ValueError(f'{key} chua on dinh: dao dong P90 {spread[i]:.2f}, troi {drift[i]:.2f}; cho flex hoi on dinh')
    return {'flex':np.median(flex,axis=0).tolist(),
            'gravity':np.median([v[1] for v in values],axis=0).tolist(),
            'flex_noise_p90':spread.tolist(),'flex_drift':drift.tolist()}


def token_peaks(log_probs):
    """Decode CTC with peak scores; scores are NOT calibrated confidence."""
    probabilities = log_probs.exp().cpu().numpy()
    ids = probabilities.argmax(axis=1)
    tokens, peaks = [], []
    previous = 0
    for i, label in enumerate(ids):
        if label:
            score = float(probabilities[i,label])
            if label != previous:
                tokens.append(LABELS[label]); peaks.append(score)
            else:
                peaks[-1] = max(peaks[-1],score)
        previous = label
    return tokens, peaks


class UtteranceCTC:
    def __init__(self, model, mean, std, reference, rest, min_token_score=.70):
        self.model, self.mean, self.std = model, mean, std
        self.reference, self.rest = reference, rest
        self.min_token_score = min_token_score
        self.reset()

    def reset(self):
        self.preroll = deque(maxlen=20)
        self.rows = []
        self.state = 'REST'
        self.last_stamp = self.onset_since = self.rest_since = None
        self.onset_rows = []

    def decode(self, rows):
        x = torch.tensor((features(rows,self.reference)-self.mean)/self.std)[None]
        with torch.inference_mode():
            log_probs=self.model(x)[0].cpu().numpy()
        best=prefix_beam(log_probs,width=10)[0][0]
        tokens=[LABELS[i] for i in best]
        scores=alignment_peaks(log_probs,best)
        return tokens, scores

    def push(self, row):
        stamp = float(row['timestamp'])
        if self.last_stamp is not None and not 0 < stamp-self.last_stamp <= 21:
            self.reset()
            raise ValueError('Gian doan du lieu: huy luot, khong ghep qua khoang mat mau')
        self.last_stamp = stamp
        raw = np.array([row[k] for k in FLEX_COLUMNS])
        f,g,gyro,acc = pose(row,self.reference)
        if not np.isfinite(np.r_[stamp,raw,f,g,gyro,acc]).all() or np.any(raw<=8) or np.any(raw>=4087):
            self.reset()
            raise ValueError('Du lieu cam bien khong hop le; huy luot')
        flex_distance = float(np.max(np.abs(f-np.array(self.rest['flex']))))
        gravity_distance = float(np.linalg.norm(g-np.array(self.rest['gravity'])))
        at_rest = flex_distance < .25 and gravity_distance < .20 and gyro < .25 and acc < 1.2
        # Hysteresis: start must be distinct from incidental light motion.
        active = flex_distance > .40 or gravity_distance > .30 or gyro > .65 or acc > 2.5
        if self.state == 'REST':
            if active:
                if self.onset_since is None:
                    self.onset_since = stamp
                    self.onset_rows = list(self.preroll)
                self.onset_rows.append(row)
                if stamp-self.onset_since >= 120:
                    self.rows = self.onset_rows
                    self.state = 'ACTIVE'
                    self.rest_since = None
                    return {'state':'START','timestamp':stamp}
            else:
                self.onset_since = None
                self.onset_rows = []
            self.preroll.append(row)
            return None
        if self.state == 'WAIT_REST':
            if at_rest:
                if self.rest_since is None: self.rest_since = stamp
                if stamp-self.rest_since >= 1000:
                    self.reset()
                    return {'state':'READY','timestamp':stamp}
            else:
                self.rest_since = None
            return None
        self.rows.append(row)
        if at_rest:
            if self.rest_since is None: self.rest_since = stamp
        else:
            self.rest_since = None
        if self.rest_since is not None and stamp-self.rest_since >= 1000:
            # Keep 200 ms of trailing rest, not the full endpoint wait.
            captured = [r for r in self.rows if r['timestamp'] <= self.rest_since+200]
            tokens, scores = self.decode(captured)
            accepted = bool(tokens) and min(scores) >= self.min_token_score
            event = {'state':'RESULT' if accepted else 'UNCERTAIN','timestamp':stamp,
                     'start':captured[0]['timestamp'],'end':captured[-1]['timestamp'],
                     'tokens':tokens if accepted else [], 'candidate':tokens,
                     'peak_scores':scores, 'reason':None if accepted else 'blank_or_weak_token'}
            self.reset()
            return event
        if stamp-self.rows[0]['timestamp'] > 8000:
            self.rows = []
            self.state = 'WAIT_REST'
            self.rest_since = None
            return {'state':'UNCERTAIN','timestamp':stamp,'tokens':[], 'candidate':[],
                    'reason':'turn_over_8_seconds','peak_scores':[]}
        return None

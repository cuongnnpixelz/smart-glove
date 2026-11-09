"""Motion-triggered complete 5s windows with preroll and release/rearm checks.

No time warping, padding, or overlapping predictions. Thresholds are demo
segmentation rules and need validation with continuous hardware recordings.
"""
from collections import deque
import numpy as np

if __package__:
    from .sensor_pipeline import Q_COLUMNS, multiply, SamplingGap
    from .sequence_guard import rotation_vectors
else:
    from sensor_pipeline import Q_COLUMNS, multiply, SamplingGap
    from sequence_guard import rotation_vectors


def flex(rows):
    return np.asarray([[r["flex_1"], r["flex_2"]] for r in rows], dtype=float)


def rotations(rows):
    q = np.asarray([[r[k] for k in Q_COLUMNS] for r in rows])
    inverse = q[0]*[1,-1,-1,-1]
    return rotation_vectors([multiply(inverse, item) for item in q])


class ContinuousSegmenter:
    def __init__(self, reference, predict):
        self.reference, self.predict = reference, predict
        self.history = deque()
        self.phase = "REST"
        self.last_stamp = None
        self.origin = None
        self.baseline = None
        self.noise = np.zeros(2)
        self.trigger_stamp = None
        self.window = None
        self.previous = None
        self.finished_at = None

    def quiet(self, rows, duration=600):
        if len(rows) < 2 or rows[-1]["timestamp"]-rows[0]["timestamp"] < duration:
            return False
        gyr = np.asarray([[r[k] for k in ("GYRx","GYRy","GYRz")] for r in rows])
        gyr -= np.asarray(self.reference["gyro_bias"])
        return (np.percentile(np.linalg.norm(gyr,axis=1),90) < .22 and
                np.max(np.percentile(flex(rows),95,axis=0)-np.percentile(flex(rows),5,axis=0)) < 20)

    def tail(self, duration):
        rows = list(self.history)
        cutoff = rows[-1]["timestamp"]-duration
        # Keep one sample at/before the boundary for timestamp-based duration.
        start = max(0, next((i for i,r in enumerate(rows) if r["timestamp"] >= cutoff),len(rows)-1)-1)
        return rows[start:]

    def completed(self, rows, label=None):
        f = flex(rows)
        baseline = np.median(f[:13],axis=0)
        delta = baseline-f  # Wiring measured on this glove: bend decreases ADC.
        bend = np.percentile(delta,95,axis=0)
        released = bend-np.median(delta[-13:],axis=0)
        active = {"TRO_TRAI_DUOI": [1], "GIUA_TRAI_DUOI": [0], "TRO_PHAI_DUOI": [1]}.get(label)
        eligible = (bend >= 15) & (released >= 5)
        has_release = np.all(eligible[active]) if active is not None else np.any(eligible)
        if not has_release:
            return False, "Chua thay ngon can gap va hoi; chi nghieng khong du"
        rotation = rotations(rows)
        angle = np.linalg.norm(rotation,axis=1)
        if angle.max() < np.deg2rad(15):
            return False, "Chua thay nghieng co tay"
        if np.median(angle[-13:]) > max(np.deg2rad(12), .3*angle.max()):
            return False, "Co tay chua ve giua"
        if not self.quiet(rows[-17:]):
            return False, "Chuoi chua ket thuc/on dinh trong cua so 5 giay"
        return True, "Da co gap/hoi va co tay ve giua"

    def can_rearm(self, recent):
        if not self.quiet(recent, 800):
            return False
        if self.previous is None:
            return True
        # Wait for wrist return AND measurable release, never an exact ADC reset.
        f = flex(self.previous)
        base = np.median(f[:13],axis=0)
        peak_bend = np.percentile(base-f,95,axis=0)
        involved = peak_bend >= 15
        if np.any(involved):
            now_bend = base-np.median(flex(recent),axis=0)
            if np.any((peak_bend-now_bend)[involved] < np.maximum(5,.2*peak_bend[involved])):
                return False
        rotation = rotations([self.previous[0], *recent])
        return np.median(np.linalg.norm(rotation[-13:],axis=1)) < np.deg2rad(15)

    def push(self, row):
        stamp = row["timestamp"]
        if self.last_stamp is not None:
            gap = stamp-self.last_stamp
            if gap <= 0:
                raise ValueError("Timestamp reset")
            if gap > 120:
                raise SamplingGap(gap)
        self.last_stamp = stamp
        self.history.append(row)
        while self.history and stamp-self.history[0]["timestamp"] > 1200:
            self.history.popleft()
        if self.phase == "REST":
            if (self.finished_at is None or stamp-self.finished_at >= 1500) and self.can_rearm(self.tail(800)):
                self.baseline = np.median(flex(self.tail(800)),axis=0)
                self.noise = np.percentile(flex(self.tail(800)),95,axis=0)-np.percentile(flex(self.tail(800)),5,axis=0)
                self.phase = "READY"
                self.trigger_stamp = None
                return {"state":"READY"}
            return None
        if self.phase == "READY":
            f = np.array([row["flex_1"],row["flex_2"]])
            gyr = np.array([row[k] for k in ("GYRx","GYRy","GYRz")])-self.reference["gyro_bias"]
            moving = np.any(np.abs(f-self.baseline) > np.maximum(10,3*self.noise)) or np.linalg.norm(gyr) > .3
            if moving:
                if self.trigger_stamp is None:
                    self.trigger_stamp = stamp
                if stamp-self.trigger_stamp >= 80:
                    start = self.trigger_stamp-600
                    self.window = [r for r in self.history if r["timestamp"] >= start]
                    if self.window[0]["timestamp"] > self.trigger_stamp-500:
                        self.phase = "REST"
                        return {"state":"REST"}
                    self.phase = "TRACKING"
                    return {"state":"TRACKING"}
            else:
                self.trigger_stamp = None
                if self.quiet(self.tail(800),800):
                    # Slow offset drift at rest is allowed; do not require old ADC.
                    self.baseline = np.median(flex(self.tail(800)),axis=0)
            return None
        self.window.append(row)
        if stamp-self.window[0]["timestamp"] < 5000:
            return None
        batch = self.window
        self.previous = batch
        self.window = None
        self.finished_at = stamp
        self.phase = "REST"
        ok, reason = self.completed(batch)
        label, candidate = "NONE", "NONE"
        if ok:
            label,candidate,reason = self.predict(batch,self.reference)
            if label != "NONE":
                ok, completion_reason = self.completed(batch,label)
                if not ok:
                    label,reason = "NONE",completion_reason
        return {"state":"RESULT", "label":label, "candidate":candidate, "reason":reason}

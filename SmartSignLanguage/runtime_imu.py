"""Runtime-only short-gap recovery. Collection continues using strict ImuProcessor.

Never integrate gyro over missing time. Retain calibrated gyro bias/gravity,
discard orientation, and reseed from a new stationary segment on the same TCP
connection. Recovery rows must never be classified or saved as training trials.
"""
from collections import deque
import numpy as np

if __package__:
    from .sensor_pipeline import ImuProcessor, RAW_COLUMNS, MAX_GAP_MS, SamplingGap, timing_report
else:
    from sensor_pipeline import ImuProcessor, RAW_COLUMNS, MAX_GAP_MS, SamplingGap, timing_report


SHORT_GAP_LIMIT_MS = 500
SETTLE_MS = 800


class RuntimeImuProcessor:
    def __init__(self, processor):
        self.processor = processor
        self.calibration = processor.calibration
        self.last_stamp = processor.last_stamp
        self.pending = None

    @property
    def ready(self):
        return self.pending is None and self.processor.ready

    def process(self, stamp, raw):
        if not isinstance(stamp, (int, np.integer)) or not 0 <= stamp <= 0xFFFFFFFF:
            raise ValueError("Invalid device timestamp")
        values = np.asarray([raw[k] for k in RAW_COLUMNS], dtype=float)
        if not np.isfinite(values).all() or np.any(values[:2] < 0) or np.any(values[:2] > 4095):
            raise ValueError("Invalid raw sensor value")
        gap = 0 if self.last_stamp is None else stamp-self.last_stamp
        if self.last_stamp is not None and gap <= 0:
            raise ValueError("Sensor clock reset/wrapped; restart runtime")
        if gap > SHORT_GAP_LIMIT_MS:
            raise SamplingGap(gap)
        self.last_stamp = stamp
        if gap > MAX_GAP_MS:
            self.processor.reset()
            self.pending = deque()
        if self.pending is None:
            return self.processor.process(stamp, raw)

        row = {"timestamp": stamp, **dict(zip(RAW_COLUMNS, values.tolist()))}
        self.pending.append(row)
        # Keep one sample at/before the 800ms boundary.
        while len(self.pending) > 1 and stamp-self.pending[1]["timestamp"] >= SETTLE_MS:
            self.pending.popleft()
        if gap > MAX_GAP_MS:
            # Emit an explicit break so the runtime invalidates its old window.
            return {**row, "_runtime_recovering": True, "_runtime_gap_ms": gap}
        if self._stationary():
            # Same calibrated bias/gravity, new local orientation. No old sample
            # participates, and no integration step spans the gap.
            seed = [self.processor.process(r["timestamp"],r) for r in self.pending]
            self.pending = None
            return {**seed[-1], "_runtime_seed": seed}
        return {**row, "_runtime_recovering": True}

    def _stationary(self):
        rows = list(self.pending)
        if rows[-1]["timestamp"]-rows[0]["timestamp"] < SETTLE_MS:
            return False
        try:
            timing_report(rows)
        except ValueError:
            return False
        values = np.asarray([[r[k] for k in RAW_COLUMNS] for r in rows])
        acc = values[:,2:5]
        gyro = values[:,5:8]-np.asarray(self.calibration["gyro_bias"])
        magnitude = np.linalg.norm(acc,axis=1)
        gravity = self.calibration["gravity"]
        return (np.all((magnitude > .9*gravity) & (magnitude < 1.1*gravity)) and
                np.max(np.std(acc,axis=0)) <= .3 and
                np.max(np.std(gyro,axis=0)) <= .03 and
                np.percentile(np.linalg.norm(gyro,axis=1),90) < .22 and
                np.max(np.percentile(values[:,:2],95,axis=0)-np.percentile(values[:,:2],5,axis=0)) < 20)

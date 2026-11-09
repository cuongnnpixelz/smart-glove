"""Versioned, shared collection/inference math. Raw flex ADC is never overwritten.

Quaternion: Hamilton [w,x,y,z], body -> local world, world +Z along the
stationary accelerometer reference. Heading is relative, NOT magnetic north.
The IMU filter is a proportional gravity-corrected complementary filter,
not the DMP used by the reference paper. Acceleration remains in m/s^2.
"""
import json
from pathlib import Path
import numpy as np

SCHEMA = "glove-v2"
PROCESSOR = "gravity-complementary-v1"
SAMPLE_MS = 40
WINDOW_SIZE = 50
WINDOW_MS = (WINDOW_SIZE - 1) * SAMPLE_MS
MAX_GAP_MS = 120
RAW_COLUMNS = ("flex_1", "flex_2", "ACCx", "ACCy", "ACCz", "GYRx", "GYRy", "GYRz")
Q_COLUMNS = ("Qw", "Qx", "Qy", "Qz")
BODY_COLUMNS = ("ACCx_body", "ACCy_body", "ACCz_body")
WORLD_COLUMNS = ("ACCx_world", "ACCy_world", "ACCz_world")
CSV_COLUMNS = ("timestamp", "user_id", "session_id", "trial_id", "label",
               "flex_1", "flex_2", *Q_COLUMNS, "GYRx", "GYRy", "GYRz",
               "ACCx", "ACCy", "ACCz", *BODY_COLUMNS, *WORLD_COLUMNS)
# Absolute yaw/world acceleration are saved for analysis, but excluded from
# this first model because the six-axis IMU has no absolute heading reference.
MODEL_FEATURES = ("flex_1_norm", "flex_2_norm", "GYRx", "GYRy", "GYRz",
                  "ACCx", "ACCy", "ACCz", *BODY_COLUMNS)
LABELS = ("XIN_CHAO", "CAM_ON_NHIEU", "NONE")


class SamplingGap(ValueError):
    """A forward sensor-time gap invalidates the current IMU reference/window."""
    def __init__(self, gap_ms):
        self.gap_ms = int(gap_ms)
        super().__init__(f"Du lieu ESP32 bi gian doan {self.gap_ms} ms "
                         f"(gioi han {MAX_GAP_MS} ms); can khoi tao lai MPU")


def from_legacy(features):
    """Adapter only: legacy derivatives are not model inputs or v2 CSV columns."""
    return dict(zip(RAW_COLUMNS, (*features[:2], *features[6:12])))


def validate_calibration(c):
    if c.get("schema") != SCHEMA or c.get("processor") != PROCESSOR or c.get("sample_ms") != SAMPLE_MS:
        raise ValueError("Calibration/schema/rate incompatible; run collect_v2.py --calibrate-only")
    for key in ("flex_1", "flex_2"):
        endpoints = np.asarray([c[key]["open"], c[key]["closed"]], dtype=float)
        if not np.isfinite(endpoints).all() or np.any(endpoints < 0) or np.any(endpoints > 4095) or abs(np.diff(endpoints)[0]) < 50:
            raise ValueError(f"{key}: invalid endpoints or span < 50 ADC; check glove")
    validate_imu_reference(c)
    if c.get("flex1_finger") not in ("Index", "Middle"):
        raise ValueError("Missing physical flex1 finger mapping")
    return c


def validate_imu_reference(c):
    bias = np.asarray(c["gyro_bias"], dtype=float)
    if bias.shape != (3,) or not np.isfinite(bias).all() or np.linalg.norm(bias) > .25:
        raise ValueError("Invalid stationary gyroscope bias")
    if not np.isfinite(c["gravity"]) or not 8 < c["gravity"] < 11:
        raise ValueError("Invalid stationary acceleration reference")
    return c


def load_calibration(path):
    return validate_calibration(json.loads(Path(path).read_text(encoding="utf-8")))


def timing_report(rows, sample_ms=SAMPLE_MS, max_gap_ms=MAX_GAP_MS):
    t = np.array([r["timestamp"] for r in rows], dtype=float)
    if len(t) < 2 or not np.isfinite(t).all() or np.any(t < 0) or np.any(t != np.floor(t)):
        raise ValueError("At least two valid millisecond timestamps are required")
    dt = np.diff(t)
    if np.any(dt <= 0):
        raise ValueError("Duplicate/backward timestamp; do not sort or merge across a reset")
    hz = 1000 / dt.mean()
    report = {"samples": len(t), "duration_ms": float(t[-1]-t[0]),
              "hz": float(hz), "min_gap_ms": float(dt.min()), "max_gap_ms": float(dt.max())}
    target_hz = 1000 / sample_ms
    tolerance = .05 if sample_ms == 10 else .12
    if dt.max() > max_gap_ms or not target_hz*(1-tolerance) <= hz <= target_hz*(1+tolerance):
        raise ValueError(f"Bad sampling: {hz:.2f} Hz, max gap {dt.max():.0f} ms; expected {target_hz:g} Hz, gap <= {max_gap_ms} ms")
    return report


def make_calibration(open_rows, closed_rows, rest_rows, flex1_finger="Index"):
    for rows in (open_rows, closed_rows, rest_rows):
        if timing_report(rows)["duration_ms"] < 1600:
            raise ValueError("Calibration needs at least 1.6 seconds of stable samples per pose")
    c = {"schema": SCHEMA, "processor": PROCESSOR, "sample_ms": SAMPLE_MS,
         "flex1_finger": flex1_finger, "world_frame": "local +Z stationary acceleration, relative yaw",
         "units": {"timestamp": "ms since device boot", "flex": "12-bit ADC (3-read mean)",
                   "acceleration": "m/s^2", "gyroscope": "rad/s"}}
    for key in ("flex_1", "flex_2"):
        ends = []
        for rows in (open_rows, closed_rows):
            values = np.array([r[key] for r in rows])
            if np.percentile(values, 95) - np.percentile(values, 5) > 25:
                raise ValueError(f"{key} not stable; hold pose and repeat calibration")
            ends.append(float(np.median(values)))
        c[key] = dict(zip(("open", "closed"), ends))
    gyros = np.array([[r[k] for k in ("GYRx", "GYRy", "GYRz")] for r in rest_rows])
    acc = np.array([[r[k] for k in ("ACCx", "ACCy", "ACCz")] for r in rest_rows])
    if np.max(np.std(gyros, axis=0)) > .03 or np.max(np.std(acc, axis=0)) > .3:
        raise ValueError("IMU moved during stationary calibration; hold still")
    c["gyro_bias"] = np.median(gyros, axis=0).tolist()
    # Empirical stationary magnitude: does not claim a full six-face accel calibration.
    c["gravity"] = float(np.median(np.linalg.norm(acc, axis=1)))
    return validate_calibration(c)


def multiply(a, b):
    w,x,y,z = a; v,i,j,k = b
    return np.array([w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
                     w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v])


def rotate(q, vector):
    q = np.asarray(q, dtype=float)
    return multiply(multiply(q, [0, *vector]), q * [1,-1,-1,-1])[1:]


def make_imu_reference(rest_rows, sample_ms=SAMPLE_MS):
    """Stationary IMU reference only; no invented flex calibration endpoints."""
    if timing_report(rest_rows, sample_ms, 20 if sample_ms == 10 else MAX_GAP_MS)["duration_ms"] < 1600:
        raise ValueError("Giu yen MPU it nhat 1.6 giay")
    values = np.asarray([[r[k] for k in RAW_COLUMNS[2:]] for r in rest_rows], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("IMU reference contains nonfinite values")
    acc, gyros = values[:, :3], values[:, 3:]
    if np.max(np.std(gyros, axis=0)) > .03 or np.max(np.std(acc, axis=0)) > .3:
        raise ValueError("MPU dang chuyen dong. Giu yen tay khi lay moc dau phien.")
    return validate_imu_reference({
        "schema": "sequence-imu-v1", "processor": PROCESSOR, "sample_ms": sample_ms,
        "gyro_bias": np.median(gyros, axis=0).tolist(),
        "gravity": float(np.median(np.linalg.norm(acc, axis=1))),
        "flex_calibrated": False,
        "world_frame": "local +Z stationary acceleration, relative yaw",
        "quaternion": "Hamilton w,x,y,z; body to local world",
        "units": {"timestamp": "ms since device boot", "flex": "raw ADC",
                  "acceleration": "m/s^2", "gyroscope": "rad/s"},
    })


class ImuProcessor:
    def __init__(self, calibration):
        self.calibration = validate_imu_reference(calibration)
        self.reset()

    def reset(self):
        self.q = None
        self.last_stamp = None
        self.first_stamp = None

    def process(self, stamp, raw):
        values = np.array([raw[k] for k in RAW_COLUMNS], dtype=float)
        if not np.isfinite(values).all() or np.any(values[:2] < 0) or np.any(values[:2] > 4095):
            raise ValueError("Invalid raw sensor value")
        if not isinstance(stamp, (int, np.integer)) or not 0 <= stamp <= 0xFFFFFFFF:
            raise ValueError("Invalid device timestamp")
        a, gyro = values[2:5], values[5:8] - self.calibration["gyro_bias"]
        magnitude = np.linalg.norm(a)
        if self.last_stamp is not None:
            gap = stamp-self.last_stamp
            if gap <= 0:
                self.reset()
                raise ValueError("Sensor clock reset/wrapped; start a new session")
            if gap > MAX_GAP_MS:
                self.reset()
                raise SamplingGap(gap)
        if self.q is None:
            if not self.calibration["gravity"]*.8 < magnitude < self.calibration["gravity"]*1.2:
                raise ValueError("Hold still to initialize IMU orientation")
            roll = np.arctan2(a[1], a[2]); pitch = np.arctan2(-a[0], np.hypot(a[1],a[2]))
            cr,sr = np.cos(roll/2),np.sin(roll/2); cp,sp = np.cos(pitch/2),np.sin(pitch/2)
            self.q = np.array([cr*cp,sr*cp,cr*sp,-sr*sp])
            self.first_stamp = stamp
        else:
            dt = (stamp-self.last_stamp)/1000
            expected = rotate(self.q * [1,-1,-1,-1], [0,0,1])
            # Reject gravity corrections during large linear acceleration.
            if .8*self.calibration["gravity"] < magnitude < 1.2*self.calibration["gravity"]:
                gyro = gyro + 2.0*np.cross(a/magnitude, expected)
            self.q += .5*multiply(self.q, [0,*gyro])*dt
            self.q /= np.linalg.norm(self.q)
        self.last_stamp = stamp
        gravity_body = rotate(self.q * [1,-1,-1,-1], [0,0,self.calibration["gravity"]])
        body = a-gravity_body
        row = {"timestamp": stamp, **dict(zip(RAW_COLUMNS, values.tolist())),
               **dict(zip(Q_COLUMNS, self.q.tolist())), **dict(zip(BODY_COLUMNS, body.tolist())),
               **dict(zip(WORLD_COLUMNS, rotate(self.q, body).tolist()))}
        return row

    @property
    def ready(self):
        return self.first_stamp is not None and self.last_stamp-self.first_stamp >= 2000


class SensorProcessor(ImuProcessor):
    def __init__(self, calibration):
        super().__init__(validate_calibration(calibration))


def model_vector(row, calibration):
    normalized = {}
    for key in ("flex_1", "flex_2"):
        c = calibration[key]
        normalized[key+"_norm"] = float(np.clip((row[key]-c["open"])/(c["closed"]-c["open"]),0,1))
    # Gyroscope is saved raw; apply the same stationary bias offline and live.
    normalized.update({k: row[k]-calibration["gyro_bias"][i] for i,k in enumerate(("GYRx","GYRy","GYRz"))})
    return np.array([{**row, **normalized}[key] for key in MODEL_FEATURES], dtype=np.float32)


def make_window(rows, calibration, end=None):
    """Identical fixed-time interpolation offline and live; never warp a whole trial."""
    if not rows:
        return None
    end = rows[-1]["timestamp"] if end is None else end
    start = end-WINDOW_MS
    if rows[0]["timestamp"] > start or rows[-1]["timestamp"] < end:
        return None
    times = np.array([r["timestamp"] for r in rows])
    lo = max(0, int(np.searchsorted(times,start,side="right"))-1)
    hi = min(len(rows), int(np.searchsorted(times,end,side="left"))+1)
    selected = rows[lo:hi]
    timing_report(selected)
    x = np.array([model_vector(r,calibration) for r in selected])
    grid = start+np.arange(WINDOW_SIZE)*SAMPLE_MS
    return np.stack([np.interp(grid,times[lo:hi],x[:,i]) for i in range(x.shape[1])],axis=1).astype(np.float32)

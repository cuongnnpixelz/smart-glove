"""Whole three-second sequence features shared by training and prediction."""
import hashlib
import json
from pathlib import Path

import numpy as np

if __package__:
    from .sensor_pipeline import (PROCESSOR, Q_COLUMNS, BODY_COLUMNS, multiply,
                                  timing_report, validate_imu_reference)
else:
    from sensor_pipeline import (PROCESSOR, Q_COLUMNS, BODY_COLUMNS, multiply,
                                 timing_report, validate_imu_reference)

SCHEMA = "sequence-svm-v1"
SAMPLE_MS = 40
DURATION_MS = 3000
GRID = np.arange(0, DURATION_MS + 1, SAMPLE_MS)
FEATURES = ("flex_1_delta", "flex_2_delta", "relative_Qw", "relative_Qx",
            "relative_Qy", "relative_Qz", "GYRx_bias_corrected",
            "GYRy_bias_corrected", "GYRz_bias_corrected", *BODY_COLUMNS)


def sequence_vector(rows, reference, duration_ms=DURATION_MS, flex_columns=("flex_1", "flex_2")):
    """Fixed 40-ms grid, full 3 seconds; never stretch a short/incomplete trial."""
    validate_imu_reference(reference)
    if reference.get("processor") != PROCESSOR:
        raise ValueError("IMU processor version mismatch")
    quality = timing_report(rows)
    if not duration_ms <= quality["duration_ms"] <= duration_ms + 120:
        raise ValueError(f"Need one complete {duration_ms/1000:g}-second sequence")
    t = np.asarray([r["timestamp"] for r in rows], dtype=float)
    t -= t[0]
    n = len(flex_columns)
    columns = (*flex_columns, *Q_COLUMNS, "GYRx", "GYRy", "GYRz", *BODY_COLUMNS)
    x = np.asarray([[r[k] for k in columns] for r in rows], dtype=float)
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite sequence feature")
    if np.any(x[:, :n] < 0) or np.any(x[:, :n] > 4095):
        raise ValueError("Invalid flex ADC")
    q = x[:, n:n+4].copy()
    if np.any(np.abs(np.linalg.norm(q, axis=1)-1) > .001):
        raise ValueError("Invalid quaternion")
    # q and -q denote the same orientation; avoid interpolation through zero.
    for i in range(1, len(q)):
        if np.dot(q[i-1], q[i]) < 0:
            q[i] *= -1
    x[:, n:n+4] = q
    grid = np.arange(0, duration_ms + 1, SAMPLE_MS)
    y = np.stack([np.interp(grid, t, x[:, i]) for i in range(x.shape[1])], axis=1)
    # Remove the starting flex offset without inventing open/closed calibration.
    y[:, :n] -= np.median(y[:5, :n], axis=0)
    q = y[:, n:n+4]
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    origin_inverse = q[0] * [1, -1, -1, -1]
    y[:, n:n+4] = np.asarray([multiply(origin_inverse, qi) for qi in q])
    y[:, n+4:n+7] -= np.asarray(reference["gyro_bias"])
    return y.astype(np.float32).reshape(-1)


class SequenceModel:
    def __init__(self, folder):
        import joblib
        folder = Path(folder)
        self.manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        m = self.manifest
        if (m.get("schema"), m.get("processor"), m.get("sample_ms"), m.get("duration_ms")) != (
                SCHEMA, PROCESSOR, SAMPLE_MS, DURATION_MS) or m.get("features") != list(FEATURES):
            raise ValueError("Incompatible sequence model/preprocessing")
        model_path = folder / "model.joblib"
        if hashlib.sha256(model_path.read_bytes()).hexdigest() != m["model_sha256"]:
            raise ValueError("Model and manifest do not match")
        self.model = joblib.load(model_path)
        if self.model.n_features_in_ != len(GRID)*len(FEATURES) or list(self.model.classes_) != m["labels"]:
            raise ValueError("Model shape/labels mismatch")

    def predict(self, rows, reference):
        # SVM decision scores are not calibrated probabilities; return a label.
        return str(self.model.predict(sequence_vector(rows, reference)[None, :])[0])

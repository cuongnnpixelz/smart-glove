"""Calibrated static/dynamic five-finger gestures: 150 real samples at 100 Hz."""
import hashlib
import json
from pathlib import Path

import numpy as np

if __package__:
    from . import sequence_model as legacy
    from .five_finger import CSV_COLUMNS, FLEX_COLUMNS, FLEX_PINS, FINGERS, validate_mapping, validate_reference, trial_quality
else:
    import sequence_model as legacy
    from five_finger import CSV_COLUMNS, FLEX_COLUMNS, FLEX_PINS, FINGERS, validate_mapping, validate_reference, trial_quality

SCHEMA = "sequence-svm-five-flex-v2"
PROCESSOR = legacy.PROCESSOR
SAMPLE_MS = 10
DURATION_MS = 1500
DATA_DIRECTORY = "sequence_data_5_100hz"
MODEL_PREFIX = "sequence_5_100hz_"
GRID = np.arange(0, DURATION_MS, SAMPLE_MS)
FEATURES = (*(f"flex_{i}_norm" for i in range(1, 6)),
            "gravity_x_body", "gravity_y_body", "gravity_z_body",
            "GYRx_bias_corrected", "GYRy_bias_corrected", "GYRz_bias_corrected",
            *legacy.BODY_COLUMNS, *(f"dFlex_{i}_norm_per_s" for i in range(1, 6)))
PREPROCESSING = ("per-session open/closed flex normalization, no per-trial baseline subtraction; "
                 "5-sample median flex; body gravity direction preserves static tilt; "
                 "40ms centered flex slope; 150 steps at 100Hz")
quality_report = trial_quality


def sequence_vector(rows, reference):
    validate_reference(reference)
    legacy.validate_imu_reference(reference)
    if reference.get("processor") != PROCESSOR:
        raise ValueError("IMU processor version mismatch")
    trial_quality(rows)
    t = np.array([r["timestamp"] for r in rows], dtype=float)
    t -= t[0]
    columns = (*FLEX_COLUMNS, "ACCx", "ACCy", "ACCz", "GYRx", "GYRy", "GYRz", *legacy.BODY_COLUMNS)
    x = np.array([[r[k] for k in columns] for r in rows], dtype=float)
    if not np.isfinite(x).all() or np.any(x[:, :5] <= 8) or np.any(x[:, :5] >= 4087):
        raise ValueError("Invalid/saturated sensor feature")
    # Resampling is confined to the recorded time span; no extrapolation or
    # converting 25 Hz recordings into fictitious 100 Hz training data.
    y = np.stack([np.interp(GRID, t, x[:, i]) for i in range(x.shape[1])], axis=1)
    flex = np.array([np.median(y[max(0,i-2):min(len(y),i+3), :5], axis=0)
                     for i in range(len(y))])
    for i, key in enumerate(FLEX_COLUMNS):
        c = reference["flex_calibration"][key]
        flex[:, i] = (flex[:, i]-c["open"])/(c["closed"]-c["open"])
    # Preserve the held hand shape. Subtracting the first frame would erase
    # the distinction between static letters, regardless of which fingers bend.
    gravity = (y[:, 5:8]-y[:, 11:14])/reference["gravity"]
    gyro = y[:, 8:11]-np.asarray(reference["gyro_bias"])
    left = np.maximum(np.arange(len(y))-2, 0)
    right = np.minimum(np.arange(len(y))+2, len(y)-1)
    velocity = (flex[right]-flex[left])/((GRID[right]-GRID[left])[:, None]/1000)
    return np.column_stack((flex, gravity, gyro, y[:, 11:14], velocity)).astype(np.float32).reshape(-1)


class SequenceModel:
    def __init__(self, folder):
        import joblib
        folder = Path(folder)
        self.manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
        m = self.manifest
        if (m.get("schema"), m.get("processor"), m.get("sample_ms"), m.get("duration_ms")) != (
                SCHEMA, PROCESSOR, SAMPLE_MS, DURATION_MS) or m.get("features") != list(FEATURES):
            raise ValueError("Can model rieng cho 5 ngon; hay train_sequence_5.py")
        validate_mapping(m)
        model_path = folder/"model.joblib"
        if hashlib.sha256(model_path.read_bytes()).hexdigest() != m["model_sha256"]:
            raise ValueError("Model/manifest mismatch")
        self.model = joblib.load(model_path)
        if self.model.n_features_in_ != len(GRID)*len(FEATURES) or list(self.model.classes_) != m["labels"]:
            raise ValueError("Model shape/labels mismatch")

    def predict(self, rows, reference):
        return str(self.model.predict(sequence_vector(rows, reference)[None, :])[0])

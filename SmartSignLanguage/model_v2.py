"""Strict loader for the calibrated v2 model bundle, never falls back to v1."""
import hashlib
import json
from pathlib import Path
import numpy as np

if __package__:
    from .sensor_pipeline import SCHEMA, PROCESSOR, SAMPLE_MS, WINDOW_SIZE, MODEL_FEATURES, LABELS
else:
    from sensor_pipeline import SCHEMA, PROCESSOR, SAMPLE_MS, WINDOW_SIZE, MODEL_FEATURES, LABELS


class ModelV2:
    def __init__(self, folder, calibration):
        folder=Path(folder)
        path=folder/"manifest.json"
        if not path.exists():
            raise ValueError("Chua co model v2. Thu >=3 phien bang collect_v2.py, sau do chay train.py. Dung --pipeline legacy neu can ban cu.")
        m=json.loads(path.read_text(encoding="utf-8"))
        if (m.get("schema"),m.get("processor"),m.get("sample_ms"),m.get("window_size")) != (SCHEMA,PROCESSOR,SAMPLE_MS,WINDOW_SIZE):
            raise ValueError("Model preprocessing version/rate mismatch")
        if m.get("features") not in (list(MODEL_FEATURES),list(MODEL_FEATURES[:8])):
            raise ValueError("Unknown feature order")
        if m.get("flex1_finger") != calibration["flex1_finger"]:
            raise ValueError("Flex wiring/finger mapping differs from training")
        if set(m.get("labels",[])) != set(LABELS):
            raise ValueError("Model labels incompatible with web")
        for name in ("model.keras","scaler.pkl","encoder.pkl"):
            if hashlib.sha256((folder/name).read_bytes()).hexdigest() != m["hashes"][name]:
                raise ValueError(f"Bundle hash mismatch: {name}; do not mix different training runs")
        import joblib
        import tensorflow as tf
        self.model=tf.keras.models.load_model(folder/"model.keras")
        self.scaler=joblib.load(folder/"scaler.pkl")
        self.encoder=joblib.load(folder/"encoder.pkl")
        self.count=len(m["features"])
        if tuple(self.model.input_shape[1:]) != (WINDOW_SIZE,self.count) or self.scaler.n_features_in_ != self.count or self.encoder.classes_.tolist() != m["labels"] or self.model.output_shape[-1] != len(m["labels"]):
            raise ValueError("Model/scaler/encoder shape mismatch")

    def predict(self, window):
        x=np.asarray(window,dtype=np.float32)[:,:self.count]
        x=self.scaler.transform(x).astype(np.float32)
        p=np.asarray(self.model(x[None,...],training=False))[0]
        if not np.isfinite(p).all():
            raise ValueError("Nonfinite model prediction")
        index=int(p.argmax())
        return str(self.encoder.classes_[index]),float(p[index])

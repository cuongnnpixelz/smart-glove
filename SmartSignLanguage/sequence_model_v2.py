"""Five-second two-flex sequences. Identical preprocessing for train and live use."""
import hashlib
import json
from pathlib import Path

import numpy as np

if __package__:
    from . import sequence_model as legacy
else:
    import sequence_model as legacy

SCHEMA = "sequence-svm-v2"
PROCESSOR = legacy.PROCESSOR
SAMPLE_MS = 40
DURATION_MS = 5000
GRID = np.arange(0, DURATION_MS + 1, SAMPLE_MS)
FEATURES = (*legacy.FEATURES, "dFlex_1_adc_per_s", "dFlex_2_adc_per_s")


def sequence_vector(rows, reference):
    x = legacy.sequence_vector(rows, reference, DURATION_MS).reshape(len(GRID), -1)
    # A short median filter rejects single-sample spikes. The entire recorded
    # window is available in both training and manual live prediction.
    flex = np.array([np.median(x[max(0,i-1):min(len(x),i+2), :2], axis=0)
                     for i in range(len(x))])
    flex -= np.median(flex[GRID < 500], axis=0)
    x[:, :2] = flex
    # Slope over 160ms, in ADC/second, rather than an unscaled sample difference.
    left = np.maximum(np.arange(len(x))-2, 0)
    right = np.minimum(np.arange(len(x))+2, len(x)-1)
    velocity = (flex[right]-flex[left])/((GRID[right]-GRID[left])[:, None]/1000)
    return np.column_stack((x, velocity)).astype(np.float32).reshape(-1)


class SequenceModel:
    def __init__(self, folder):
        import joblib
        folder = Path(folder)
        self.manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
        m = self.manifest
        if (m.get("schema"), m.get("processor"), m.get("sample_ms"), m.get("duration_ms")) != (
                SCHEMA, PROCESSOR, SAMPLE_MS, DURATION_MS) or m.get("features") != list(FEATURES):
            raise ValueError("Can model v2: chuoi 5 giay, ca hai flex va dFlex; hay train lai")
        if hashlib.sha256((folder/"model.joblib").read_bytes()).hexdigest() != m["model_sha256"]:
            raise ValueError("Model/manifest mismatch")
        self.model = joblib.load(folder/"model.joblib")
        if self.model.n_features_in_ != len(GRID)*len(FEATURES) or list(self.model.classes_) != m["labels"]:
            raise ValueError("Model shape/labels mismatch")
        self.motion_checks = m.get("motion_checks", "strict")
        if self.motion_checks not in ("strict", "classifier-only"):
            raise ValueError("Unknown motion-check policy")
        self.guards = m["motion_guards"]
        if self.motion_checks == "strict" and set(self.guards) != set(m["labels"])-{"NONE"}:
            raise ValueError("Missing two-flex motion profiles")
        if self.motion_checks == "classifier-only" and self.guards:
            raise ValueError("Unexpected motion profiles for classifier-only model")

    def predict_details(self, rows, reference):
        if __package__:
            from .sequence_motion_v2 import evaluate
        else:
            from sequence_motion_v2 import evaluate
        vector = sequence_vector(rows, reference)
        candidate = str(self.model.predict(vector[None, :])[0])
        if self.motion_checks == "classifier-only":
            return candidate, candidate, "SVM thu nghiem: chua co kiem tra rieng ngon/thu tu"
        if candidate == "NONE":
            return "NONE", candidate, "Model: nghi hoac chuoi khac"
        accepted, reason = evaluate(vector, self.guards[candidate])
        return candidate if accepted else "NONE", candidate, reason

    def predict(self, rows, reference):
        return self.predict_details(rows, reference)[0]

"""Measured two-flex prerequisites and an explicit bend/tilt/return/release guard.

This is a deterministic acceptance check alongside the classifier, not an
accuracy guarantee. Fraction/angle margins are demo rules that need live tests.
"""
import numpy as np
import hashlib
import json
from pathlib import Path

if __package__:
    from .check_flex import analyze
    from .sensor_pipeline import Q_COLUMNS, multiply, timing_report
    from .sequence_model import GRID, FEATURES
else:
    from check_flex import analyze
    from sensor_pipeline import Q_COLUMNS, multiply, timing_report
    from sequence_model import GRID, FEATURES


def flex_profile(saved_report):
    report = analyze(saved_report["raw_poses"])
    if not report["two_fingers_distinguishable"]:
        raise ValueError("Chua xac dinh duoc hai kenh flex rieng; chay check_flex.py")
    issues = []
    for finger, state in report["finger_readiness"].items():
        if not state["returned_at_check"]:
            issues.append(f"{finger}/{state['channel']}: chua hoi ve moc duoi")
        if not state["stable_during_poses"]:
            issues.append(f"{finger}/{state['channel']}: tin hieu con troi khi giu tu the")
        if not state["stable_when_other_finger_moves"]:
            issues.append(f"{finger}/{state['channel']}: lech {state['inactive_drift_adc']:.1f} ADC khi ngon khac cu dong")
    if issues:
        raise ValueError("Hai flex chua dat: "+"; ".join(issues)+". Chinh cach gan/kiem tra mach, chay check_flex.py lai.")
    return {channel: report["responses"][finger][channel]
            for finger, channel in report["suggested_mapping"].items()}


def check_open_pose(rows, profile):
    timing_report(rows)
    for channel, p in profile.items():
        median = float(np.median([r[channel] for r in rows]))
        if abs(median-p["open_adc"]) > p["recovery_tolerance_adc"]:
            raise ValueError(f"{channel}: tu the duoi hien tai {median:.1f} ADC lech moc {p['open_adc']:.1f}; kiem tra gang va lay lai bao cao flex")


def rotation_vectors(quaternions):
    q = np.array(quaternions, dtype=float, copy=True)
    if not np.isfinite(q).all() or np.any(np.abs(np.linalg.norm(q, axis=1)-1) > .001):
        raise ValueError("Invalid quaternion")
    q *= np.where(q[:, :1] < 0, -1, 1)
    magnitude = np.linalg.norm(q[:, 1:], axis=1)
    angle = 2*np.arctan2(magnitude, q[:, 0])
    return q[:, 1:] * (angle/np.maximum(magnitude, 1e-12))[:, None]


def learn_direction(trials):
    """Use training trials only, retaining the signed tilt direction."""
    axes, angles = [], []
    for trial in trials:
        q = trial["vector"].reshape(len(GRID), len(FEATURES))[:, 2:6]
        rotation = rotation_vectors(q)
        magnitude = np.linalg.norm(rotation, axis=1)
        index = int(magnitude.argmax())
        if magnitude[index] < np.deg2rad(15):
            raise ValueError("Training tilt too small to establish direction")
        axes.append(rotation[index]/magnitude[index])
        angles.append(magnitude[index])
    if len(axes) < 3:
        raise ValueError("Need at least three training trials to learn tilt direction")
    axis = np.mean(axes, axis=0)
    if np.linalg.norm(axis) < .8:
        raise ValueError("Training tilt directions conflict")
    axis /= np.linalg.norm(axis)
    if np.min(np.asarray(axes)@axis) < np.cos(np.deg2rad(35)):
        raise ValueError("Training tilt directions are not consistent within 35 degrees")
    return {"axis": axis.tolist(), "angle_rad": float(np.median(angles)),
            "training_trials": len(axes)}


def prepare_guard(model_folder, data_folder):
    """Add an acceptance profile without changing or retraining the saved SVM."""
    if __package__:
        from .sequence_model import SequenceModel
        from .train_sequence import load_trials
    else:
        from sequence_model import SequenceModel
        from train_sequence import load_trials
    folder = Path(model_folder)
    model = SequenceModel(folder)
    if set(model.manifest["labels"]) != {"NONE", "NGHIENG_GAP_DUOI"}:
        raise ValueError("This guard is for the two-finger bend/tilt/return/release demo only")
    report = json.loads((folder/"report.json").read_text(encoding="utf-8"))
    for source in report["sources"]:
        path = Path(source["path"])
        if (hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"] or
                hashlib.sha256(path.with_name("imu_reference.json").read_bytes()).hexdigest() != source["reference_sha256"]):
            raise ValueError("Training source changed; do not learn a guard from changed data")
    trials, _, _ = load_trials(data_folder)
    keys = set(report["train_keys"])
    selected = [t for t in trials if t["key"] in keys]
    if {t["key"] for t in selected} != keys:
        raise ValueError("Missing original training trials")
    positive = [t for t in selected if t["label"] == "NGHIENG_GAP_DUOI"]
    guard = {"schema": "two-flex-sequence-guard-v1", "model_sha256": model.manifest["model_sha256"],
             "label": "NGHIENG_GAP_DUOI", "direction": learn_direction(positive),
             "direction_training_keys": [t["key"] for t in positive],
             "limits": "Demo rules, not an accuracy guarantee. Requires a fresh passing two-flex check; bend/release bands 0.6/0.25, tilt reach/return 0.65/0.25 of learned peak, 35-degree direction tolerance, 120ms holds."}
    with (folder/"acceptance_guard.json").open("x", encoding="utf-8") as f:
        json.dump(guard, f, indent=2)
    return guard


def _run_start(mask, times, after=0, hold_ms=120):
    start = None
    for i in range(after, len(mask)):
        if not mask[i]:
            start = None
        else:
            start = i if start is None else start
            if times[i]-times[start] >= hold_ms:
                return start
    return None


def evaluate(rows, profile, direction):
    quality = timing_report(rows)
    if not 3000 <= quality["duration_ms"] <= 3120:
        raise ValueError("Guard needs a complete 3-second sequence")
    times = np.array([r["timestamp"] for r in rows], dtype=float)
    times -= times[0]
    channels = ("flex_1", "flex_2")
    if set(profile) != set(channels):
        raise ValueError("Guard requires both flex channels")
    raw = np.array([[r[c] for c in channels] for r in rows], dtype=float)
    if not np.isfinite(raw).all():
        raise ValueError("Nonfinite flex data")
    filtered = np.array([np.median(raw[max(0,i-1):min(len(raw),i+2)], axis=0) for i in range(len(raw))])
    bend = np.stack([(filtered[:,j]-profile[c]["open_adc"])/profile[c]["delta_adc"]
                     for j,c in enumerate(channels)], axis=1)
    bad_start = [channels[j] for j in range(2) if abs(np.median(bend[:5,j])) > .25]
    if bad_start:
        return False, "Chua duoi o dau chuoi: "+", ".join(bad_start)
    missing = [channels[j] for j in range(2) if _run_start(bend[:,j] >= .6, times) is None]
    if missing:
        return False, "Chua gap ro: "+", ".join(missing)
    bent = _run_start(np.all(bend >= .6, axis=1), times)
    if bent is None:
        return False, "Hai ngon chua cung giu gap"
    q = np.asarray([[r[k] for k in Q_COLUMNS] for r in rows], dtype=float)
    inverse = q[0]*[1,-1,-1,-1]
    rotation = rotation_vectors(np.asarray([multiply(inverse, item) for item in q]))
    magnitude = np.linalg.norm(rotation, axis=1)
    axis = np.asarray(direction["axis"], dtype=float)
    target = float(direction["angle_rad"])
    if axis.shape != (3,) or not np.isfinite(axis).all() or abs(np.linalg.norm(axis)-1) > .001 or not np.isfinite(target) or target <= 0:
        raise ValueError("Invalid tilt direction profile")
    alignment = (rotation@axis)/np.maximum(magnitude, 1e-12)
    peak = int(magnitude.argmax())
    if alignment[peak] < np.cos(np.deg2rad(35)):
        return False, "Nghieng sai huong so voi mau train"
    onset_mask = magnitude >= .35*target
    onset = int(np.flatnonzero(onset_mask)[0]) if onset_mask.any() else None
    reached = _run_start((magnitude >= .65*target) & (alignment >= np.cos(np.deg2rad(35))), times)
    if reached is None:
        return False, "Chua nghieng du theo huong da hoc"
    if onset is not None and times[onset] < times[bent]+120:
        return False, "Sai thu tu: can gap truoc khi nghieng"
    returned = _run_start(magnitude <= .25*target, times, after=peak)
    if returned is None:
        return False, "Co tay chua ve tu the dau"
    if np.any(bend[bent:returned+1] < .35):
        return False, "Tha ngon truoc khi co tay ve giua"
    if _run_start(np.all(np.abs(bend) <= .25, axis=1), times, after=returned) is None or np.any(np.abs(np.median(bend[-5:],axis=0)) > .25):
        return False, "Chua duoi lai ca hai ngon o cuoi chuoi"
    return True, "Du ca hai flex: gap -> nghieng dung huong -> ve giua -> duoi"

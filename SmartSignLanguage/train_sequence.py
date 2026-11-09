"""Train a demo classifier for whole 3-second sequences, preserving legacy models."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid
import time
import threading
from contextlib import contextmanager

import numpy as np

if __package__:
    from . import sequence_model as legacy_backend
    from .session_csv import session_csv_groups, read_session
    from .sensor_pipeline import (CSV_COLUMNS, Q_COLUMNS, BODY_COLUMNS, WORLD_COLUMNS,
                                  PROCESSOR, rotate, timing_report, validate_imu_reference)
    from .sequence_model import SCHEMA, FEATURES, SAMPLE_MS, DURATION_MS, sequence_vector
else:
    import sequence_model as legacy_backend
    from session_csv import session_csv_groups, read_session
    from sensor_pipeline import (CSV_COLUMNS, Q_COLUMNS, BODY_COLUMNS, WORLD_COLUMNS,
                                 PROCESSOR, rotate, timing_report, validate_imu_reference)
    from sequence_model import SCHEMA, FEATURES, SAMPLE_MS, DURATION_MS, sequence_vector

BASE = Path(__file__).resolve().parent


class TrainingProgress:
    def __init__(self, interval=5):
        self.started = time.monotonic()
        self.interval = interval

    def log(self, message):
        print(f"[{time.monotonic()-self.started:.1f}s] {message}", flush=True)

    @contextmanager
    def stage(self, name):
        started = time.monotonic()
        stopped = threading.Event()
        self.log(name)

        def heartbeat():
            while not stopped.wait(self.interval):
                self.log(f"Dang xu ly: {name} | buoc nay: {time.monotonic()-started:.1f}s")

        worker = threading.Thread(target=heartbeat, daemon=True)
        worker.start()
        try:
            yield
        except BaseException:
            stopped.set()
            worker.join()
            self.log(f"Buoc bi dung: {name}")
            raise
        else:
            stopped.set()
            worker.join()
            self.log(f"XONG: {name} | mat {time.monotonic()-started:.1f}s")


def load_trials(root, backend=legacy_backend, progress=None, allow_no_none=False):
    columns = getattr(backend, "CSV_COLUMNS", CSV_COLUMNS)
    flex_columns = getattr(backend, "FLEX_COLUMNS", ("flex_1", "flex_2"))
    quality_check = getattr(backend, "quality_report", timing_report)
    trials, sources, skipped = [], [], []
    seen_sessions = set()
    sessions = list(session_csv_groups(root, per_label=backend.SCHEMA.startswith("sequence-svm-five-flex-")))
    for session_index, paths in enumerate(sessions, 1):
        if progress:
            progress(f"Doc phien {session_index}/{len(sessions)}: {paths[0].parent.name}")
        path = paths[0]
        raw_rows = read_session(paths, columns)
        if not raw_rows:
            skipped.append(str(path))
            continue
        ref_path = path.with_name("imu_reference.json")
        reference = json.loads(ref_path.read_text(encoding="utf-8"))
        validate_imu_reference(reference)
        if hasattr(backend, "validate_mapping"):
            backend.validate_mapping(reference)
        if hasattr(backend, "validate_reference"):
            backend.validate_reference(reference)
        if (reference.get("schema"), reference.get("processor"), reference.get("sample_ms"),
                reference.get("trial_seconds")) != ("sequence-imu-v1", backend.PROCESSOR, backend.SAMPLE_MS, backend.DURATION_MS/1000):
            raise ValueError(f"{path}: incompatible reference/duration")
        sid = reference["session_id"]
        if sid in seen_sessions:
            raise ValueError(f"Duplicate session {sid}")
        seen_sessions.add(sid)
        grouped = {}
        last_stamp, last_trial = -1, 0
        for raw in raw_rows:
            row = {k: raw[k] if k in ("user_id", "session_id", "label") else float(raw[k]) for k in columns}
            if not all(np.isfinite(v) for k,v in row.items() if k not in ("user_id", "session_id", "label")):
                raise ValueError(f"{path}: nonfinite row")
            stamp, tid = row["timestamp"], row["trial_id"]
            if stamp != int(stamp) or not last_stamp < stamp <= 0xFFFFFFFF:
                raise ValueError(f"{path}: timestamp reset/duplicate")
            if tid != int(tid) or tid < 1 or tid < last_trial:
                raise ValueError(f"{path}: invalid trial id")
            if row["session_id"] != sid or row["user_id"] != reference["user_id"]:
                raise ValueError(f"{path}: session/user mismatch")
            if not row["label"] or any(not 0 <= row[k] <= 4095 for k in flex_columns):
                raise ValueError(f"{path}: invalid label/flex")
            last_stamp, last_trial = stamp, tid
            q = np.array([row[k] for k in Q_COLUMNS])
            body = np.array([row[k] for k in BODY_COLUMNS])
            world = np.array([row[k] for k in WORLD_COLUMNS])
            acc = np.array([row[k] for k in ("ACCx", "ACCy", "ACCz")])
            if (abs(np.linalg.norm(q)-1) > .001 or
                    not np.allclose(rotate(q, body), world, atol=.001) or
                    not np.allclose(acc-body, rotate(q*[1,-1,-1,-1], [0,0,reference["gravity"]]), atol=.001)):
                raise ValueError(f"{path}: inconsistent derived IMU channels")
            grouped.setdefault(int(tid), []).append(row)
        for tid, rows in grouped.items():
            labels = {r["label"] for r in rows}
            if len(labels) != 1:
                raise ValueError(f"{path} trial {tid}: mixed labels")
            trials.append({"key": f"{sid}/{tid}", "session": sid, "user": reference["user_id"],
                           "label": rows[0]["label"], "quality": quality_check(rows),
                           "vector": backend.sequence_vector(rows, reference)})
        sources.extend({"path": str(source.resolve()), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        "reference_sha256": hashlib.sha256(ref_path.read_bytes()).hexdigest()} for source in paths)
        if progress:
            progress(f"Da xu ly {session_index}/{len(sessions)} phien ({session_index/len(sessions):.0%}); {len(trials)} trials hop le")
    counts = Counter(t["label"] for t in trials)
    if len(counts) < 2 or ("NONE" not in counts and not allow_no_none):
        raise ValueError(f"Need NONE and at least one gesture; found {dict(counts)}")
    if min(counts.values()) < 4:
        raise ValueError(f"Need at least 4 complete trials per label; found {dict(counts)}")
    return trials, sources, skipped


def split_trials(trials, seed=42):
    from sklearn.model_selection import GroupShuffleSplit, train_test_split
    labels = np.array([t["label"] for t in trials])
    groups = np.array([t["session"] for t in trials])
    required = set(labels)
    indices = np.arange(len(trials))
    if len(set(groups)) >= 2:
        for train, test in GroupShuffleSplit(n_splits=50, test_size=.25, random_state=seed).split(indices, labels, groups):
            if set(labels[train]) == required and set(labels[test]) == required:
                return train, test, "session_holdout"
    # Explicit demo fallback: split WHOLE trials, never rows/overlapping windows.
    train, test = train_test_split(indices, test_size=max(len(required), int(np.ceil(.25*len(trials)))),
                                   random_state=seed, stratify=labels)
    return train, test, "within_session_trial_holdout"


def main(argv=None, backend=legacy_backend):
    v2 = backend.SCHEMA == "sequence-svm-v2"
    five = backend.SCHEMA.startswith("sequence-svm-five-flex-")
    parser = argparse.ArgumentParser(description="Train calibrated five-finger gestures, 100 Hz / 1.5 seconds." if five else
                                     "Train whole sequences; v2 uses 5 seconds and both flex slopes." if v2 else __doc__)
    parser.add_argument("--data", type=Path, default=BASE/getattr(backend, "DATA_DIRECTORY", "sequence_data_v2" if v2 else "sequence_data"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--train-all", action="store_true", help="Fit all valid trials without a test split or accuracy evaluation")
    parser.add_argument("--allow-trial-split", action="store_true", help="V2: allow preliminary same-session demo evaluation")
    parser.add_argument("--allow-no-none", action="store_true", help="Experimental closed-set test: permit training without a rest/background label")
    parser.add_argument("--motion-checks", choices=("classifier-only",) if five else ("strict", "classifier-only"),
                        default="classifier-only" if five else "strict",
                        help="V2: classifier-only learns arbitrary labels without the two-finger motion rules; experimental")
    args = parser.parse_args(argv)
    progress = TrainingProgress()
    try:
        with progress.stage("Buoc 1/5: Doc, kiem tra du lieu va trich dac trung"):
            trials, sources, skipped = load_trials(args.data, backend, progress=progress.log,
                                                   allow_no_none=args.allow_no_none)
        if not any(t['label'] == 'NONE' for t in trials):
            progress.log("THU NGHIEM KHONG NONE: khi nghi/lam dong tac la, model van chon mot ky hieu da hoc.")
        with progress.stage("Buoc 2/5: Chon du lieu train"):
            if args.train_all:
                train, test, scope = np.arange(len(trials)), np.array([], dtype=int), "full_data_no_test"
            else:
                train, test, scope = split_trials(trials, args.seed)
        counts = Counter(t["label"] for t in trials)
        session_counts = {s: dict(Counter(t["label"] for t in trials if t["session"] == s))
                          for s in sorted({t["session"] for t in trials})}
        print(f"DATA: {len(trials)} trials; {dict(counts)}", flush=True)
        print(f"SPLIT: train={len(train)}, test={len(test)}; {scope}", flush=True)
        warning = None
        if args.train_all:
            warning = "Trained on all available trials; no held-out evaluation was performed."
        elif scope != "session_holdout":
            warning = ("Demo only: labels cannot be evaluated in separate sessions. "
                       "Trial holdout shares recording sessions with training; "
                       "scores do not establish performance on a new glove session.")
            print("LUU Y: chi danh gia demo trong phien; chua chung minh do chinh xac o phien moi.", flush=True)
            if (v2 or five) and not args.allow_trial_split:
                raise ValueError("Can it nhat 2 phien, MOI phien co NONE va cu chi. Khuyen nghi 3 phien; dung --allow-trial-split chi de thu so bo")
        guards = None
        if v2 and args.motion_checks == "strict":
            if __package__:
                from .sequence_motion_v2 import learn_profiles, evaluate
            else:
                from sequence_motion_v2 import learn_profiles, evaluate
            guards = learn_profiles([trials[i] for i in train])
        elif v2:
            print("MODEL THU NGHIEM: SVM hoc nhan tu du lieu; KHONG ap luat bat buoc gap ca hai ngon.", flush=True)
            print("Can thu truc tiep chi nghieng/chi gap/sai ngon de kiem tra nhan nham.", flush=True)
        if args.check_only:
            progress.log("DA XONG kiem tra du lieu; khong train model.")
            return 0
        output = args.output or BASE/"models"/(getattr(backend, "MODEL_PREFIX", "sequence_v2_" if v2 else "sequence_")+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8])
        if output.exists():
            raise ValueError("Output already exists; choose a new --output to preserve the saved model")
        import joblib
        import sklearn
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.svm import SVC
        from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, classification_report
        x = np.stack([t["vector"] for t in trials])
        y = np.array([t["label"] for t in trials])
        model = make_pipeline(StandardScaler(), SVC(C=1, kernel="rbf", class_weight="balanced"))
        progress.log("SVM khong cung cap %/epoch trong luc fit; hien thoi gian cho den khi hoan tat.")
        with progress.stage("Buoc 3/5: Train SVM"):
            model.fit(x[train], y[train])
        with progress.stage("Buoc 4/5: Bo qua test" if args.train_all else "Buoc 4/5: Du doan tap test"):
            predicted = np.array([], dtype=str) if args.train_all else model.predict(x[test])
        classifier_predicted = predicted.copy()
        if v2 and guards is not None:
            predicted = np.array([p if p == "NONE" or evaluate(x[i], guards[str(p)])[0] else "NONE"
                                  for i, p in zip(test, predicted)])
        labels = list(model.classes_)
        report = {"evaluation_scope": scope, "warning": warning, "seed": args.seed,
                  "motion_checks": args.motion_checks if (v2 or five) else "legacy",
                  "trial_counts": dict(counts), "session_counts": session_counts,
                  "train_keys": [trials[i]["key"] for i in train],
                  "test_keys": [trials[i]["key"] for i in test],
                  "accuracy": None if args.train_all else float(accuracy_score(y[test], predicted)),
                  "classifier_accuracy_before_motion_checks": None if args.train_all else float(accuracy_score(y[test], classifier_predicted)),
                  "balanced_accuracy": None if args.train_all else float(balanced_accuracy_score(y[test], predicted)),
                  "labels": labels, "confusion_matrix": None if args.train_all else confusion_matrix(y[test], predicted, labels=labels).tolist(),
                  "classification": None if args.train_all else classification_report(y[test], predicted, labels=labels, output_dict=True, zero_division=0),
                  "predictions": [{"key": trials[i]["key"], "actual": str(y[i]), "predicted": str(p)} for i,p in zip(test,predicted)],
                  "sources": sources, "skipped_empty_files": skipped}
        progress.log("Buoc 5/5: Luu model va bao cao")
        output.mkdir(parents=True, exist_ok=False)
        joblib.dump(model, output/"model.joblib")
        manifest = {"background_label_present": "NONE" in labels,
                    "schema": backend.SCHEMA, "processor": backend.PROCESSOR, "sample_ms": backend.SAMPLE_MS,
                    "duration_ms": backend.DURATION_MS, "features": list(backend.FEATURES), "labels": labels,
                    "sklearn_version": sklearn.__version__, "evaluation_scope": scope,
                    "model_sha256": hashlib.sha256((output/"model.joblib").read_bytes()).hexdigest(),
                    "input": f"whole {backend.DURATION_MS/1000:g}-second sequence, fixed {len(backend.GRID)}-sample grid; one prediction per trial",
                    "scaling": "StandardScaler fit only on training trials, per flattened time/feature position"}
        if five:
            manifest.update(flex_pins=backend.FLEX_PINS, fingers=backend.FINGERS,
                            csv_columns=list(backend.CSV_COLUMNS))
        if v2 or five:
            manifest["motion_checks"] = args.motion_checks
            manifest["motion_guards"] = guards if guards is not None else {}
            manifest["preprocessing"] = "3-sample median flex; first 0.5s baseline; 160ms centered dFlex in ADC/s; allow partial flex recovery"
        if five:
            manifest["preprocessing"] = backend.PREPROCESSING
        (output/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (output/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if not v2 and not five and set(labels) == {"NONE", "NGHIENG_GAP_DUOI"}:
            if __package__:
                from .sequence_guard import prepare_guard
            else:
                from sequence_guard import prepare_guard
            prepare_guard(output, args.data)
        if args.train_all:
            print(f"TRAIN TOAN BO: {len(train)} trials; KHONG TEST, khong co diem accuracy moi.")
        else:
            print(f"TEST: {report['accuracy']:.1%} ({len(test)} trials); scope={scope}")
        print(f"MODEL: {output.resolve()}")
        progress.log("HOAN TAT 5/5 buoc. Thoi gian trong ngoac la tong thoi gian chay.")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"LOI: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

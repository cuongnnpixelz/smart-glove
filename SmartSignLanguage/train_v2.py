"""Train v2 from calibrated sessions; fixed-time windows and disjoint held-out groups."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np

if __package__:
    from .sensor_pipeline import (SCHEMA, PROCESSOR, CSV_COLUMNS, MODEL_FEATURES, LABELS,
        Q_COLUMNS, BODY_COLUMNS, WORLD_COLUMNS, SAMPLE_MS, WINDOW_MS, WINDOW_SIZE,
        load_calibration, make_window, rotate, timing_report)
else:
    from sensor_pipeline import (SCHEMA, PROCESSOR, CSV_COLUMNS, MODEL_FEATURES, LABELS,
        Q_COLUMNS, BODY_COLUMNS, WORLD_COLUMNS, SAMPLE_MS, WINDOW_MS, WINDOW_SIZE,
        load_calibration, make_window, rotate, timing_report)

BASE = Path(__file__).resolve().parent


def read_dataset(root):
    trials = []
    sources = []
    mappings = set()
    seen_sessions = set()
    files = sorted(Path(root).rglob("samples.csv"))
    if not files:
        raise ValueError("No v2 samples.csv. Run collect_v2.py on the real glove first; old CSVs are not converted automatically.")
    for path in files:
        calibration_path = path.with_name("calibration.json")
        c = load_calibration(calibration_path)
        mappings.add(c["flex1_finger"])
        sid = c["session_id"]
        if sid in seen_sessions:
            raise ValueError(f"Duplicate session {sid}")
        seen_sessions.add(sid)
        with path.open(encoding="utf-8",newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != list(CSV_COLUMNS):
                raise ValueError(f"{path}: expected v2 header; do not mix legacy files")
            raw_rows = list(reader)
        grouped = {}
        previous_stamp = -1
        previous_trial = -1
        for raw in raw_rows:
            row = {k:raw[k] if k in ("user_id","session_id","label") else float(raw[k]) for k in CSV_COLUMNS}
            if not all(np.isfinite(row[k]) for k in CSV_COLUMNS if k not in ("user_id","session_id","label")):
                raise ValueError(f"{path}: missing/nonfinite numeric field")
            if row["timestamp"] <= previous_stamp or row["timestamp"] != int(row["timestamp"]) or not 0<=row["timestamp"]<=0xFFFFFFFF:
                raise ValueError(f"{path}: timestamp reset/duplicate/out of range")
            previous_stamp = row["timestamp"]
            tid = row["trial_id"]
            if tid != int(tid) or tid < 1 or tid < previous_trial:
                raise ValueError(f"{path}: invalid/noncontiguous trial id")
            previous_trial = tid
            if row["session_id"] != sid or row["user_id"] != c["user_id"] or row["label"] not in LABELS:
                raise ValueError(f"{path}: session/user/label mismatch")
            if any(not 0<=row[k]<=4095 for k in ("flex_1","flex_2")):
                raise ValueError(f"{path}: flex ADC outside 12-bit range")
            q = np.array([row[k] for k in Q_COLUMNS])
            body = np.array([row[k] for k in BODY_COLUMNS])
            world = np.array([row[k] for k in WORLD_COLUMNS])
            acceleration = np.array([row[k] for k in ("ACCx","ACCy","ACCz")])
            if abs(np.linalg.norm(q)-1)>.001 or not np.allclose(rotate(q,body),world,atol=.001) or not np.allclose(acceleration-body,rotate(q*[1,-1,-1,-1],[0,0,c["gravity"]]),atol=.001):
                raise ValueError(f"{path}: quaternion/derived acceleration inconsistent")
            grouped.setdefault(int(tid),[]).append(row)
        for tid, rows in grouped.items():
            if len({r["label"] for r in rows}) != 1:
                raise ValueError(f"{path} trial {tid}: conflicting labels")
            quality = timing_report(rows)
            if not 2200<=quality["duration_ms"]<=2700:
                raise ValueError(f"{path} trial {tid}: duration must be about 2.4s, found {quality['duration_ms']}ms")
            windows = []
            # Same 40 ms interpolation and 200 ms hop as live inference.
            for end in np.arange(rows[0]["timestamp"]+WINDOW_MS,rows[-1]["timestamp"]+1,200):
                windows.append(make_window(rows,c,end))
            trials.append({"key":f"{sid}/{tid}","session":sid,"user":c["user_id"],
                           "label":rows[0]["label"],"windows":windows,"quality":quality})
        sources.append({"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                        "calibration_sha256":hashlib.sha256(calibration_path.read_bytes()).hexdigest()})
    if len(mappings)!=1:
        raise ValueError("Physical flex1 finger mapping differs between sessions; do not mix wiring")
    return trials,sources,mappings.pop()


def split_trials(trials, group_by="session", seed=42):
    groups = sorted({t[group_by] for t in trials})
    if len(groups)<3:
        raise ValueError(f"Need >=3 independent {group_by}s, preferably >=5; do not split adjacent windows randomly")
    for group in groups:
        if {t["label"] for t in trials if t[group_by]==group} != set(LABELS):
            raise ValueError(f"{group_by} {group} must contain every label including NONE")
    np.random.default_rng(seed).shuffle(groups)
    holdout = max(1,int(len(groups)*.2))
    parts = {"test":groups[:holdout],"validation":groups[holdout:2*holdout],"train":groups[2*holdout:]}
    result = {name:[t for t in trials if t[group_by] in selected] for name,selected in parts.items()}
    for name, items in result.items():
        counts = Counter(t["label"] for t in items)
        required = 10 if name=="train" else 3
        if any(counts[k]<required for k in LABELS):
            raise ValueError(f"{name}: need >= {required} independent trials per label; found {dict(counts)}")
    return result, parts


def build_parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data",type=Path,default=BASE/"data_v2")
    p.add_argument("--output",type=Path,default=BASE/"models"/"v2")
    p.add_argument("--group-by",choices=("session","user"),default="session")
    p.add_argument("--features",choices=("base8","imu11"),default="imu11")
    p.add_argument("--epochs",type=int,default=80)
    p.add_argument("--seed",type=int,default=42)
    p.add_argument("--check-only",action="store_true",help="Validate CSV, timing and splits without training or writing")
    return p


def main(argv=None):
    args=build_parser().parse_args(argv)
    try:
        trials,sources,mapping=read_dataset(args.data)
        splits,groups=split_trials(trials,args.group_by,args.seed)
        for name,items in splits.items():
            print(f"{name}: {len(items)} trials; {dict(Counter(t['label'] for t in items))}; groups={groups[name]}")
        if args.check_only:
            return 0
        if args.output.exists():
            raise ValueError("Output already exists. Choose a new --output; existing model is never overwritten")
        if not 1<=args.epochs<=1000:
            raise ValueError("epochs must be 1..1000")
        import joblib
        from sklearn.preprocessing import StandardScaler, LabelEncoder
        from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
        import tensorflow as tf
        tf.keras.utils.set_random_seed(args.seed)
        features=MODEL_FEATURES[:8] if args.features=="base8" else MODEL_FEATURES
        encoder=LabelEncoder().fit(list(LABELS))
        arrays={}
        for name,items in splits.items():
            x=np.stack([w[:,:len(features)] for t in items for w in t["windows"]])
            y=encoder.transform([t["label"] for t in items for _ in t["windows"]])
            arrays[name]=(x,y)
        scaler=StandardScaler().fit(arrays["train"][0].reshape(-1,len(features)))
        for name,(x,y) in arrays.items():
            arrays[name]=(scaler.transform(x.reshape(-1,len(features))).reshape(x.shape).astype(np.float32),y)
        model=tf.keras.Sequential([
            tf.keras.layers.Input((WINDOW_SIZE,len(features))),
            tf.keras.layers.Conv1D(16,5,activation="relu"),
            tf.keras.layers.MaxPooling1D(2),
            tf.keras.layers.Conv1D(32,3,activation="relu"),
            tf.keras.layers.GlobalAveragePooling1D(),
            tf.keras.layers.Dropout(.25),
            tf.keras.layers.Dense(len(encoder.classes_),activation="softmax"),
        ])
        model.compile(optimizer="adam",loss="sparse_categorical_crossentropy",metrics=["accuracy"])
        model.fit(*arrays["train"],validation_data=arrays["validation"],epochs=args.epochs,
                  batch_size=16,callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_loss",patience=12,restore_best_weights=True)])
        x_test,y_test=arrays["test"]
        probabilities=model(x_test,training=False).numpy()
        predictions=probabilities.argmax(axis=1)
        offset=0; trial_true=[]; trial_pred=[]
        for trial in splits["test"]:
            n=len(trial["windows"])
            trial_true.append(encoder.transform([trial["label"]])[0])
            trial_pred.append(probabilities[offset:offset+n].mean(axis=0).argmax())
            offset+=n
        report={"window_accuracy":float(accuracy_score(y_test,predictions)),
                "trial_accuracy":float(accuracy_score(trial_true,trial_pred)),
                "trial_macro_f1":float(f1_score(trial_true,trial_pred,average="macro")),
                "trial_confusion_matrix":confusion_matrix(trial_true,trial_pred,labels=range(len(LABELS))).tolist(),
                "classes":encoder.classes_.tolist(),"groups":groups,"group_by":args.group_by,
                "trials":{k:[t["key"] for t in v] for k,v in splits.items()},"sources":sources,
                "seed":args.seed,"note":"Held-out groups; continuous-stream accuracy/false activations still require real glove testing."}
        # Save only after training succeeds. Missing manifest means incomplete bundle.
        args.output.mkdir(parents=True,exist_ok=False)
        model.save(args.output/"model.keras")
        joblib.dump(scaler,args.output/"scaler.pkl")
        joblib.dump(encoder,args.output/"encoder.pkl")
        (args.output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        manifest={"schema":SCHEMA,"processor":PROCESSOR,"sample_ms":SAMPLE_MS,
                  "window_size":WINDOW_SIZE,"features":list(features),"flex1_finger":mapping,
                  "labels":encoder.classes_.tolist(),"created_utc":datetime.now(timezone.utc).isoformat(),
                  "hashes":{f:hashlib.sha256((args.output/f).read_bytes()).hexdigest() for f in ("model.keras","scaler.pkl","encoder.pkl")}}
        (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        print(f"Saved {args.output}; held-out trial accuracy {report['trial_accuracy']:.1%}. Test on the glove before using as final results.")
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__=="__main__":
    raise SystemExit(main())

"""Synthetic end-to-end train/load/infer check, never writes production data/models."""
import json
from pathlib import Path
import sys
import tempfile
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from SmartSignLanguage.collect_v2 import save_trial
from SmartSignLanguage.sensor_pipeline import SensorProcessor, make_window, MODEL_FEATURES
from SmartSignLanguage.train_v2 import main as train
from SmartSignLanguage.model_v2 import ModelV2
from test_pipeline_v2 import calibration, raw


def main():
    artifacts=ROOT/".runtime"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v2-smoke-",dir=artifacts) as temporary:
        folder=Path(temporary)
        for session in range(3):
            c=calibration(f"synthetic{session}")
            target=folder/"data"/c["session_id"]
            target.mkdir(parents=True)
            (target/"calibration.json").write_text(json.dumps(c))
            p=SensorProcessor(c)
            for t in range(0,2440,40):
                p.process(t,raw())
            stamp=2440
            trial=0
            for label in ("XIN_CHAO","CAM_ON_NHIEU","NONE"):
                for repeat in range(10):
                    trial+=1
                    rows=[]
                    for n in range(61):
                        bend=80*np.sin(np.pi*n/60)**2
                        r=raw(f1=1000-bend if label=="CAM_ON_NHIEU" else 1000,
                              f2=1100-bend if label=="XIN_CHAO" else 1100)
                        rows.append(p.process(stamp,r));stamp+=40
                    save_trial(target/"samples.csv",rows,c,trial,label)
        model=folder/"model"
        result=train(["--data",str(folder/"data"),"--output",str(model),"--epochs","2"])
        assert result==0
        predictor=ModelV2(model,c)
        label,confidence=predictor.predict(make_window(rows,c))
        assert label in ("XIN_CHAO","CAM_ON_NHIEU","NONE") and 0<=confidence<=1
        manifest=json.loads((model/"manifest.json").read_text())
        assert manifest["features"]==list(MODEL_FEATURES)
        with (model/"scaler.pkl").open("ab") as changed:
            changed.write(b"tampered")
        try:
            ModelV2(model,c)
            raise AssertionError("Mixed model bundle was accepted")
        except ValueError as error:
            assert "hash mismatch" in str(error)
        print("PASS: synthetic collection CSV -> session split -> train -> saved bundle -> live input -> prediction; corrupt bundle rejected.")
        print("Synthetic scores above are SOFTWARE TESTS ONLY, not real glove accuracy. Temporary files are removed.")


if __name__=="__main__":
    main()

"""Whole-phrase SVM: retain raw recordings, resample features on normalized time."""
import hashlib
import json
from pathlib import Path
import numpy as np

if __package__:
    from . import sequence_model_5 as word
    from .phrase_data import validate_phrase_reference, phrase_quality
else:
    import sequence_model_5 as word
    from phrase_data import validate_phrase_reference, phrase_quality

SCHEMA = 'sequence-svm-five-flex-phrase-v1'
PHRASE = True
PROCESSOR = word.PROCESSOR
SAMPLE_MS = 10
DURATION_MS = 0
GRID = np.linspace(0, 1, 300)
FEATURES = word.FEATURES
FLEX_COLUMNS, FLEX_PINS, FINGERS = word.FLEX_COLUMNS, word.FLEX_PINS, word.FINGERS
CSV_COLUMNS = word.CSV_COLUMNS
validate_mapping = word.validate_mapping
validate_reference = validate_phrase_reference
DATA_DIRECTORY = 'phrase_data_5_100hz'
MODEL_PREFIX = 'phrase_5_100hz_'
PREPROCESSING = '5-sample median flex; per-session endpoints; physical-time flex slope; 300 normalized-time feature points across complete phrase'


def quality_report(rows, reference):
    seconds = len(rows)/100
    if rows and 'label' in rows[0]:
        label = rows[0]['label']
        if label not in reference['label_settings']:
            raise ValueError(f'Missing phrase settings: {label}')
        seconds = reference['label_settings'][label]['seconds']
    result = phrase_quality(rows, seconds, reference)
    return dict(result, seconds=seconds)


def sequence_vector(rows, reference):
    validate_reference(reference)
    quality_report(rows, reference)
    t = np.asarray([r['timestamp'] for r in rows], dtype=float)
    t = (t-t[0])/1000
    keys = (*FLEX_COLUMNS, 'ACCx','ACCy','ACCz','GYRx','GYRy','GYRz', *word.legacy.BODY_COLUMNS)
    x = np.asarray([[r[k] for k in keys] for r in rows], dtype=float)
    if not np.isfinite(x).all():
        raise ValueError('Nonfinite phrase features')
    flex = np.array([np.median(x[max(0,i-2):min(len(x),i+3),:5],axis=0) for i in range(len(x))])
    for i,k in enumerate(FLEX_COLUMNS):
        c = reference['flex_calibration'][k]
        flex[:,i] = (flex[:,i]-c['open'])/(c['closed']-c['open'])
    left=np.maximum(np.arange(len(x))-2,0);right=np.minimum(np.arange(len(x))+2,len(x)-1)
    slope=(flex[right]-flex[left])/(t[right]-t[left])[:,None]
    features=np.column_stack((flex,(x[:,5:8]-x[:,11:14])/reference['gravity'],
                              x[:,8:11]-np.asarray(reference['gyro_bias']),x[:,11:14],slope))
    # Interpolation creates model features, not fabricated acquisition rows.
    grid=GRID*t[-1]
    return np.column_stack([np.interp(grid,t,features[:,i]) for i in range(features.shape[1])]).astype(np.float32).reshape(-1)


class PhraseModel:
    def __init__(self, folder):
        import joblib
        folder=Path(folder)
        self.manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        m=self.manifest
        if m.get('schema')!=SCHEMA or m.get('processor')!=PROCESSOR or m.get('features')!=list(FEATURES):
            raise ValueError('Can model cau rieng')
        path=folder/'model.joblib'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=m['model_sha256']:
            raise ValueError('Model hash mismatch')
        self.model=joblib.load(path)
        if self.model.n_features_in_!=len(GRID)*len(FEATURES) or list(self.model.classes_)!=m['labels']:
            raise ValueError('Phrase model shape/labels mismatch')
        self.durations=m['phrase_seconds']

    def predict(self, rows, reference):
        seconds=len(rows)/100
        if seconds not in self.durations:
            raise ValueError('Thoi gian chua co trong du lieu train cau')
        label=str(self.model.predict(sequence_vector(rows,reference)[None,:])[0])
        if seconds not in self.manifest['label_seconds'][label]:
            return 'NONE'
        return label

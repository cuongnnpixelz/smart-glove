"""Compile the real C++ model/features on Windows and compare against Python.

Uses zig c++ as a host compiler. No device is flashed or modified.
"""
import argparse
import ctypes as ct
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from SmartSignLanguage import sequence_model_5 as backend
from SmartSignLanguage.train_sequence import load_trials
from SmartSignLanguage.session_csv import session_csv_groups, read_session
from SmartSignLanguage.sensor_pipeline import ImuProcessor
from SmartSignLanguage.predict_sentence_words import filter_window_predictions
from export_model import DEFAULT


class Sample(ct.Structure):
    _fields_ = [('stamp', ct.c_uint32), ('flex', ct.c_double*5), ('acc', ct.c_double*3),
                ('gyro', ct.c_double*3), ('body', ct.c_double*3)]


class Calibration(ct.Structure):
    _fields_ = [('opened', ct.c_double*5), ('closed', ct.c_double*5),
                ('bias', ct.c_double*3), ('gravity', ct.c_double)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', type=Path, default=ROOT.parent/'.runtime/s3_tools/ziglang/zig.exe')
    parser.add_argument('--data', type=Path, default=ROOT.parent/'.runtime/training_u6_four_words_20261117/data')
    args = parser.parse_args()
    build = ROOT.parent/'.runtime/s3_conversion_check'
    build.mkdir(parents=True, exist_ok=True)
    wrapper = build/'wrapper.cpp'
    wrapper.write_text('''#include "model.h"
#include "features.h"
#include "sentence.h"
using namespace GloveFeatures;
extern "C" __declspec(dllexport) int predict(const float* x) {
 uint16_t votes[15]; return GloveModel::predict(x,votes);
}
extern "C" __declspec(dllexport) int build_features(const Sample* s, const Calibration* c, float* x) {
 double grid[150][14], flex[150][5];return build(s,*c,x,grid,flex);
}
extern "C" __declspec(dllexport) void process_imu(Sample* s, int n, const Calibration* c) {
 Imu imu; for(int i=0;i<n;++i) imu.process(s[i],*c);
}
extern "C" __declspec(dllexport) int sentence_words(const int* labels,int n,int* words) {
 Sentence s; for(int i=0;i<n;++i) { if(s.push(labels[i])<0) return -1; } return s.words(words);
}
''', encoding='utf-8')
    dll = build/'glove_check.dll'
    subprocess.run([str(args.compiler.resolve()),'c++','-shared','-O2','-std=c++11',
                    '-I'+str(ROOT/'firmware'),str(wrapper),str(ROOT/'firmware/model_data.cpp'),
                    '-o',str(dll)], check=True)
    lib = ct.CDLL(str(dll))
    fp = ct.POINTER(ct.c_float)
    lib.predict.argtypes = [fp]
    lib.build_features.argtypes = [ct.POINTER(Sample),ct.POINTER(Calibration),fp]
    lib.process_imu.argtypes = [ct.POINTER(Sample),ct.c_int,ct.POINTER(Calibration)]
    lib.sentence_words.argtypes = [ct.POINTER(ct.c_int),ct.c_int,ct.POINTER(ct.c_int)]
    model = backend.SequenceModel(DEFAULT)
    trials, _, _ = load_trials(args.data, backend)
    mismatches = []
    expected_labels = model.model.predict(np.stack([t['vector'] for t in trials]))
    for trial, a in zip(trials, expected_labels):
        x = np.ascontiguousarray(trial['vector'],dtype=np.float32)
        b = model.manifest['labels'][lib.predict(x.ctypes.data_as(fp))]
        if a != b: mismatches.append(trial['key'])
    max_error = 0.; feature_label_errors = 0; count = 0; imu_error=0.
    for paths in session_csv_groups(args.data, per_label=True):
        ref=json.loads((paths[0].parent/'imu_reference.json').read_text())
        raw=read_session(paths, backend.CSV_COLUMNS)
        grouped={}
        for r in raw:
            r={k:v if k in ('user_id','session_id','label') else float(v) for k,v in r.items()}
            grouped.setdefault(r['trial_id'],[]).append(r)
        c=Calibration()
        for k in range(5):
            c.opened[k]=ref['flex_calibration'][f'flex_{k+1}']['open']
            c.closed[k]=ref['flex_calibration'][f'flex_{k+1}']['closed']
        for k in range(3):c.bias[k]=ref['gyro_bias'][k]
        c.gravity=ref['gravity']
        for rows in grouped.values():
            samples=(Sample*150)()
            for i,row in enumerate(rows):
                samples[i].stamp=int(row['timestamp'])
                for k in range(5):samples[i].flex[k]=row[f'flex_{k+1}']
                for k,axis in enumerate('xyz'):
                    samples[i].acc[k]=row['ACC'+axis]
                    samples[i].gyro[k]=row['GYR'+axis]
                    samples[i].body[k]=row['ACC'+axis+'_body']
            out=np.zeros(2850,np.float32)
            assert lib.build_features(samples,ct.byref(c),out.ctypes.data_as(fp))
            expected=backend.sequence_vector(rows,ref)
            max_error=max(max_error,float(np.max(np.abs(out-expected))))
            if lib.predict(out.ctypes.data_as(fp)) != lib.predict(expected.ctypes.data_as(fp)):feature_label_errors+=1
            count+=1
        # Run IMU from a known first pose through identical raw samples. The
        # saved body channels start earlier, so compare fresh Python processing.
        rows=next(iter(grouped.values())); samples=(Sample*350)(); py=ImuProcessor(ref)
        expected_body=[]
        # A moving recorded trial cannot seed orientation. Feed a stationary
        # two-second prefix to both implementations before replaying the motion.
        for i in range(200):
            samples[i].stamp=3000+i*10
            samples[i].acc[2]=c.gravity
            raw={f'flex_{k+1}':1000 for k in range(5)}
            for k,axis in enumerate('xyz'):
                samples[i].gyro[k]=c.bias[k]
                raw['ACC'+axis]=c.gravity if k==2 else 0
                raw['GYR'+axis]=c.bias[k]
            processed=py.process(samples[i].stamp,raw)
            expected_body.append([processed['ACC'+axis+'_body'] for axis in 'xyz'])
        for i,row in enumerate(rows):
            sample=samples[i+200]
            sample.stamp=5000+int(row['timestamp']-rows[0]['timestamp'])
            for k,axis in enumerate('xyz'):
                sample.acc[k]=row['ACC'+axis];sample.gyro[k]=row['GYR'+axis]
            processed=py.process(sample.stamp,row)
            expected_body.append([processed['ACC'+axis+'_body'] for axis in 'xyz'])
        lib.process_imu(samples,350,ct.byref(c))
        imu_error=max(imu_error,float(np.max(np.abs(np.array([list(s.body) for s in samples])-expected_body))))
    rng=np.random.default_rng(42); sentence_cases=0
    labels=model.manifest['labels']; none=labels.index('NONE')
    cases=[[labels.index('TOI')]*6+[labels.index('CAM_ON')]*3+[labels.index('BAN')]*5+[none]*10]
    for _ in range(2000):
        sequence=[]
        for _ in range(int(rng.integers(1,15))): sequence += [int(rng.integers(15))]*int(rng.integers(1,12))
        cases.append(sequence+[none]*10)
    for sequence in cases:
        native=(ct.c_int*len(sequence))(*sequence);out=(ct.c_int*128)()
        n=lib.sentence_words(native,len(sequence),out)
        actual=[labels[out[i]] for i in range(n)]
        expected,_=filter_window_predictions([labels[i] for i in sequence],5)
        assert actual==expected,(actual,expected)
        sentence_cases+=1
    report=dict(trials=len(trials),model_label_mismatches=mismatches,
                feature_windows=count,feature_max_absolute_error=max_error,
                feature_label_mismatches=feature_label_errors,imu_max_absolute_error=imu_error,
                sentence_cases=sentence_cases,
                scope='Host C++ equivalence only. Not S3 hardware or independent accuracy evaluation.')
    (ROOT/'verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    assert not mismatches and feature_label_errors==0 and max_error<1e-5 and imu_error<1e-8


if __name__=='__main__':main()

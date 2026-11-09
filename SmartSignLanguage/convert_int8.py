import os
import sys
import numpy as np
import pandas as pd
import joblib
import tensorflow as tf

MODEL_FILE = "gesture_model.keras"
SCALER_FILE = "gesture_scaler.pkl"
CSV_FILE = "dataset_gesture.csv"
OUTPUT_FILE = "gesture_model_int8.tflite"

WINDOW_SIZE = 50

FEATURE_COLS = [
    "flex1", "flex2",
    "dFlex1", "dFlex2",
    "dFlex1Avg", "dFlex2Avg",
    "ax", "ay", "az",
    "gx", "gy", "gz"
]


def check_file(path):
    if not os.path.exists(path):
        print("LOI: Khong tim thay file:", path)
        print("Hay dat file nay cung thu muc voi convert_int8.py")
        sys.exit(1)


print("=" * 60)
print("CONVERT KERAS -> TFLITE INT8 CHO ESP32")
print("=" * 60)

for f in [MODEL_FILE, SCALER_FILE, CSV_FILE]:
    check_file(f)


# =========================================================
# 1. LOAD MODEL
# =========================================================

print("\n[1/6] Dang load Keras model...")

model = tf.keras.models.load_model(MODEL_FILE)

print("Model input :", model.input_shape)
print("Model output:", model.output_shape)

input_shape = model.input_shape

if len(input_shape) != 3:
    print("LOI: Model khong co input dang (batch, time, feature)")
    sys.exit(1)

expected_t = input_shape[1]
expected_f = input_shape[2]

if expected_t is not None and expected_t != WINDOW_SIZE:
    print(
        "LOI: Model can",
        expected_t,
        "mau/window, nhung code dang dung",
        WINDOW_SIZE
    )
    sys.exit(1)

if expected_f is not None and expected_f != len(FEATURE_COLS):
    print(
        "LOI: Model can",
        expected_f,
        "feature, nhung code co",
        len(FEATURE_COLS)
    )
    sys.exit(1)


# =========================================================
# 2. LOAD SCALER
# =========================================================

print("\n[2/6] Dang load scaler...")

scaler = joblib.load(SCALER_FILE)

print("Da load:", SCALER_FILE)


# =========================================================
# 3. LOAD DATASET
# =========================================================

print("\n[3/6] Dang doc dataset...")

df = pd.read_csv(CSV_FILE)

required_cols = ["trial_id", "label"] + FEATURE_COLS

missing = []

for c in required_cols:
    if c not in df.columns:
        missing.append(c)

if missing:
    print("LOI: Dataset thieu cac cot:")
    print(missing)
    sys.exit(1)


print("Tong so dong :", len(df))
print("So trial     :", df["trial_id"].nunique())
print("So lop       :", df["label"].nunique())
print("Nhan         :", sorted(df["label"].unique().tolist()))


# =========================================================
# 4. TAO WINDOW 50 x 12
# =========================================================

print("\n[4/6] Dang tao representative dataset...")

windows = []

for trial_id, group in df.groupby("trial_id", sort=True):

    group = group.sort_index()

    if len(group) < WINDOW_SIZE:
        print(
            "Canh bao: trial",
            trial_id,
            "chi co",
            len(group),
            "mau -> bo qua"
        )
        continue

    x = group[FEATURE_COLS].iloc[:WINDOW_SIZE].to_numpy(
        dtype=np.float32
    )

    # Scale giong luc train
    x_scaled = scaler.transform(x)

    x_scaled = x_scaled.astype(np.float32)

    windows.append(x_scaled)


if len(windows) == 0:
    print("LOI: Khong tao duoc window nao")
    sys.exit(1)


windows = np.stack(windows, axis=0)

print("Representative windows:", windows.shape)
print("Dang mong doi          : (so_trial, 50, 12)")


# =========================================================
# 5. REPRESENTATIVE DATASET
# =========================================================

def representative_dataset():

    for i in range(len(windows)):

        sample = windows[i:i + 1]

        yield [
            sample.astype(np.float32)
        ]


# =========================================================
# 6. CONVERT INT8
# =========================================================

print("\n[5/6] Dang quantize INT8...")

converter = tf.lite.TFLiteConverter.from_keras_model(model)

converter.optimizations = [
    tf.lite.Optimize.DEFAULT
]

converter.representative_dataset = representative_dataset

converter.target_spec.supported_ops = [
    tf.lite.OpsSet.TFLITE_BUILTINS_INT8
]

converter.inference_input_type = tf.int8
converter.inference_output_type = tf.int8


try:

    tflite_int8 = converter.convert()

except Exception as e:

    print("\nLOI KHI CONVERT INT8:")
    print(e)

    sys.exit(1)


with open(OUTPUT_FILE, "wb") as f:

    f.write(tflite_int8)


# =========================================================
# 7. KIEM TRA FILE INT8
# =========================================================

print("\n[6/6] Dang kiem tra model INT8...")

interpreter = tf.lite.Interpreter(
    model_path=OUTPUT_FILE
)

interpreter.allocate_tensors()

input_details = interpreter.get_input_details()

output_details = interpreter.get_output_details()


size_bytes = os.path.getsize(OUTPUT_FILE)

size_kb = size_bytes / 1024


float_size_kb = None

if os.path.exists("gesture_model.tflite"):

    float_size_kb = (
        os.path.getsize("gesture_model.tflite") / 1024
    )


print("\n" + "=" * 60)
print("HOAN TAT")
print("=" * 60)


if float_size_kb is not None:

    print(
        "Model FLOAT32 :",
        round(float_size_kb, 2),
        "KB"
    )


print(
    "Model INT8    :",
    round(size_kb, 2),
    "KB"
)


if float_size_kb is not None:

    reduction = (
        1 - size_kb / float_size_kb
    ) * 100

    print(
        "Giam          :",
        round(reduction, 2),
        "%"
    )


print("\nINPUT TFLITE")

print(
    "Shape:",
    input_details[0]["shape"]
)

print(
    "Dtype:",
    input_details[0]["dtype"]
)

print(
    "Quantization:",
    input_details[0]["quantization"]
)


print("\nOUTPUT TFLITE")

print(
    "Shape:",
    output_details[0]["shape"]
)

print(
    "Dtype:",
    output_details[0]["dtype"]
)

print(
    "Quantization:",
    output_details[0]["quantization"]
)


print("\nDa tao file:")

print(
    os.path.abspath(
        OUTPUT_FILE
    )
)


print("\nNeu Input va Output deu la int8 thi da thanh cong.")

print(
    "Buoc tiep theo: "
    "chuyen gesture_model_int8.tflite thanh model_data.h"
)
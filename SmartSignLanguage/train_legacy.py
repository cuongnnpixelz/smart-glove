import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
from sklearn.preprocessing import LabelEncoder

import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import (
    Conv1D,
    MaxPooling1D,
    GlobalAveragePooling1D,
    Dense,
    Dropout,
    BatchNormalization
)
from tensorflow.keras.callbacks import EarlyStopping


# ============================================================
# CẤU HÌNH
# ============================================================

CSV_FILE = "dataset_gesture.csv"

TARGET_LENGTH = 50

FEATURE_COLUMNS = [
    "flex1",
    "flex2",
    "dFlex1",
    "dFlex2",
    "dFlex1Avg",
    "dFlex2Avg",
    "ax",
    "ay",
    "az",
    "gx",
    "gy",
    "gz"
]


# ============================================================
# ĐỌC DATA
# ============================================================

df = pd.read_csv(CSV_FILE)

print("=" * 60)
print("TRAIN 1D-CNN")
print("=" * 60)

print("Tong so dong:", len(df))

print()
print("Labels:")
print(df["label"].value_counts())


# ============================================================
# HÀM RESAMPLE 1 TRIAL VỀ 50 MẪU
# ============================================================

def resample_trial(trial_df, target_length=50):

    data = trial_df[FEATURE_COLUMNS].values.astype(np.float32)

    original_length = len(data)

    if original_length == target_length:
        return data

    old_x = np.linspace(0, 1, original_length)
    new_x = np.linspace(0, 1, target_length)

    resampled = []

    for col in range(data.shape[1]):

        new_col = np.interp(
            new_x,
            old_x,
            data[:, col]
        )

        resampled.append(new_col)

    resampled = np.stack(resampled, axis=1)

    return resampled


# ============================================================
# TẠO X, y THEO TRIAL
# ============================================================

X = []
y = []
trial_ids = []

grouped = df.groupby(["trial_id", "label"])

for (trial_id, label), trial_df in grouped:

    trial_df = trial_df.sort_values("time_ms")

    sample = resample_trial(
        trial_df,
        TARGET_LENGTH
    )

    X.append(sample)
    y.append(label)
    trial_ids.append(trial_id)

X = np.array(X, dtype=np.float32)
y = np.array(y)

print()
print("Shape X:", X.shape)
print("Shape y:", y.shape)

print()
print("Ky vong:")
print(
    f"(so_trial, {TARGET_LENGTH}, {len(FEATURE_COLUMNS)})"
)


# ============================================================
# MÃ HÓA LABEL
# ============================================================

label_encoder = LabelEncoder()

y_encoded = label_encoder.fit_transform(y)

class_names = label_encoder.classes_

print()
print("Classes:")

for i, name in enumerate(class_names):
    print(i, "->", name)


# ============================================================
# CHIA TRAIN / TEST
# Với dataset nhỏ 30 trial:
# 80% train, 20% test
# stratify để các lớp cân bằng
# ============================================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y_encoded,
    test_size=0.2,
    random_state=42,
    stratify=y_encoded
)


# ============================================================
# TÁCH VALIDATION TỪ TRAIN
# ============================================================

X_train, X_val, y_train, y_val = train_test_split(
    X_train,
    y_train,
    test_size=0.25,
    random_state=42,
    stratify=y_train
)

print()
print("Train:", X_train.shape[0])
print("Validation:", X_val.shape[0])
print("Test:", X_test.shape[0])


# ============================================================
# CHUẨN HÓA FEATURE
# ============================================================

num_features = X_train.shape[2]

scaler = StandardScaler()

# Fit scaler chỉ trên TRAIN
X_train_2d = X_train.reshape(-1, num_features)

scaler.fit(X_train_2d)


def scale_dataset(X_data):

    shape = X_data.shape

    X_2d = X_data.reshape(-1, num_features)

    X_scaled = scaler.transform(X_2d)

    return X_scaled.reshape(shape)


X_train = scale_dataset(X_train)
X_val = scale_dataset(X_val)
X_test = scale_dataset(X_test)


# ============================================================
# MODEL 1D-CNN
# ============================================================

model = Sequential([
    Conv1D(
        32,
        kernel_size=5,
        activation="relu",
        input_shape=(
            TARGET_LENGTH,
            num_features
        )
    ),

    BatchNormalization(),

    MaxPooling1D(
        pool_size=2
    ),

    Conv1D(
        64,
        kernel_size=3,
        activation="relu"
    ),

    BatchNormalization(),

    MaxPooling1D(
        pool_size=2
    ),

    Conv1D(
        128,
        kernel_size=3,
        activation="relu"
    ),

    GlobalAveragePooling1D(),

    Dropout(0.3),

    Dense(
        64,
        activation="relu"
    ),

    Dropout(0.3),

    Dense(
        len(class_names),
        activation="softmax"
    )
])


# ============================================================
# COMPILE
# ============================================================

model.compile(
    optimizer="adam",
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"]
)

model.summary()


# ============================================================
# EARLY STOPPING
# ============================================================

early_stop = EarlyStopping(
    monitor="val_loss",
    patience=15,
    restore_best_weights=True
)


# ============================================================
# TRAIN
# ============================================================

history = model.fit(
    X_train,
    y_train,

    validation_data=(
        X_val,
        y_val
    ),

    epochs=100,
    batch_size=4,

    callbacks=[
        early_stop
    ],

    verbose=1
)


# ============================================================
# TEST
# ============================================================

test_loss, test_accuracy = model.evaluate(
    X_test,
    y_test,
    verbose=0
)

print()
print("=" * 60)
print("KET QUA TEST")
print("=" * 60)

print(
    "Test accuracy:",
    round(test_accuracy * 100, 2),
    "%"
)


# ============================================================
# PREDICTION
# ============================================================

pred_prob = model.predict(
    X_test,
    verbose=0
)

y_pred = np.argmax(
    pred_prob,
    axis=1
)


# ============================================================
# IN KẾT QUẢ TEST
# ============================================================

print()
print("Chi tiet du doan:")

for i in range(len(y_test)):

    true_label = class_names[
        y_test[i]
    ]

    predicted_label = class_names[
        y_pred[i]
    ]

    confidence = np.max(
        pred_prob[i]
    ) * 100

    print(
        f"That: {true_label:15s} | "
        f"Du doan: {predicted_label:15s} | "
        f"Confidence: {confidence:.2f}%"
    )


# ============================================================
# CONFUSION MATRIX
# ============================================================

cm = confusion_matrix(
    y_test,
    y_pred
)

disp = ConfusionMatrixDisplay(
    confusion_matrix=cm,
    display_labels=class_names
)

disp.plot()

plt.title(
    "Confusion Matrix"
)

plt.tight_layout()

plt.show()


# ============================================================
# BIỂU ĐỒ ACCURACY
# ============================================================

plt.figure(figsize=(8, 5))

plt.plot(
    history.history["accuracy"],
    label="Train accuracy"
)

plt.plot(
    history.history["val_accuracy"],
    label="Validation accuracy"
)

plt.xlabel("Epoch")
plt.ylabel("Accuracy")

plt.legend()
plt.grid(True)

plt.tight_layout()

plt.show()


# ============================================================
# BIỂU ĐỒ LOSS
# ============================================================

plt.figure(figsize=(8, 5))

plt.plot(
    history.history["loss"],
    label="Train loss"
)

plt.plot(
    history.history["val_loss"],
    label="Validation loss"
)

plt.xlabel("Epoch")
plt.ylabel("Loss")

plt.legend()
plt.grid(True)

plt.tight_layout()

plt.show()


# ============================================================
# LƯU MODEL
# ============================================================

model.save(
    "gesture_model.keras"
)

print()
print(
    "[OK] Da luu model: gesture_model.keras"
)


# ============================================================
# LƯU SCALER
# ============================================================

import joblib

joblib.dump(
    scaler,
    "gesture_scaler.pkl"
)

joblib.dump(
    label_encoder,
    "label_encoder.pkl"
)

print(
    "[OK] Da luu scaler: gesture_scaler.pkl"
)

print(
    "[OK] Da luu label encoder: label_encoder.pkl"
)

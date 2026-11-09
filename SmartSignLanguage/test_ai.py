import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import time
from collections import deque

import joblib
import numpy as np
import serial
import tensorflow as tf

# ============================================================
# CAU HINH
# ============================================================

SERIAL_PORT = "COM3"
BAUD_RATE = 115200

MODEL_FILE = "gesture_model.keras"
SCALER_FILE = "gesture_scaler.pkl"
LABEL_FILE = "label_encoder.pkl"

WINDOW_SIZE = 50
PREDICT_EVERY = 5

CONFIDENCE_THRESHOLD = 0.85
STABLE_PREDICTIONS = 3

# ============================================================
# HAM DOC 1 DONG TU ESP32
# ============================================================

def read_sensor_line(ser):
    try:
        raw = ser.readline()

        if not raw:
            return None

        line = raw.decode("utf-8", errors="ignore").strip()

        if not line:
            return None

        if line.startswith("time_ms"):
            return None

        if "," not in line:
            return None

        parts = line.split(",")

        # ESP32 gui 13 cot:
        # time_ms + 12 features
        if len(parts) != 13:
            return None

        values = [float(x) for x in parts]

        # Bo time_ms, giu 12 features
        features = values[1:]

        return np.array(features, dtype=np.float32)

    except Exception:
        return None


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 55)
    print("TEST AI GANG TAY REALTIME")
    print("=" * 55)

    # --------------------------------------------------------
    # LOAD MODEL
    # --------------------------------------------------------

    try:
        model = tf.keras.models.load_model(MODEL_FILE)
        print("[OK] Load model:", MODEL_FILE)
    except Exception as e:
        print("[LOI] Khong load duoc model")
        print(e)
        return

    # --------------------------------------------------------
    # LOAD SCALER
    # --------------------------------------------------------

    try:
        scaler = joblib.load(SCALER_FILE)
        print("[OK] Load scaler:", SCALER_FILE)
    except Exception as e:
        print("[LOI] Khong load duoc scaler")
        print(e)
        return

    # --------------------------------------------------------
    # LOAD LABEL ENCODER
    # --------------------------------------------------------

    try:
        label_encoder = joblib.load(LABEL_FILE)
        print("[OK] Load label encoder:", LABEL_FILE)
    except Exception as e:
        print("[LOI] Khong load duoc label encoder")
        print(e)
        return

    print("[OK] Classes:", list(label_encoder.classes_))

    # --------------------------------------------------------
    # MO COM
    # --------------------------------------------------------

    try:
        ser = serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            timeout=0.1
        )
        print("[OK] Da mo", SERIAL_PORT)
    except Exception as e:
        print("[LOI] Khong mo duoc", SERIAL_PORT)
        print(e)
        print("Hay dong Serial Monitor Arduino va kiem tra COM.")
        return

    print("Dang cho ESP32 khoi dong...")
    time.sleep(2)
    ser.reset_input_buffer()

    sensor_buffer = deque(maxlen=WINDOW_SIZE)
    prediction_history = deque(maxlen=STABLE_PREDICTIONS)

    sample_counter = 0
    last_confirmed = None

    print()
    print("Dang nap 50 mau dau tien...")
    print("Nhan Ctrl+C de dung.")
    print()

    try:
        while True:
            sample = read_sensor_line(ser)

            if sample is None:
                continue

            sensor_buffer.append(sample)
            sample_counter += 1

            # Chua du 50 mau
            if len(sensor_buffer) < WINDOW_SIZE:
                if len(sensor_buffer) in (10, 20, 30, 40):
                    print(
                        f"Dang nap buffer: "
                        f"{len(sensor_buffer)}/{WINDOW_SIZE}"
                    )
                continue

            # Bao du 50 mau lan dau
            if sample_counter == WINDOW_SIZE:
                print("Dang nap buffer: 50/50")
                print("[OK] Bat dau du doan.")
                print()

            # Chi du doan moi 5 mau
            if sample_counter % PREDICT_EVERY != 0:
                continue

            # ------------------------------------------------
            # TAO WINDOW 50 x 12
            # ------------------------------------------------

            window = np.array(
                sensor_buffer,
                dtype=np.float32
            )

            # ------------------------------------------------
            # SCALE
            # ------------------------------------------------

            window_scaled = scaler.transform(window)

            X = window_scaled.reshape(
                1,
                WINDOW_SIZE,
                12
            )

            # ------------------------------------------------
            # PREDICT
            # ------------------------------------------------

            probabilities = model.predict(
                X,
                verbose=0
            )[0]

            class_index = int(np.argmax(probabilities))
            confidence = float(probabilities[class_index])

            label = label_encoder.inverse_transform(
                [class_index]
            )[0]

            print(
                f"Du doan: {label:15s} | "
                f"{confidence * 100:6.2f}%"
            )

            # ------------------------------------------------
            # LOC CONFIDENCE
            # ------------------------------------------------

            if confidence < CONFIDENCE_THRESHOLD:
                prediction_history.clear()
                continue

            prediction_history.append(label)

            if len(prediction_history) < STABLE_PREDICTIONS:
                continue

            if len(set(prediction_history)) != 1:
                continue

            confirmed = prediction_history[0]

            # NONE = reset de cho phep nhan cu chi moi
            if confirmed == "NONE":
                if last_confirmed is not None:
                    print("----> Trang thai: NONE")

                last_confirmed = None
                continue

            # Chong lap
            if confirmed == last_confirmed:
                continue

            print()
            print("=" * 55)
            print("DA NHAN DIEN:", confirmed)
            print(f"DO TIN CAY: {confidence * 100:.2f}%")
            print("=" * 55)
            print()

            last_confirmed = confirmed

    except KeyboardInterrupt:
        print()
        print("Da dung chuong trinh.")

    finally:
        try:
            ser.close()
        except Exception:
            pass

        print("Da dong COM.")


if __name__ == "__main__":
    main()

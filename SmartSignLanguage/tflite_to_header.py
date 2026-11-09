from pathlib import Path

INPUT_FILE = "gesture_model_dynamic.tflite"
OUTPUT_FILE = "model_data.h"

data = Path(INPUT_FILE).read_bytes()

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:

    f.write("#ifndef MODEL_DATA_H\n")
    f.write("#define MODEL_DATA_H\n\n")

    f.write("const unsigned char model_data[] = {\n")

    for i, b in enumerate(data):

        if i % 12 == 0:
            f.write("  ")

        f.write(f"0x{b:02X}")

        if i != len(data) - 1:
            f.write(", ")

        if i % 12 == 11:
            f.write("\n")

    if len(data) % 12 != 0:
        f.write("\n")

    f.write("};\n\n")

    f.write(
        f"const unsigned int model_data_len = {len(data)};\n\n"
    )

    f.write("#endif\n")

print("DA TAO:", OUTPUT_FILE)
print("KICH THUOC MODEL:", len(data), "bytes")
print("KHOANG:", round(len(data) / 1024, 2), "KB")
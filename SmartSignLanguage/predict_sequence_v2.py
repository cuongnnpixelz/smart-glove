"""Manual five-second tests, using the exact preprocessing of training v2."""
import argparse
import socket
from pathlib import Path

if __package__:
    from .collect_v2 import SampleStream
    from .collect_sequence import countdown
    from .sensor_pipeline import make_imu_reference, SamplingGap
    from .sequence_model_v2 import SequenceModel, DURATION_MS
else:
    from collect_v2 import SampleStream
    from collect_sequence import countdown
    from sensor_pipeline import make_imu_reference, SamplingGap
    from sequence_model_v2 import SequenceModel, DURATION_MS


LCD_LABELS = {
    "TRO_TRAI_DUOI": "XIN_CHAO",
    "GIUA_TRAI_DUOI": "CAM_ON",
    "TRO_PHAI_DUOI": "TAM_BIET",
}


def send_lcd_result(sock, accepted_label):
    """Only the final decision goes to hardware; unknown labels clear old text."""
    message = LCD_LABELS.get(accepted_label, "NONE")
    sock.sendall(f"SEQ,{message}\n".encode("ascii"))
    return message.replace("_", " ")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, help="Default: newest complete sequence_v2 model")
    parser.add_argument("--esp32-host", default="192.168.137.115")
    parser.add_argument("--esp32-port", type=int, default=5000)
    args = parser.parse_args(argv)
    stream = None
    try:
        folder = args.model
        if folder is None:
            folders = [p.parent for p in (Path(__file__).resolve().parent/"models").glob("sequence_v2_*/manifest.json")
                       if (p.parent/"report.json").exists() and (p.parent/"model.joblib").exists()]
            if not folders:
                raise ValueError("Chua co model 5 giay. Thu du lieu moi, chay train_sequence_v2.py truoc")
            folder = max(folders, key=lambda p: (p/"manifest.json").stat().st_mtime_ns)
        model = SequenceModel(folder)
        print(f"MODEL V2: {folder}")
        print("LCD: TRO_TRAI_DUOI=XIN CHAO | GIUA_TRAI_DUOI=CAM ON | TRO_PHAI_DUOI=TAM BIET")
        print("Can nap firmware mophong_wireless.ino co lenh SEQ de hien LCD.")
        if model.motion_checks == "classifier-only":
            print("MODEL THU NGHIEM: SVM hoc theo nhan; chua co kiem tra rieng ngon/thu tu.")
        if model.manifest["evaluation_scope"] != "session_holdout":
            print("MODEL DEMO: chua kiem chung tren phien doc lap")
        stream = SampleStream(socket.create_connection((args.esp32_host, args.esp32_port), timeout=3))
        stream.check_ready()
        input("Duoi hai ngon, dat tay yen. ENTER: lay moc MPU > ")
        countdown()
        print("GIU YEN khoang 4 giay...", flush=True)
        reference = make_imu_reference(stream.capture(2))
        stream.configure_imu(reference)
        stream.capture(2.1)
        print("SAN SANG: khong ghi dataset; khong can bao cao flex tinh.")
        print("Moi trial: 0.5s dau duoi/yen; lam chuoi mot lan; cuoi duoi va giu yen.")
        while True:
            command = input("ENTER: thu 5s | Q: dung > ").strip().upper()
            if command == "Q":
                return 0
            if command:
                continue
            stream.check_ready()
            countdown()
            stream.sock.sendall(b"START\n")
            print("BAT DAU: 0.5s dau yen, roi lam dong tac; thu ca chi nghieng/chi gap/sai huong", flush=True)
            try:
                rows = stream.capture(DURATION_MS/1000)
            finally:
                stream.sock.sendall(b"STOP\n")
            label, candidate, reason = model.predict_details(rows, reference)
            lcd_text = send_lcd_result(stream.sock, label)
            print(f"KET QUA: {label} | GUI LCD: {lcd_text} | SVM: {candidate} | {reason}", flush=True)
    except SamplingGap as exc:
        print(f"TAM DUNG: {exc}. Khong du doan mau thieu; chay lai de lay moc MPU.")
        return 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"LOI: {exc}")
        return 1
    except (KeyboardInterrupt, EOFError):
        return 0
    finally:
        if stream:
            try:
                send_lcd_result(stream.sock, "NONE")
            except OSError:
                pass
            stream.close()


if __name__ == "__main__":
    raise SystemExit(main())

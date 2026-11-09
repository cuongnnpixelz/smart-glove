"""Continuous glove recognition: no Enter prompts, auto rest initialization/reconnect."""
import argparse
from pathlib import Path
import socket
import time

if __package__:
    from .collect_v2 import SampleStream
    from .sensor_pipeline import make_imu_reference, SamplingGap
    from .sequence_model_v2 import SequenceModel
    from .continuous_sequence import ContinuousSegmenter
    from .predict_sequence_v2 import send_lcd_result
else:
    from collect_v2 import SampleStream
    from sensor_pipeline import make_imu_reference, SamplingGap
    from sequence_model_v2 import SequenceModel
    from continuous_sequence import ContinuousSegmenter
    from predict_sequence_v2 import send_lcd_result


def send_state(stream, state):
    if state not in {"CALIBRATING","READY","TRACKING","REST","ERROR","OFF","PING"}:
        raise ValueError("Invalid LCD state")
    stream.sock.sendall(f"RUN,{state}\n".encode("ascii"))


def run_connected(stream, model):
    send_state(stream,"CALIBRATING")
    print("GIU YEN: duoi hai ngon, dat tay yen khoang 4 giay; tu dong lay moc MPU.",flush=True)
    while True:
        raw = stream.capture(2)
        send_state(stream,"PING")
        try:
            reference = make_imu_reference(raw)
            break
        except SamplingGap:
            raise
        except ValueError as exc:
            print(f"CHUA YEN: {exc}; se tu do lai.",flush=True)
    stream.configure_imu(reference)
    stream.capture(2.1)
    detector = ContinuousSegmenter(reference,model.predict_details)
    cursor = stream.enable_runtime_recovery()
    heartbeat = 0
    print("DANG CHAY LIEN TUC. Cho LCD SAN SANG, lam chuoi, duoi/giu yen giua hai lan. Ctrl+C de dung.",flush=True)
    send_state(stream,"REST")
    while True:
        now = time.monotonic()
        if now-heartbeat >= .8:
            send_state(stream,"PING")
            heartbeat = now
        cursor,batch = stream.read_since(cursor,timeout=.5)
        for row in batch:
            if row.get("_runtime_gap_ms"):
                detector = None
                send_state(stream,"REST")
                print(f"PHUC HOI NHANH: gian doan {row['_runtime_gap_ms']} ms; giu TCP, bo chuoi do. Duoi/giu yen khoang 0.8 giay; khong lay lai gyro bias.",flush=True)
            if row.get("_runtime_recovering"):
                continue
            seed = row.get("_runtime_seed")
            if seed is not None:
                detector = ContinuousSegmenter(reference,model.predict_details)
                print("DU LIEU DA ON DINH: tiep tuc tren ket noi cu.",flush=True)
            if detector is None:
                raise ValueError("Missing IMU recovery boundary")
            for sample in (seed if seed is not None else [row]):
                event = detector.push(sample)
                if event is None:
                    continue
                if event["state"] == "RESULT":
                    text = send_lcd_result(stream.sock,event["label"])
                    print(f"KET QUA: {event['label']} | LCD: {text} | SVM: {event['candidate']} | {event['reason']}",flush=True)
                else:
                    send_state(stream,event["state"])
                    print(event["state"],flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esp32-host",default="192.168.137.115")
    parser.add_argument("--esp32-port",type=int,default=5000)
    parser.add_argument("--model",type=Path)
    args = parser.parse_args(argv)
    try:
        folder = args.model
        if folder is None:
            folders = [p.parent for p in (Path(__file__).resolve().parent/"models").glob("sequence_v2_*/manifest.json")
                       if (p.parent/"report.json").exists() and (p.parent/"model.joblib").exists()]
            if not folders:
                raise ValueError("Chua co model; chay train_sequence_v2.py truoc")
            folder = max(folders,key=lambda p:(p/"manifest.json").stat().st_mtime_ns)
        model = SequenceModel(folder)
        print(f"MODEL: {folder}")
        print("Model 5 giay: cua so bat dau theo chuyen dong, khong chia moi 5 giay bat ke dong tac.")
        print("Phat hien chuoi tu dong can kiem tra tren gang that; diem test tung trial khong phai diem nhan dien lien tuc.")
        if model.motion_checks == "classifier-only":
            print("SVM thu nghiem + kiem tra ket thuc/gap-hoi; chua bao dam phan biet moi chuoi sai thu tu.")
    except (OSError,ValueError,KeyError) as exc:
        print(f"LOI MODEL: {exc}")
        return 1
    try:
        while True:
            stream = None
            try:
                stream = SampleStream(socket.create_connection((args.esp32_host,args.esp32_port),timeout=3))
                run_connected(stream,model)
            except (OSError,ValueError) as exc:
                print(f"TAM DUNG: {exc}. Bo chuoi do; tu ket noi lai va lay moc MPU.",flush=True)
                if stream:
                    try:
                        send_state(stream,"ERROR")
                    except OSError:
                        pass
            finally:
                if stream:
                    try:
                        send_state(stream,"OFF")
                    except OSError:
                        pass
                    stream.close()
            time.sleep(2)
    except KeyboardInterrupt:
        print("Da dung nhan dien.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

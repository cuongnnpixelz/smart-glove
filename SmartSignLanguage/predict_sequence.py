"""Manual 3-second prediction on ESP32, using the trained whole-sequence model."""
import argparse
import socket
import json
from pathlib import Path

if __package__:
    from .collect_v2 import SampleStream
    from .collect_sequence import countdown
    from .sensor_pipeline import make_imu_reference, SamplingGap
    from .sequence_model import SequenceModel
    from .sequence_guard import flex_profile, check_open_pose, evaluate
else:
    from collect_v2 import SampleStream
    from collect_sequence import countdown
    from sensor_pipeline import make_imu_reference, SamplingGap
    from sequence_model import SequenceModel
    from sequence_guard import flex_profile, check_open_pose, evaluate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--esp32-host", default="192.168.137.115")
    parser.add_argument("--esp32-port", type=int, default=5000)
    parser.add_argument("--flex-report", type=Path, help="Two-flex diagnostic report; defaults to newest report")
    args = parser.parse_args(argv)
    stream = None
    try:
        model = SequenceModel(args.model)
        print("MODEL: "+", ".join(model.manifest["labels"]))
        guard = json.loads((Path(args.model)/"acceptance_guard.json").read_text(encoding="utf-8"))
        if guard.get("schema") != "two-flex-sequence-guard-v1" or guard.get("model_sha256") != model.manifest["model_sha256"]:
            raise ValueError("Acceptance guard/model mismatch")
        report_path = args.flex_report
        if report_path is None:
            reports = list((Path(__file__).resolve().parent/"diagnostics").glob("*/flex_check.json"))
            if not reports:
                raise ValueError("Chay check_flex.py de kiem tra ca hai flex truoc")
            report_path = max(reports, key=lambda p: p.stat().st_mtime_ns)
        print(f"KIEM TRA HAI FLEX: {report_path}")
        profile = flex_profile(json.loads(report_path.read_text(encoding="utf-8")))
        if model.manifest["evaluation_scope"] != "session_holdout":
            print("MODEL DEMO: chua duoc kiem chung tren phien doc lap.")
        stream = SampleStream(socket.create_connection((args.esp32_host, args.esp32_port), timeout=3))
        stream.check_ready()
        input("Duoi CA HAI ngon, dat tay yen tren ban; ENTER de lay moc MPU > ")
        countdown()
        print("GIU YEN khoang 4 giay...", flush=True)
        rest = stream.capture(2)
        check_open_pose(rest, profile)
        reference = make_imu_reference(rest)
        stream.configure_imu(reference)
        stream.capture(2.1)
        print("SAN SANG. Thu nay chi du doan, KHONG ghi vao dataset.")
        while True:
            command = input("ENTER: kiem tra mot chuoi 3 giay | Q: dung > ").strip().upper()
            if command == "Q":
                return 0
            if command:
                continue
            stream.check_ready()
            countdown()
            stream.sock.sendall(b"START\n")
            print("BAT DAU: thuc hien chuoi HOAC nghi/chuyen dong khac de thu NONE", flush=True)
            try:
                rows = stream.capture(3)
            finally:
                stream.sock.sendall(b"STOP\n")
            candidate = model.predict(rows, reference)
            if candidate == "NONE":
                print("KET QUA: NONE", flush=True)
            elif candidate != guard["label"]:
                print("KET QUA: CHUA_XAC_DINH (nhan chua co kiem tra chuoi)", flush=True)
            else:
                accepted, reason = evaluate(rows, profile, guard["direction"])
                print("KET QUA: "+(candidate if accepted else "NONE")+" | "+reason, flush=True)
    except SamplingGap as exc:
        print(f"TAM DUNG: {exc}. Khong du doan doan thieu; chay lai de lay moc MPU.")
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(f"LOI: {exc}")
        return 1
    except (KeyboardInterrupt, EOFError):
        return 0
    finally:
        if stream:
            stream.close()


if __name__ == "__main__":
    raise SystemExit(main())

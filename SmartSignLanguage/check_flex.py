"""Guided raw flex check; no training, IMU reference or dataset changes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import uuid

import numpy as np

if __package__:
    from .collect_v2 import SampleStream
    from .sensor_pipeline import timing_report
else:
    from collect_v2 import SampleStream
    from sensor_pipeline import timing_report

CHANNELS = ("flex_1", "flex_2")
POSES = (
    ("open_before", "Duoi hai ngon, giu co tay yen"),
    ("index_bent", "Gap RIENG ngon TRO, giu ngon GIUA duoi va co tay yen"),
    ("open_after_index", "Duoi lai ca hai ngon, giu co tay yen"),
    ("middle_bent", "Gap RIENG ngon GIUA, giu ngon TRO duoi va co tay yen"),
    ("open_after_middle", "Duoi lai ca hai ngon, giu co tay yen"),
)


def summarize(rows):
    quality = timing_report(rows)
    if quality["duration_ms"] < 1600:
        raise ValueError("Can it nhat 1.6 giay cho moi tu the")
    result = {}
    for channel in CHANNELS:
        values = np.asarray([r[channel] for r in rows], dtype=float)
        if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 4095):
            raise ValueError("ADC khong hop le")
        lo, hi = np.percentile(values, [5, 95])
        result[channel] = {"median": float(np.median(values)), "p05": float(lo),
                           "p95": float(hi), "spread": float(hi-lo),
                           "local_step_adc": float(np.median(np.abs(np.diff(values)))),
                           "drift_adc": float(np.median(values[len(values)//2:])-np.median(values[:len(values)//2]))}
    return result


def analyze(poses):
    stats = {name: summarize(poses[name]) for name, _ in POSES}
    responses = {}
    mapping = {}
    for finger, before, bent, after in (
            ("Index", "open_before", "index_bent", "open_after_index"),
            ("Middle", "open_after_index", "middle_bent", "open_after_middle")):
        channels = {}
        candidates = []
        for channel in CHANNELS:
            a, b, c = (stats[p][channel] for p in (before, bent, after))
            delta = b["median"]-a["median"]
            noise = max(a["spread"], b["spread"], c["spread"])
            # Separate response, drift and return. Slow settling must not be
            # called absence of flex response or inflate the return allowance.
            jitter = max(a["local_step_adc"], b["local_step_adc"], c["local_step_adc"])
            minimum = max(15., 3*jitter)
            separation = max(b["p05"]-a["p95"], a["p05"]-b["p95"])
            clear = abs(delta) >= minimum and separation >= max(5., 3*jitter)
            tolerance = min(.25*abs(delta), max(5., 2*jitter, .2*abs(delta)))
            recovered = abs(c["median"]-a["median"]) <= tolerance
            drift = max(abs(s["drift_adc"]) for s in (a,b,c))
            drift_tolerance = max(5., 3*jitter, .15*abs(delta))
            channels[channel] = {
                "open_adc": a["median"], "bent_adc": b["median"], "reopened_adc": c["median"],
                "delta_adc": delta, "noise_spread_adc": noise,
                "minimum_change_adc": minimum, "clear_response": bool(clear),
                "separation_adc": separation, "local_step_adc": jitter,
                "pose_drift_adc": drift, "pose_drift_tolerance_adc": drift_tolerance,
                "stable_during_poses": bool(drift <= drift_tolerance),
                "return_error_adc": abs(c["median"]-a["median"]),
                "recovery_tolerance_adc": tolerance, "returned_at_check": bool(recovered),
            }
            # Identify the moving finger independently of return quality.
            if clear:
                candidates.append(channel)
        responses[finger] = channels
        if len(candidates) == 1:
            mapping[finger] = candidates[0]
    distinguishable = len(mapping) == 2 and len(set(mapping.values())) == 2
    readiness = {}
    if distinguishable:
        for finger, channel in mapping.items():
            own = responses[finger][channel]
            other_poses = (("open_after_index", "middle_bent", "open_after_middle")
                           if finger == "Index" else ("open_before", "index_bent", "open_after_index"))
            inactive = [stats[p][channel] for p in other_poses]
            drift = max(r["median"] for r in inactive)-min(r["median"] for r in inactive)
            tolerance = max(15., 3*max(r["local_step_adc"] for r in inactive), .2*abs(own["delta_adc"]))
            stable = drift <= tolerance
            readiness[finger] = {"channel": channel, "returned_at_check": own["returned_at_check"],
                                 "stable_during_poses": own["stable_during_poses"],
                                 "stable_when_other_finger_moves": bool(stable),
                                 "inactive_drift_adc": drift, "inactive_tolerance_adc": tolerance,
                                 "usable_in_this_check": bool(own["returned_at_check"] and stable and own["stable_during_poses"])}
    ready = distinguishable and all(r["usable_in_this_check"] for r in readiness.values())
    return {"schema": "flex-check-v3", "poses": stats, "responses": responses,
            "suggested_mapping": mapping if distinguishable else {},
            "two_fingers_distinguishable": distinguishable,
            "finger_readiness": readiness, "ready_for_two_finger_demo": ready,
            "limitations": "One static check only. Screening thresholds are heuristics, not a hardware fault diagnosis or a gesture accuracy score. Return is measured at the prompted pose, not a recovery time."}


def print_report(report):
    print("\nKET QUA KIEM TRA:")
    for finger, responses in report["responses"].items():
        print("Ngon "+("TRO" if finger == "Index" else "GIUA"))
        for ch, result in responses.items():
            print(f"  {ch}: duoi {result['open_adc']:.1f} -> gap {result['bent_adc']:.1f} -> duoi lai {result['reopened_adc']:.1f}; "
                  f"phan ung gap={'CO' if result['clear_response'] else 'CHUA'}; "
                  f"ve gan moc={'CO' if result['returned_at_check'] else 'CHUA'} "
                  f"(lech {result['return_error_adc']:.1f} ADC)")
    if not report["two_fingers_distinguishable"]:
        print("CHUA XAC DINH RO KENH CUA TUNG NGON. Kiem tra tu the, cach gan va day/mach.")
        return
    print("DA XAC DINH KENH: "+str(report["suggested_mapping"]))
    for finger, state in report["finger_readiness"].items():
        print(f"{finger} ({state['channel']}): "
              f"hoi ve={'CO' if state['returned_at_check'] else 'CHUA'}; "
              f"on dinh khi giu={'CO' if state['stable_during_poses'] else 'CHUA'}; "
              f"on dinh khi ngon khac cu dong={'CO' if state['stable_when_other_finger_moves'] else 'CHUA'} "
              f"(lech {state['inactive_drift_adc']:.1f} ADC)")
    if report["ready_for_two_finger_demo"]:
        print("HAI KENH DAT KIEM TRA LAN NAY. Can lap lai de kiem chung; chua phai do chinh xac nhan dien.")
    else:
        print("DA BIET DUNG KENH, NHUNG HOI VE/DO ON DINH CHUA DAT. Chua ket luan cam bien hong.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esp32-host", default="192.168.137.115")
    parser.add_argument("--esp32-port", type=int, default=5000)
    parser.add_argument("--report", type=Path, help="Reanalyze saved raw poses; no ESP32 connection or file changes")
    args = parser.parse_args(argv)
    stream = None
    try:
        if args.report:
            saved = json.loads(args.report.read_text(encoding="utf-8"))
            print_report(analyze(saved["raw_poses"]))
            return 0
        stream = SampleStream(socket.create_connection((args.esp32_host, args.esp32_port), timeout=3))
        stream.check_ready()
        print("KIEM TRA 5 TU THE. Giu co tay yen; chua thu chuoi cu chi.")
        print("Lam tu the truoc, dung tay con lai nhan Enter, giu yen 2 giay.")
        poses = {}
        for i, (name, instruction) in enumerate(POSES, 1):
            command = input(f"\nBUOC {i}/5: {instruction}. ENTER: do | Q: dung > ").strip().upper()
            if command == "Q":
                return 0
            print("DANG DO: GIU NGUYEN TU THE 2 GIAY...", flush=True)
            rows = stream.capture(2)
            poses[name] = rows
            stats = summarize(rows)
            print(" | ".join(f"{ch}: {stats[ch]['median']:.1f} ADC (dao dong {stats[ch]['spread']:.1f})" for ch in CHANNELS))
        report = analyze(poses)
        folder = Path(__file__).resolve().parent/"diagnostics"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8])
        folder.mkdir(parents=True, exist_ok=False)
        report["raw_poses"] = poses
        path = folder/"flex_check.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print_report(report)
        print(f"BAO CAO: {path}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"CHUA HOAN TAT KIEM TRA: {exc}. Chua the ket luan ve flex.")
        return 1
    except (KeyboardInterrupt, EOFError):
        return 0
    finally:
        if stream:
            stream.close()


if __name__ == "__main__":
    raise SystemExit(main())

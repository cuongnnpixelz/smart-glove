"""Five physical flex channels; RAW5 wire format and versioned CSV metadata."""
import math
import numpy as np

if __package__:
    from .sensor_pipeline import CSV_COLUMNS as OLD_COLUMNS, timing_report
else:
    from sensor_pipeline import CSV_COLUMNS as OLD_COLUMNS, timing_report

FLEX_COLUMNS = tuple(f"flex_{i}" for i in range(1, 6))
FLEX_PINS = [32, 33, 34, 35, 36]
FINGERS = ["thumb", "index", "middle", "ring", "little"]
RAW_COLUMNS = (*FLEX_COLUMNS, "ACCx", "ACCy", "ACCz", "GYRx", "GYRy", "GYRz")
CSV_COLUMNS = (*OLD_COLUMNS[:5], *FLEX_COLUMNS, *OLD_COLUMNS[7:])
SAMPLE_MS = 10
DURATION_MS = 1500
SAMPLE_COUNT = 150
LEGACY_CALIBRATION_SCHEMA = "five-flex-10k-calibration-v1"
CALIBRATION_SCHEMA = "five-flex-10k-calibration-v2"


def quality_report(rows):
    return timing_report(rows, sample_ms=SAMPLE_MS, max_gap_ms=20)


def trial_quality(rows):
    quality = quality_report(rows)
    # 150 readings at t=0..1490 ms describe a nominal 1.5-second record.
    if len(rows) != SAMPLE_COUNT or not 1490 <= quality["duration_ms"] <= 1510:
        raise ValueError("Can 150 mau that, 100 Hz (khoang timestamp 1490..1510 ms); thu lai trial")
    values = np.asarray([[r[k] for k in RAW_COLUMNS] for r in rows], dtype=float)
    invalid = np.argwhere(~np.isfinite(values))
    if len(invalid):
        sample, column = invalid[0]
        raise ValueError(f"Du lieu khong huu han: {RAW_COLUMNS[column]}={values[sample, column]}, mau {sample+1}")
    bad_flex = (values[:, :5] <= 8) | (values[:, :5] >= 4087)
    if np.any(bad_flex):
        details = []
        for i in range(5):
            indices = np.flatnonzero(bad_flex[:, i])
            if len(indices):
                first = int(indices[0])
                details.append(f"F{i+1} ({FINGERS[i]}, GPIO {FLEX_PINS[i]}): "
                               f"min={values[:, i].min():g}, max={values[:, i].max():g}, "
                               f"{len(indices)}/{len(rows)} mau loi; "
                               f"mau {first+1}, ADC={values[first, i]:g}, timestamp={rows[first]['timestamp']}")
        raise ValueError("Flex ADC sat bien (<=8 hoac >=4087): " + " | ".join(details))
    if np.any(np.abs(values[:, 5:8]) >= 19.5) or np.any(np.abs(values[:, 8:11]) >= 4.34):
        raise ValueError("MPU gan cham gioi han +/-2g hoac +/-250 do/s; lam cu chi nhe hon va thu lai")
    return quality


def calibration_issue(entry):
    """Screen measured pose separation, not a fixed span/noise ratio.

    These are practical screening thresholds, not an accuracy guarantee.
    Keep acquisition and training validation on the same acceptance rule.
    """
    span = entry["open"]-entry["closed"]
    separation = entry["open_p05"]-entry["closed_p95"]
    drift = max(abs(entry["open_drift"]), abs(entry["closed_drift"]))
    if span < 15:
        return f"bien do {span:.1f} ADC < 15; chua thay doi du hoac sai chieu"
    if separation < 5:
        return f"khoang duoi/gap con chong lan hoac qua gan (cach {separation:.1f} ADC, can >=5)"
    if drift > max(5, .2*span):
        return f"ADC con troi {drift:.1f} khi giu tu the; giu yen va cho cam bien on dinh"
    return None


def make_finger_calibration(open_rows, closed_rows, key):
    if key not in FLEX_COLUMNS:
        raise ValueError("Unknown flex channel")
    for rows in (open_rows, closed_rows):
        if quality_report(rows)["duration_ms"] < 1600:
            raise ValueError("Giu moi tu the hieu chuan it nhat 1.6 giay")
    finger = FINGERS[FLEX_COLUMNS.index(key)]
    opened = np.asarray([r[key] for r in open_rows], dtype=float)
    closed = np.asarray([r[key] for r in closed_rows], dtype=float)
    both = np.concatenate((opened, closed))
    if not np.isfinite(both).all() or np.min(both) <= 8 or np.max(both) >= 4087:
        raise ValueError(f"{key} ({finger}): ADC sat bien/loi; kiem tra day va mach chia ap")
    a, b = float(np.median(opened)), float(np.median(closed))
    entry = {"open": a, "closed": b}
    for name, values in (("open", opened), ("closed", closed)):
        lo, hi = np.percentile(values, [5, 95])
        quarter = max(1, len(values)//4)
        entry[name+"_p05"] = float(lo)
        entry[name+"_p95"] = float(hi)
        entry[name+"_drift"] = float(np.median(values[-quarter:])-np.median(values[:quarter]))
    entry["noise_p90"] = max(entry["open_p95"]-entry["open_p05"],
                             entry["closed_p95"]-entry["closed_p05"])
    issue = calibration_issue(entry)
    if issue:
        raise ValueError(f"{key} ({finger}): duoi={a:.0f}, gap={b:.0f}, "
                         f"bien do={a-b:.1f}, dao dong P90={entry['noise_p90']:.1f}. {issue}")
    return entry


def make_flex_calibration(open_rows, closed_rows):
    return {key: make_finger_calibration(open_rows, closed_rows, key) for key in FLEX_COLUMNS}


def validate_reference(reference):
    validate_mapping(reference)
    if (reference.get("sample_ms") != SAMPLE_MS or reference.get("trial_seconds") != 1.5
            or reference.get("flex_calibration_schema") not in (CALIBRATION_SCHEMA, LEGACY_CALIBRATION_SCHEMA)
            or reference.get("divider_ohms") != 10000 or reference.get("supply_volts") != 3.3
            or reference.get("divider_topology") != "3V3-flex-ADC-10k-GND"):
        raise ValueError("Can phien 100 Hz/1.5s, hieu chuan 5 flex voi 10k xuong GND; khong tron phien cu")
    calibration = reference.get("flex_calibration", {})
    for key in FLEX_COLUMNS:
        entry = calibration.get(key, {})
        values = [entry.get(k, float("nan")) for k in ("open", "closed", "noise_p90")]
        a, b, noise = values
        if (not all(math.isfinite(v) for v in values) or not 8 < b < a < 4087 or noise < 0):
            raise ValueError(f"{key}: moc hieu chuan khong hop le")
        if reference["flex_calibration_schema"] == LEGACY_CALIBRATION_SCHEMA:
            if a-b < max(60, 6*noise):
                raise ValueError(f"{key}: moc hieu chuan cu khong hop le")
            continue
        for pose in ("open", "closed"):
            lo, hi, drift = [entry.get(pose+suffix, float("nan")) for suffix in ("_p05", "_p95", "_drift")]
            if (not all(math.isfinite(v) for v in (lo, hi, drift))
                    or not 8 < lo <= entry[pose] <= hi < 4087):
                raise ValueError(f"{key}: thieu/loi thong ke hieu chuan")
        measured_noise = max(entry["open_p95"]-entry["open_p05"], entry["closed_p95"]-entry["closed_p05"])
        if not math.isclose(noise, measured_noise, abs_tol=1e-6) or calibration_issue(entry):
            raise ValueError(f"{key}: moc hieu chuan chua tach biet/on dinh")
    return reference


def raw5_error_detail(line):
    """Bounded diagnostics only; never try to repair or silently drop a bad packet."""
    if isinstance(line, bytes):
        try:
            text = line.decode('ascii')
        except UnicodeDecodeError:
            return f"co byte khong phai ASCII; goi={line[:220]!r}"
    else:
        text = line
    fields = text.strip().split(',')
    reasons = []
    if len(fields) != 13:
        reasons.append(f"co {len(fields)} truong, can 13")
    else:
        if not fields[1].isascii() or not fields[1].isdigit() or int(fields[1]) > 0xFFFFFFFF:
            reasons.append(f"timestamp khong hop le: {fields[1]!r}")
        for i, (key, value) in enumerate(zip(RAW_COLUMNS, fields[2:])):
            try:
                number = float(value)
                if not math.isfinite(number) or (i < 5 and not 0 <= number <= 4095):
                    reasons.append(f"{key} ngoai mien: {value!r}")
            except ValueError:
                reasons.append(f"{key} khong phai so: {value!r}")
    return '; '.join(reasons or ['khong dung giao thuc']) + f"; goi={text[:220]!r}"


def parse_raw5(line, protocol="RAW5"):
    if isinstance(line, bytes):
        try:
            line = line.decode("ascii")
        except UnicodeDecodeError:
            return None
    if len(line) > 2048:
        return None
    parts = line.strip().split(",")
    if len(parts) != 13 or parts[0] != protocol:
        return None
    try:
        if not parts[1].isascii() or not parts[1].isdigit():
            return None
        stamp = int(parts[1])
        values = tuple(float(v) for v in parts[2:])
    except (ValueError, OverflowError):
        return None
    if (not 0 <= stamp <= 0xFFFFFFFF or not all(math.isfinite(v) for v in values)
            or not all(0 <= v <= 4095 for v in values[:5])):
        return None
    return stamp, dict(zip(RAW_COLUMNS, values))


def validate_mapping(reference):
    if (reference.get("flex_pins") != FLEX_PINS or reference.get("fingers") != FINGERS
            or reference.get("csv_columns") != list(CSV_COLUMNS)):
        raise ValueError("Can du lieu 5 ngon dung thu tu GPIO 32,33,34,35,36; khong tron du lieu 2 ngon")

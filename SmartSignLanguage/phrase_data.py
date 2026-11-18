"""Acquisition format for whole phrases, separate from 1.5-second models.

Each label has a fixed duration within one session. CSV rows remain the original
26-column sensor format; acquisition never pads, interpolates, or truncates data
to make an incomplete trial pass validation.
"""
from copy import deepcopy
import math

import numpy as np

if __package__:
    from .five_finger import (
        FINGERS, FLEX_PINS, RAW_COLUMNS, SAMPLE_MS, quality_report,
        validate_reference as validate_flex_reference, check_imu_range,
    )
else:
    from five_finger import (
        FINGERS, FLEX_PINS, RAW_COLUMNS, SAMPLE_MS, quality_report,
        validate_reference as validate_flex_reference, check_imu_range,
    )

PROTOCOL = "phrase-five-flex-100hz-v1"
MIN_SECONDS = 1.0
MAX_SECONDS = 10.0


def validate_duration(value):
    """Accept 1..10 seconds, exactly representable as 100 Hz samples."""
    message = "Thoi gian thu phai tu 1 den 10 giay, theo buoc 0.01 giay (100 Hz)"
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(message) from exc
    if isinstance(value, bool) or not math.isfinite(seconds) or not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise ValueError(message)
    count = seconds * (1000 / SAMPLE_MS)
    if not math.isclose(count, round(count), rel_tol=0, abs_tol=1e-7):
        raise ValueError(message)
    return round(count) * SAMPLE_MS / 1000


def sample_count(seconds):
    return round(validate_duration(seconds) * (1000 / SAMPLE_MS))


def phrase_quality(rows, seconds, reference=None):
    """Check all real readings, including dropouts and sensor saturation."""
    seconds = validate_duration(seconds)
    count = sample_count(seconds)
    quality = quality_report(rows)
    # Same acquisition tolerance as the 150-sample collector: n real samples
    # normally span (n-1)*10 ms, with at most 20 ms accumulated scheduling delay.
    minimum_ms = (count - 1) * SAMPLE_MS
    maximum_ms = minimum_ms + 20
    if len(rows) != count or not minimum_ms <= quality["duration_ms"] <= maximum_ms:
        raise ValueError(
            f"Can {count} mau that cho {seconds:g} giay, 100 Hz "
            f"(khoang timestamp {minimum_ms}..{maximum_ms} ms); thu lai luot"
        )
    try:
        values = np.asarray([[row[key] for key in RAW_COLUMNS] for row in rows], dtype=float)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Mau cau thieu/loi du lieu 5 flex hoac MPU") from exc
    invalid = np.argwhere(~np.isfinite(values))
    if len(invalid):
        sample, column = invalid[0]
        raise ValueError(
            f"Du lieu khong huu han: {RAW_COLUMNS[column]}={values[sample, column]}, mau {sample+1}"
        )
    bad_flex = (values[:, :5] <= 8) | (values[:, :5] >= 4087)
    if np.any(bad_flex):
        details = []
        for index in range(5):
            invalid_indices = np.flatnonzero(bad_flex[:, index])
            if len(invalid_indices):
                first = int(invalid_indices[0])
                details.append(
                    f"F{index+1} ({FINGERS[index]}, GPIO {FLEX_PINS[index]}): "
                    f"min={values[:, index].min():g}, max={values[:, index].max():g}, "
                    f"{len(invalid_indices)}/{len(rows)} mau loi; "
                    f"mau {first+1}, ADC={values[first, index]:g}, timestamp={rows[first]['timestamp']}"
                )
        raise ValueError("Flex ADC sat bien (<=8 hoac >=4087): " + " | ".join(details))
    check_imu_range(values, reference)
    return quality


def make_phrase_reference(reference):
    """Copy an accepted calibration, without claiming a global trial duration."""
    validate_flex_reference(reference)
    result = deepcopy(reference)
    result.update(
        data_kind="phrase",
        collection_protocol=PROTOCOL,
        trial_seconds=None,
        sample_count=None,
        label_settings={},
    )
    return result


def validate_phrase_reference(reference):
    """Reuse physical calibration checks while keeping phrase metadata distinct."""
    if (reference.get("data_kind") != "phrase" or reference.get("collection_protocol") != PROTOCOL
            or "trial_seconds" not in reference or reference["trial_seconds"] is not None
            or "sample_count" not in reference or reference["sample_count"] is not None
            or not isinstance(reference.get("label_settings"), dict)):
        raise ValueError("Can moc hieu chuan danh rieng cho cau, voi thoi gian theo tung nhan")
    physical_reference = deepcopy(reference)
    physical_reference.update(trial_seconds=1.5, sample_count=150)
    validate_flex_reference(physical_reference)
    for label, settings in reference["label_settings"].items():
        if not isinstance(label, str) or not label or not isinstance(settings, dict):
            raise ValueError("Cai dat nhan cau khong hop le")
        duration = validate_duration(settings.get("seconds"))
        if (settings.get("sample_count") != sample_count(duration)
                or not isinstance(settings.get("display_text"), str)
                or not settings["display_text"].strip()):
            raise ValueError(f"{label}: thoi gian/so mau/noi dung cau khong hop le")
    return reference

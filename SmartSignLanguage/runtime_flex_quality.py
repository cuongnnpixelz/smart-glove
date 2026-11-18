"""Runtime screening consistent with the model's existing five-sample median.

Training collection remains strict. Raw samples are never replaced or saved as
repaired observations; SequenceModel applies its usual preprocessing itself.
"""
import numpy as np

from .five_finger import FLEX_COLUMNS, trial_quality


def recognition_quality(rows, reference=None):
    # Never hide missing samples, ADC rails, nonfinite values, or IMU clipping.
    quality = trial_quality(rows, reference)
    values = np.asarray([[row[key] for key in FLEX_COLUMNS] for row in rows], dtype=float)
    median = np.asarray([
        np.median(values[max(0, i-2):min(len(values), i+3)], axis=0)
        for i in range(len(values))
    ])
    spikes = np.abs(values - median) > 400
    # Runtime policy: in-range flex jumps/offsets are diagnostic only.
    # Do not reset words or alter calibration. The model still median-filters
    # flex itself; collection_quality remains strict when collecting data.
    return {**quality, "flex_spike_samples": np.argwhere(spikes).tolist()}

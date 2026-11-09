"""Train-only motion checks for the bend -> tilt -> return -> release demo.

Allow residual flex displacement at the end. These are demo acceptance rules,
not proof of physical finger position and not a substitute for negative trials.
"""
import numpy as np

if __package__:
    from .sequence_model_v2 import GRID, FEATURES
    from .sequence_guard import rotation_vectors, _run_start
else:
    from sequence_model_v2 import GRID, FEATURES
    from sequence_guard import rotation_vectors, _run_start


def matrix(vector):
    x = np.asarray(vector).reshape(len(GRID), len(FEATURES))
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite sequence")
    return x


def learn_profiles(trials):
    """Only pass training trials. No test or diagnostic file contributes limits."""
    profiles = {}
    labels = sorted({t["label"] for t in trials}-{"NONE"})
    for label in labels:
        selected = [t for t in trials if t["label"] == label]
        arrays = [matrix(t["vector"]) for t in selected]
        if len(arrays) < 3:
            raise ValueError(f"{label}: can it nhat 3 trial TRAIN")
        axes, angles, amplitudes, recoveries, signs = [], [], [], [], []
        for x in arrays:
            flex = x[:, :2]
            signed_peak = flex[np.abs(flex).argmax(axis=0), np.arange(2)]
            signs.append(np.sign(signed_peak))
            amplitudes.append(np.abs(signed_peak))
            recoveries.append(np.abs(signed_peak)-np.sign(signed_peak)*np.median(flex[-13:], axis=0))
            rotation = rotation_vectors(x[:, 2:6])
            magnitude = np.linalg.norm(rotation, axis=1)
            peak = int(magnitude.argmax())
            angles.append(magnitude[peak])
            axes.append(rotation[peak]/max(magnitude[peak], 1e-12))
        signs = np.asarray(signs)
        sign = np.sign(np.median(signs, axis=0))
        if np.any(sign == 0):
            raise ValueError(f"{label}: chua co bien thien gap ro cua CA HAI flex; xem lai trial")
        if np.any(np.mean(signs == sign, axis=0) < .8):
            raise ValueError(f"{label}: chieu gap hai flex khong nhat quan; xem lai trial/gan cam bien")
        if np.any(np.percentile(amplitudes, 10, axis=0) < 15) or np.any(np.percentile(recoveries, 10, axis=0) < 5):
            raise ValueError(f"{label}: nhieu trial chua co bien thien gap VA hoi cua CA HAI flex; thu lai mau do")
        axis = np.mean(axes, axis=0)
        norm = np.linalg.norm(axis)
        if norm < .8 or min(angles) < np.deg2rad(15):
            raise ValueError(f"{label}: huong nghieng chua nhat quan/qua nho")
        axis /= norm
        if np.min(np.asarray(axes)@axis) < np.cos(np.deg2rad(40)):
            raise ValueError(f"{label}: can cung mot huong nghieng cho nhan nay")
        profile = {
            "sign": sign.tolist(),
            "min_bend_adc": np.maximum(15, .4*np.percentile(amplitudes, 10, axis=0)).tolist(),
            "min_release_adc": np.maximum(5, .35*np.percentile(recoveries, 10, axis=0)).tolist(),
            "axis": axis.tolist(), "angle_rad": float(np.median(angles)),
            "training_keys": [t["key"] for t in selected],
        }
        failures = [t["key"] for t in selected if not evaluate(t["vector"], profile)[0]]
        if len(failures) > .2*len(selected):
            raise ValueError(f"{label}: {len(failures)}/{len(selected)} trial TRAIN chua ro thu tu/gap/hoi; kiem tra {failures[:5]}")
        profile["training_rejected_keys"] = failures
        profiles[label] = profile
    return profiles


def evaluate(vector, profile):
    x = matrix(vector)
    flex = x[:, :2]*np.asarray(profile["sign"])
    noise = np.ptp(np.percentile(flex[GRID < 500], [5, 95], axis=0), axis=0)
    threshold = np.maximum(profile["min_bend_adc"], 3*noise)
    bent = _run_start(np.all(flex >= threshold, axis=1), GRID)
    if bent is None:
        return False, "Chua thay CA HAI flex gap ro vuot nhieu dau trial"
    rotation = rotation_vectors(x[:, 2:6])
    magnitude = np.linalg.norm(rotation, axis=1)
    axis = np.asarray(profile["axis"])
    target = profile["angle_rad"]
    alignment = rotation@axis/np.maximum(magnitude, 1e-12)
    peak = int(magnitude.argmax())
    if alignment[peak] < np.cos(np.deg2rad(40)):
        return False, "Nghieng sai huong da thu"
    onset = np.flatnonzero(magnitude >= .35*target)
    reached = _run_start((magnitude >= .65*target) & (alignment >= np.cos(np.deg2rad(40))), GRID)
    if reached is None:
        return False, "Chua nghieng du"
    if len(onset) and GRID[onset[0]] < GRID[bent]+120:
        return False, "Can gap CA HAI ngon truoc khi nghieng"
    returned = _run_start(magnitude <= .25*target, GRID, after=peak)
    if returned is None:
        return False, "Co tay chua ve giua"
    if np.any(flex[bent:returned+1] < .5*threshold):
        return False, "Tha ngon qua som truoc khi co tay ve giua"
    # Require a measured release after wrist return, not exact original ADC.
    at_return = np.median(flex[max(bent,returned-3):returned+1], axis=0)
    end = np.median(flex[-13:], axis=0)
    reversal = at_return-end
    if np.any(reversal < np.asarray(profile["min_release_adc"])):
        return False, "Chua thay hai flex hoi sau khi co tay ve; khong bat buoc ve dung ADC cu"
    return True, "Hai flex gap/hoi + MPU dung huong/thu tu; cho phep ADC cuoi con lech"

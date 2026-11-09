"""One CSV per label inside a calibrated session; legacy samples.csv remains readable."""
import csv
from pathlib import Path
import re
import hashlib
import shutil
import json


def organize_session(folder):
    """Move label files into numbered takes; preserve reference bytes and session IDs."""
    folder = Path(folder)
    reference = folder/'imu_reference.json'
    if not reference.exists():
        return []
    destinations = []
    for source in sorted(folder.glob('*.csv')):
        if source.name == 'samples.csv':
            raise ValueError('Split legacy samples.csv before organizing')
        label = source.stem.upper()
        if label_filename(label) != source.name:
            raise ValueError(f'Invalid label file: {source}')
        with source.open(encoding='utf-8', newline='') as file:
            if any(row['label'] != label for row in csv.DictReader(file)):
                raise ValueError(f'Mixed labels: {source}')
        parent = folder.parent/label
        parent.mkdir(exist_ok=True)
        number = 1
        while (parent/f'Lan_{number:02d}').exists():
            number += 1
        target = parent/f'Lan_{number:02d}'
        target.mkdir()
        shutil.copy2(reference, target/reference.name)
        for log in folder.glob('*.jsonl'):
            shutil.copy2(log, target/log.name)
        shutil.move(str(source), str(target/source.name))
        destinations.append(target)
    if destinations:
        # The reference has been copied byte-for-byte beside every label file.
        for item in list(folder.iterdir()):
            if item.name == 'imu_reference.json' or item.suffix == '.jsonl':
                item.unlink()
        if not any(folder.iterdir()):
            folder.rmdir()
    return destinations


def label_filename(label):
    if not re.fullmatch(r'[A-Z0-9_]{1,48}', label) or label in {'CON', 'PRN', 'AUX', 'NUL'} or re.fullmatch(r'(COM|LPT)[1-9]', label):
        raise ValueError('Nhan khong hop le de dat ten file CSV')
    return label.lower()+'.csv'


def session_csv_groups(root, per_label=False):
    root = Path(root)
    folders = {p.parent for p in root.rglob('samples.csv')}
    if per_label:
        folders.update(p.parent for p in root.rglob('imu_reference.json'))
    grouped = {}
    for folder in sorted(folders):
        paths = sorted(folder.glob('*.csv')) if per_label else [folder/'samples.csv']
        if not paths:
            continue
        if len(paths) > 1 and any(p.name == 'samples.csv' for p in paths):
            raise ValueError(f'{folder}: co ca samples.csv va CSV theo nhan; tranh dem trung du lieu')
        if per_label and re.fullmatch(r'Lan_\d+', folder.name):
            reference = (folder/'imu_reference.json').read_bytes()
            sid = json.loads(reference)['session_id']
            key = (str(folder.parent.parent.resolve()), sid)
            if key in grouped:
                old_reference, old_paths = grouped[key]
                if reference != old_reference:
                    raise ValueError(f'{folder}: conflicting calibration for session {sid}')
                old_paths.extend(paths)
            else:
                grouped[key] = (reference, list(paths))
        else:
            yield paths
    for _, paths in grouped.values():
        names = [p.name for p in paths]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate label files in the same session')
        yield sorted(paths)


def read_session(paths, columns):
    combined = []
    for path in paths:
        with path.open(encoding='utf-8', newline='') as file:
            reader = csv.DictReader(file)
            rows = list(reader)
            if not rows:
                continue
            if reader.fieldnames != list(columns):
                raise ValueError(f'{path}: wrong CSV schema; raw-only trials cannot be mixed')
        last_stamp, last_trial = -1, 0
        for row in rows:
            if path.name != 'samples.csv' and label_filename(row['label']) != path.name:
                raise ValueError(f'{path}: nhan trong dong khong khop ten file')
            stamp, trial = float(row['timestamp']), float(row['trial_id'])
            if stamp <= last_stamp or trial < last_trial:
                raise ValueError(f'{path}: timestamp/trial reset or duplicate')
            last_stamp, last_trial = stamp, trial
        combined.extend(rows)
    # File order is alphabetical, acquisition order need not be.
    if len(paths) > 1:
        combined.sort(key=lambda row: float(row['timestamp']))
    return combined


def split_legacy_session(folder, backup_root):
    """Split only after backing up; compare every field before removing the old CSV."""
    folder = Path(folder).resolve()
    original = folder/'samples.csv'
    with original.open(encoding='utf-8', newline='') as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        columns = reader.fieldnames
    if not rows:
        return []
    grouped = {}
    for row in rows:
        grouped.setdefault(label_filename(row['label']), []).append(row)
    if any((folder/name).exists() for name in grouped):
        raise FileExistsError('CSV theo nhan da ton tai; khong ghi de')
    backup = Path(backup_root).resolve()/folder.name/'samples.csv'
    if folder == backup.parent or folder in backup.parents:
        raise ValueError('Backup must be outside the active session')
    backup.parent.mkdir(parents=True, exist_ok=True)
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    if not backup.exists():
        shutil.copy2(original, backup)
    if hashlib.sha256(backup.read_bytes()).hexdigest() != original_hash:
        raise ValueError('Backup differs from original; refusing conversion')
    created = []
    try:
        for name, label_rows in grouped.items():
            target = folder/name
            with target.open('x', encoding='utf-8', newline='') as file:
                created.append(target)
                writer = csv.DictWriter(file, fieldnames=columns)
                writer.writeheader()
                writer.writerows(label_rows)
        if read_session(created, columns) != rows:
            raise ValueError('Split CSV does not preserve every original row')
        original.unlink()
    except BaseException:
        for path in created:
            path.unlink()
        raise
    return created

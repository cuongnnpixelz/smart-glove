"""Build a source-linked sequence corpus; never cut or relabel source CSVs."""
import argparse
from collections import Counter
import json
from pathlib import Path

from SmartSignLanguage import phrase_model, sequence_model_5
from SmartSignLanguage.train_sequence import load_trials

BASE = Path(__file__).resolve().parent
# Gesture order explicitly confirmed by the signer, not inferred from Vietnamese.
PHRASES = {
    'TOI_CAM_ON_BAN': ['TOI', 'CAM_ON', 'BAN'],
    'BAN_KHOE_KHONG': ['BAN', 'KHOE'],
    'TOI_KHOE': ['TOI', 'KHOE'],
    'NONE': [],
}
WORDS = {label: [label] for label in ('TOI', 'CAM_ON', 'BAN', 'KHOE', 'CHAO')}
WORDS['NONE'] = []


def prepare():
    records, sources, excluded, skipped = [], [], Counter(), []
    for kind, root, backend, mapping in (
        ('continuous', BASE / 'phrase_data_5_100hz', phrase_model, PHRASES),
        ('isolated', BASE / 'sequence_data_5_100hz' / 'U4', sequence_model_5, WORDS),
    ):
        trials, origin, empty = load_trials(root, backend)
        sources.extend(origin)
        skipped.extend(empty)
        for trial in trials:
            label = trial['label']
            if label not in mapping:
                excluded[f'{kind}:{label}'] += 1
                continue
            records.append({k: trial[k] for k in ('key', 'session', 'user', 'label', 'quality')} |
                           {'kind': kind, 'tokens': mapping[label]})
    keys = [r['key'] for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate trial keys across sources')
    return {
        'schema': 'word-sequence-source-manifest-v1',
        'status': 'prepared_not_trained',
        'annotation_basis': 'signer-confirmed gesture order; no word timestamps inferred',
        'notes': [
            'Read original CSV rows by session and trial_id; retain original calibration.',
            'Source users remain unchanged; phrase recordings are not relabeled U4.',
            'NONE has an empty token sequence; it is not a word or a CTC alignment.',
            'No equal-duration cuts, resampling, synthetic joins, or train/test split.',
            'Split by acquisition session before fitting preprocessing or models.',
            'Gesture completeness and boundary alignment are not verified by numeric checks.',
        ],
        'mapping': PHRASES,
        'counts': dict(Counter(f"{r['kind']}:{r['label']}" for r in records)),
        'excluded_counts': dict(excluded), 'empty_sources': skipped,
        'sources': sources, 'trials': records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = prepare()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(json.dumps({'counts': result['counts'], 'excluded': result['excluded_counts'],
                      'trials': len(result['trials']), 'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()

"""Export the saved 14-word ExtraTrees without retraining or pruning.

Pure leaves make each tree an exact class vote. Thresholds are rounded DOWN
to float32 so comparisons on sklearn's float32 inputs keep identical branches.
"""
import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT.parent / 'SmartSignLanguage/models/sequence_5_100hz_U4_U5_U6_14words_extra_trees_20261117_all'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, default=DEFAULT)
    args = parser.parse_args()
    manifest = json.loads((args.model / 'manifest.json').read_text(encoding='utf-8'))
    source = args.model / 'model.joblib'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest == manifest['model_sha256']
    model = joblib.load(source)
    assert model.n_features_in_ == 2850 and len(model.classes_) == 15
    assert list(model.classes_) == manifest['labels']
    assert 'DIEN_THOAI' not in model.classes_
    total = sum(e.tree_.node_count for e in model.estimators_)
    assert total == 47966 and len(model.estimators_) == 300, 'Update model.h and verify before exporting another forest'
    entries, roots = [], []
    for estimator in model.estimators_:
        tree = estimator.tree_
        offset = len(entries)
        roots.append(offset)
        for i in range(tree.node_count):
            if tree.children_left[i] < 0:
                values = tree.value[i, 0]
                assert np.count_nonzero(values) == 1, 'Mixed leaf needs probability export'
                entries.append((0.0, 65535, int(np.argmax(values)), 0))
            else:
                threshold = np.float32(tree.threshold[i])
                if float(threshold) > tree.threshold[i]:
                    threshold = np.nextafter(threshold, np.float32(-np.inf))
                entries.append((float(threshold), int(tree.feature[i]),
                                offset + int(tree.children_left[i]), offset + int(tree.children_right[i])))
    firmware = ROOT / 'firmware'
    firmware.mkdir(parents=True, exist_ok=True)
    names = ', '.join(json.dumps(str(label)) for label in model.classes_)
    source_text = '#include "model.h"\nnamespace GloveModel {\n'
    source_text += f'const char* const LABELS[CLASS_COUNT] = {{{names}}};\n'
    source_text += 'const uint16_t ROOTS[TREE_COUNT] = {' + ','.join(map(str, roots)) + '};\n'
    source_text += 'const Node NODES[NODE_COUNT] = {\n'
    for threshold, feature, left, right in entries:
        literal = format(threshold, '.9g')
        if '.' not in literal and 'e' not in literal:
            literal += '.0'
        source_text += f'{{{literal}f,{feature},{left},{right}}},\n'
    source_text += '};\n}\n'
    (firmware / 'model_data.cpp').write_text(source_text, encoding='utf-8')
    metadata = dict(source_model=str(args.model.resolve()), model_sha256=digest,
                    trees=len(roots), nodes=total, classes=list(map(str, model.classes_)),
                    features=2850, node_bytes=12, model_table_bytes=total * 12 + len(roots) * 2,
                    conversion='pure leaf votes, float32 downward thresholds; no retraining',
                    evaluation_scope=manifest['evaluation_scope'])
    (ROOT / 'model_info.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()

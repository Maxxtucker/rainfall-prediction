#!/usr/bin/env python3
"""Explicitly package saved sensitivity forests for prediction; never fit models.

Only metadata, empirical_support and stations inside each new candidate are
replaced. Original models, forest pipelines and recorded evaluation stay intact.
"""
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from analyze_rf_sensitivity import load_results, read_document


def document_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def candidate_metadata(original, supports, result):
    """Copy prediction requirements, not the original model's evaluation claims."""
    if (original['seed'] != result['seed']
            or original['counts']['train_sample'] != result['counts']['train15']
            or original['counts']['validation'] != result['counts']['validation']
            or set(original['thresholds_evaluated']) != {m['threshold'] for m in result['threshold_metrics']}
            or sum(item['n'] for item in supports) != original['counts']['train_full']):
        raise ValueError('Original model does not match the sensitivity experiment')
    fields = ('schema_version', 'feature_mode', 'amount_edges', 'thresholds_evaluated',
              'numeric_features', 'categorical_features', 'max_bins', 'requires_recent_rainfall',
              'latency_minutes', 'rainfall_rounding_mm', 'train_max_y30', 'purge')
    metadata = {key: original[key] for key in fields if key in original}
    metadata.update({
        'model': 'RandomForestClassifier + training empirical within-bin survival; uncalibrated (T=1)',
        'depth': result['depth'], 'num_trees': result['trees'], 'seed': result['seed'],
        'min_instances_per_node': result['min_instances_per_node'],
        'feature_subset_strategy': result['feature_subset_strategy'],
        'subsampling_rate': result['subsampling_rate'],
        'train_fraction': result['fraction'], 'temperature': 1.0,
        'test_evaluation_completed': False, 'calibration_completed': False,
        'split_years': {'train': [2017, 2021], 'validation': [2022, 2022]},
        'counts': {'train_sample': result['counts']['train30' if result['fraction'] == .30 else 'train15'],
                   'train_full': original['counts']['train_full'], 'validation': result['counts']['validation']},
        'empirical_bin_counts': [item['n'] for item in supports],
        'sensitivity_result': result, 'supported_predictors': ['random_forest'],
        'original_model_provenance': {'mode': result['mode'],
                                     'metadata_sha256': document_hash(original),
                                     'empirical_support_sha256': document_hash(supports)},
        'empirical_support_source': 'empirical_support',
        'purpose': 'Validation-only RF sensitivity candidate; not a new final-tested model',
        'limitations': ['Within-bin rainfall shape is global, not conditional on current weather.',
                       'Probabilities beyond the largest training total are zero due to finite support.',
                       'This candidate has no separate calibration fit or final-test evaluation.'],
    })
    return metadata


def prepare_models(root, original_root):
    results = load_results(root)
    plans = []
    for result in results:
        if result['reuse']:
            continue
        original = original_root / result['mode']
        dest = root / result['mode'] / result['name']
        if not (dest / 'pipeline').is_dir():
            raise FileNotFoundError(dest / 'pipeline')
        if not (original / 'stations').is_dir():
            raise FileNotFoundError(original / 'stations')
        source = read_document(original / 'metadata')
        supports = read_document(original / 'empirical_support')
        metadata = candidate_metadata(source, supports, result)
        for name in ('metadata', 'empirical_support', 'stations'):
            if (dest / name).is_symlink() or ((dest / name).exists() and not (dest / name).is_dir()):
                raise ValueError(f'Expected a regular model directory: {dest / name}')
        plans.append((original, dest, metadata, supports))
    # Validate every candidate before changing any package. Stage complete copies
    # before replacing helper directories, so old Spark part files cannot linger.
    for original, dest, metadata, supports in plans:
        with tempfile.TemporaryDirectory(prefix='.prepare-', dir=dest) as temporary:
            staging = Path(temporary)
            shutil.copytree(original / 'stations', staging / 'stations')
            for name, value in (('metadata', metadata), ('empirical_support', supports)):
                directory = staging / name
                directory.mkdir()
                (directory / 'part-00000').write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
                (directory / '_SUCCESS').touch()
            for name in ('empirical_support', 'stations', 'metadata'):
                destination = dest / name
                backup = staging / ('old-' + name)
                if destination.exists():
                    destination.rename(backup)
                try:
                    (staging / name).rename(destination)
                except OSError:
                    if backup.exists():
                        backup.rename(destination)
                    raise
    return len(plans)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True, help='Downloaded sensitivity experiment root')
    parser.add_argument('--original-models', type=Path, required=True,
                        help='Original model root containing short_term/ and/or calendar/')
    args = parser.parse_args()
    count = prepare_models(args.results, args.original_models)
    print(f'Prepared {count} saved RF candidates; no training or evaluation performed.')


if __name__ == '__main__':
    main()

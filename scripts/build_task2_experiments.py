#!/usr/bin/env python3
"""Format the unified model and training-fraction comparisons from saved facts."""
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / 'report/task2/experiments_facts.json'
MODES = (('short_term', 'A'), ('calendar', 'B'))
MODELS = (
    ('random_forest', 'Random forest'),
    ('binary_logistic', 'Logistic regression'),
    ('gbt', 'GBT'),
)


def latex_rows(rows):
    return '\n'.join(row + r' \\' for row in rows)


def record_index(facts):
    records = {}
    for row in facts['summary']:
        key = (row['mode'], row['model'], row['fraction'])
        if key in records:
            raise ValueError(f'Duplicate model/fraction result: {key}')
        if not math.isfinite(row['mean_brier']):
            raise ValueError(f'Nonfinite Brier score: {key}')
        records[key] = row
    return records


def build_values(facts=None):
    """Return report placeholders; a missing experiment stays a missing cell."""
    if facts is None:
        facts = json.loads(FACTS.read_text())
    records = record_index(facts)
    comparison, sampling, complete, interior = [], [], [], []
    for mode, label in MODES:
        # Use the initial RF/LR models and the largest GBT fit in the overview.
        for model, name, fraction in (
            ('random_forest', 'Random forest', .15),
            ('binary_logistic', 'Logistic regression', .15),
            ('gbt', 'GBT', 1.),
            ('climatology', 'Historical frequency', 1.),
        ):
            row = records[mode, model, fraction]
            comparison.append(
                f"{label} & {name} & {100 * fraction:g}\\% & {row['mean_brier']:.5f}"
                f" & {row['pr_auc_1mm']:.4f} & {row['log_loss_1mm']:.4f}"
            )
        for model, name in MODELS:
            first, last = (records[mode, model, fraction] for fraction in (.15, 1.))
            cells = []
            for fraction in (.15, .3, 1.):
                row = records.get((mode, model, fraction))
                cells.append(f"{row['mean_brier']:.8f}" if row else '---')
                if row:
                    precision_recall = ('---' if row['pr_auc_1mm'] is None
                                        else f"{row['pr_auc_1mm']:.4f}")
                    complete.append(
                        f"{label} & {name} & {100 * fraction:g}\\%"
                        f" & {row['mean_brier']:.8f} & {row['mean_log_loss']:.6f}"
                        f" & {precision_recall}"
                    )
            improvement = 100 * (1 - last['mean_brier'] / first['mean_brier'])
            sampling.append(f'{label} & {name} & ' + ' & '.join(cells) + f' & {improvement:+.3f}')
        baseline = records[mode, 'climatology', 1.]
        complete.append(
            f"{label} & Historical frequency & 100\\% & {baseline['mean_brier']:.8f}"
            f" & {baseline['mean_log_loss']:.6f} & {baseline['pr_auc_1mm']:.4f}"
        )
        for row in facts['interior_thresholds']:
            if row['mode'] == mode and row['fraction'] == 1.:
                interior.append(
                    f"{label} & {row['threshold']:g} & {row['random_forest_brier']:.6f}"
                    f" & {row['gbt_brier']:.6f} & {row['random_forest_pr_auc']:.4f}"
                    f" & {row['gbt_pr_auc']:.4f}"
                )

    gains = {}
    for mode, label in MODES:
        for model, _ in MODELS:
            first, last = (records[mode, model, fraction]['mean_brier'] for fraction in (.15, 1.))
            gains[label, model] = 100 * (1 - last / first)
    interpretation = (
        "Using all eligible training examples changes mean Brier only slightly. "
        f"For RF, the 100\\% score is {abs(gains['A', 'random_forest']):.3f}\\% higher in A "
        f"and {abs(gains['B', 'random_forest']):.3f}\\% higher in B than at 15\\%. "
        f"The corresponding changes for logistic regression are "
        f"{abs(gains['A', 'binary_logistic']):.3f}\\% and {abs(gains['B', 'binary_logistic']):.3f}\\%. "
        f"GBT's mean Brier falls by approximately {gains['A', 'gbt']:.3f}\\% in A "
        f"and {gains['B', 'gbt']:.3f}\\% in B. A's 30\\% GBT score is slightly higher "
        "than its 15\\% score, so the observed learning curve is not monotonic. "
        "At both 15\\% and 100\\%, where all three classifiers have results, RF has "
        "lower mean Brier than LR and GBT in both information settings."
    )
    order = {(row['mode'], row['fraction']): 100 * row['violation_fraction']
             for row in facts['threshold_order']}
    threshold_order = (
        "Across the ten evaluated thresholds, the proportion of adjacent query pairs "
        "with increasing GBT probability is "
        f"{order['short_term', .3]:.4f}\\% at 30\\% training and "
        f"{order['short_term', 1.]:.4f}\\% at 100\\% for A, compared with "
        f"{order['calendar', .3]:.4f}\\% and {order['calendar', 1.]:.4f}\\% for B."
    )
    return {
        'MODEL_COMPARISON_ROWS': latex_rows(comparison),
        'SAMPLING_ROWS': latex_rows(sampling),
        'SAMPLING_INTERPRETATION': interpretation,
        'INTERIOR_ROWS': latex_rows(interior),
        'EXPERIMENT_METRIC_ROWS': latex_rows(complete),
        'THRESHOLD_ORDER_TEXT': threshold_order,
    }


if __name__ == '__main__':
    print(json.dumps(build_values(), indent=2))

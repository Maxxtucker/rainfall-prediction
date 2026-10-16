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
    """Return report placeholders for the complete common-year comparison grid."""
    if facts is None:
        facts = json.loads(FACTS.read_text())
    records = record_index(facts)
    required = {(mode, model, fraction) for mode, _ in MODES
                for model, _ in MODELS for fraction in (.15, .3, 1.)}
    if required - records.keys():
        raise ValueError('Complete 2024 comparison grid required; missing classifier cells')
    comparison, sampling, complete, interior = [], [], [], []
    for mode, label in MODES:
        # Hold training fraction fixed at 100% in the algorithm overview.
        for model, name, fraction in (
            ('random_forest', 'Random forest', 1.),
            ('binary_logistic', 'Logistic regression', 1.),
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
            if row['mode'] == mode and row['fraction'] == .3:
                interior.append(
                    f"{label} & {row['threshold']:g} & {row['random_forest_brier']:.6f}"
                    f" & {row['binary_logistic_brier']:.6f} & {row['gbt_brier']:.6f}"
                )

    gains = {}
    for mode, label in MODES:
        for model, _ in MODELS:
            first, last = (records[mode, model, fraction]['mean_brier'] for fraction in (.15, 1.))
            gains[label, model] = 100 * (1 - last / first)
    interpretation = (
        f"For RF, the 100\\% score is {abs(gains['A', 'random_forest']):.3f}\\% higher in A "
        f"and {abs(gains['B', 'random_forest']):.3f}\\% higher in B than at 15\\%. "
        "LR also changes little, while GBT improves slightly at full training. "
        "A's 30\\% GBT score is worse than its 15\\% score, so the observed learning "
        "curve is not monotonic. The model ordering is unchanged: RF has lower "
        "mean Brier than LR and GBT at every fitting fraction in both settings."
    )
    rf = records['short_term', 'random_forest', 1.]
    lr = records['short_term', 'binary_logistic', 1.]
    gbt = records['short_term', 'gbt', 1.]
    algorithm_comparison = (
        "The ranking metrics explain why model choice depends on the objective. "
        "In A, GBT has slightly higher PR-AUC at 1 mm "
        f"({gbt['pr_auc_1mm']:.4f} versus {rf['pr_auc_1mm']:.4f}), but higher mean "
        "probability squared error. LR has higher ROC-AUC at 1 mm "
        f"({lr['roc_auc_1mm']:.4f} versus {rf['roc_auc_1mm']:.4f}), "
        "while RF has better PR-AUC, Brier and log loss. Ranking events and assigning "
        "accurate probabilities therefore describe different aspects of performance."
    )
    forest_temperatures = [records[mode, 'random_forest', fraction]['temperature']
                           for mode, _ in MODES for fraction in (.15, .3, 1.)]
    if set(forest_temperatures) == {1.}:
        rf_temperature_text = ("Temperature selection chooses $T=1$ for all three fractions "
                               "in both settings on the 2023 calibration set.")
    else:
        settings = [f"{label}: " + ", ".join(
            f"{fraction*100:g}\\% uses $T={records[mode, 'random_forest', fraction]['temperature']:g}$"
            for fraction in (.15,.3,1.)) for mode,label in MODES]
        rf_temperature_text = "Selected temperatures are " + "; ".join(settings) + "."
    risk = {(row['mode'], row['model'], row['threshold']):row
            for row in facts['matched_threshold_risk']}
    a, b = risk['short_term','gbt',20.], risk['calendar','gbt',20.]
    tail_text = (
        "At the matched 30\\% fitting fraction, GBT's mean predicted risk above 20 mm is "
        f"{100*a['mean_probability']:.3f}\\% in A and {100*b['mean_probability']:.3f}\\% in B, "
        f"compared with observed frequencies of {100*a['event_rate']:.3f}\\% and "
        f"{100*b['event_rate']:.3f}\\%. This overprediction helps explain why event ranking "
        "and probability error can favour different models."
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
        'ALGORITHM_COMPARISON_TEXT': algorithm_comparison,
        'RF_TEMPERATURE_TEXT': rf_temperature_text,
        'MATCHED_TAIL_RISK_TEXT': tail_text,
        'SAMPLING_ROWS': latex_rows(sampling),
        'SAMPLING_INTERPRETATION': interpretation,
        'INTERIOR_ROWS': latex_rows(interior),
        'EXPERIMENT_METRIC_ROWS': latex_rows(complete),
        'THRESHOLD_ORDER_TEXT': threshold_order,
    }


if __name__ == '__main__':
    print(json.dumps(build_values(), indent=2))

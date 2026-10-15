#!/usr/bin/env python3
"""Assemble the canonical report from editable prose and saved numerical evidence."""
import json
from pathlib import Path

import pandas as pd

from build_rf_sensitivity_report import build_section
from build_teammate_report import build_section as build_teammate_section


ROOT = Path(__file__).resolve().parents[1]
MODES = (('short_term', 'A'), ('calendar', 'B'))


def latex_rows(lines):
    return '\n'.join(line + r' \\' for line in lines)


def split_table(models):
    periods = (
        ('train_full', '2017--2021 (full)', 'Empirical supports and baseline'),
        ('train_sample', '2017--2021 (15\\%)', 'RF and binary fitting'),
        ('validation', '2022', 'Model and cutoff selection'),
        ('calibration', '2023', 'RF temperature selection'),
        ('test', '2024', 'Final held-out evaluation'),
    )
    short_term_counts = models['short_term']['counts']
    calendar_counts = models['calendar']['counts']
    return latex_rows(
        f'{period} & {short_term_counts[key]:,} & {calendar_counts[key]:,} & {purpose}'
        for key, period, purpose in periods
    )


def comparison_values(facts):
    """Format the forest comparison on identical test examples."""
    common = pd.DataFrame(facts['common_threshold_results'])
    brier = common.pivot(index='threshold', columns='model', values='brier')
    relative_reduction = 100 * (1 - brier['short_term'] / brier['calendar'])
    table = []
    for threshold in brier.index:
        threshold_rows = common[common['threshold'] == threshold]
        short_term = threshold_rows[threshold_rows['model'] == 'short_term'].iloc[0]
        calendar = threshold_rows[threshold_rows['model'] == 'calendar'].iloc[0]
        table.append(
            f"{threshold:g} & {100 * short_term['prevalence']:.3f}"
            f" & {short_term['brier']:.5f} & {calendar['brier']:.5f}"
            f" & {short_term['pr_auc']:.4f} & {calendar['pr_auc']:.4f}"
        )

    comparison = facts['comparison']
    interval_low, interval_high = facts['bootstrap']['macro_relative_reduction_95']
    return {
        'COMMON_ROWS': latex_rows(table),
        'COMMON_N': f"{comparison['counts']['common']:,}",
        'COVERAGE': f"{100 * comparison['short_term_coverage_of_calendar_test']:.1f}",
        'MACRO_A': f"{facts['common_macro_brier']['short_term']:.5f}",
        'MACRO_B': f"{facts['common_macro_brier']['calendar']:.5f}",
        'REDUCTION': f"{100 * facts['common_relative_reduction']:.1f}",
        'CI_LOW': f'{100 * interval_low:.1f}',
        'CI_HIGH': f'{100 * interval_high:.1f}',
        'SKILL_ZERO': f'{relative_reduction.loc[0]:.1f}',
        'SKILL_TWENTY': f'{relative_reduction.loc[20]:.1f}',
    }


def baseline_values(facts, results_root):
    """Keep each baseline on its own mode's eligible test population."""
    model_names = (
        ('random_forest', 'Random forest'),
        ('binary_logistic', 'Binary LR'),
        ('climatology', 'Historical frequency'),
    )
    values = {}
    table = []
    for mode, label in MODES:
        metrics_directory = results_root / 'models' / mode / 'metrics/test_metrics'
        metrics = pd.concat(
            [pd.read_csv(path) for path in metrics_directory.glob('part-*.csv')]
        )
        threshold_metrics = metrics[
            (metrics['threshold'] == 1) & (metrics['cutoff_kind'] == 'default_0.5')
        ]
        for model, name in model_names:
            metric = threshold_metrics[threshold_metrics['model'] == model].iloc[0]
            mean_brier = facts['models'][mode]['macro_brier'][model]
            table.append(
                f"{label} & {name} & {mean_brier:.5f}"
                f" & {metric['pr_auc']:.4f} & {metric['log_loss']:.4f}"
            )
            if mode == 'short_term' and model == 'random_forest':
                values['RF_ROC'] = f"{metric['roc_auc']:.4f}"
            elif mode == 'short_term' and model == 'binary_logistic':
                values['LR_ROC'] = f"{metric['roc_auc']:.4f}"

    values['BASELINE_ROWS'] = latex_rows(table)
    return values


def render_task2(facts, results_root):
    models = facts['models']
    calibration = next(
        record for record in models['short_term']['calibration']
        if record['threshold'] == 1 and record['model'] == 'random_forest'
    )
    values = {
        'SPLIT_ROWS': split_table(models),
        'B_TEST_N': f"{models['calendar']['counts']['test']:,}",
        'MAX_TRAIN': f"{models['short_term']['max_training_amount']:.1f}",
        'A_MEAN_P': f"{100 * calibration['mean_probability']:.2f}",
        'A_EVENT': f"{100 * calibration['event_rate']:.2f}",
        'A_ECE': f"{100 * calibration['ece_10bin']:.3f}",
    }
    values.update(comparison_values(facts))
    values.update(baseline_values(facts, results_root))

    section = (ROOT / 'report/task2/section_template.tex').read_text()
    for key, value in values.items():
        section = section.replace('@@' + key + '@@', value)
    if '@@' in section:
        raise ValueError('Unfilled Task 2 placeholder')
    return section


def assemble_report(task2, sensitivity):
    sections = {'TASK2': task2, 'RF_SENSITIVITY': sensitivity, 'TEAMMATE': build_teammate_section()}
    for name in ('introduction', 'data', 'weather', 'discussion', 'appendix'):
        sections[name.upper()] = (ROOT / 'report/sections' / (name + '.tex')).read_text()

    report = (ROOT / 'report/project_report.template.tex').read_text()
    for key, section in sections.items():
        marker = '@@' + key + '@@'
        if report.count(marker) != 1:
            raise ValueError('Expected exactly one report insertion point: ' + marker)
        report = report.replace(marker, section)
    if '@@' in report:
        raise ValueError('Unfilled combined-report placeholder')
    return report


def main():
    facts = json.loads((ROOT / 'report/task2/analysis_facts.json').read_text())
    sensitivity = build_section()
    task2 = render_task2(facts, ROOT / 'outputs/steps/task2-dual-v2')
    report = assemble_report(task2, sensitivity)

    (ROOT / 'report/task2/section.tex').write_text(task2)
    (ROOT / 'report/task2/rf_sensitivity.tex').write_text(sensitivity)
    (ROOT / 'report/task2/teammate.tex').write_text(build_teammate_section())
    target = ROOT / 'report/project_report.tex'
    target.write_text(report)
    print(target)


if __name__ == '__main__':
    main()

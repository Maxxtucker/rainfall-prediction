#!/usr/bin/env python3
"""Assemble the canonical report from editable prose and saved numerical evidence."""
import json
from pathlib import Path

import pandas as pd

from build_rf_sensitivity_report import build_section
from build_task2_experiments import build_values as experiment_values


ROOT = Path(__file__).resolve().parents[1]
MODES = (('short_term', 'A'), ('calendar', 'B'))


def latex_rows(lines):
    return '\n'.join(line + r' \\' for line in lines)


def split_table(models):
    periods = (
        ('train_full', '2017--2021', 'Training population'),
        ('validation', '2022', 'Model and cutoff selection'),
        ('calibration', '2023', 'RF and GBT temperature selection'),
        ('test', '2024', 'Model evaluation'),
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


def ranking_values(results_root):
    """Retain the original 1 mm ROC comparison alongside the new model table."""
    metrics_directory = results_root / 'models/short_term/metrics/test_metrics'
    metrics = pd.concat([pd.read_csv(path) for path in sorted(metrics_directory.glob('part-*.csv'))])
    metrics = metrics[(metrics['threshold'] == 1) & (metrics['cutoff_kind'] == 'default_0.5')]
    return {
        key: f"{metrics.loc[metrics['model'] == model, 'roc_auc'].iloc[0]:.4f}"
        for key, model in [('RF_ROC', 'random_forest'), ('LR_ROC', 'binary_logistic')]
    }


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
    values.update(ranking_values(results_root))
    values.update(experiment_values())

    section = (ROOT / 'report/task2/section_template.tex').read_text()
    for key, value in values.items():
        section = section.replace('@@' + key + '@@', value)
    if '@@' in section:
        raise ValueError('Unfilled Task 2 placeholder')
    return section


def assemble_report(task2, sensitivity):
    sections = {'TASK2': task2}
    for name in ('introduction', 'data', 'weather', 'discussion', 'appendix'):
        sections[name.upper()] = (ROOT / 'report/sections' / (name + '.tex')).read_text()
    for key, value in experiment_values().items():
        sections['APPENDIX'] = sections['APPENDIX'].replace('@@' + key + '@@', value)

    sections['APPENDIX'] = sections['APPENDIX'].replace('@@RF_SENSITIVITY@@', sensitivity)

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
    target = ROOT / 'report/project_report.tex'
    target.write_text(report)
    print(target)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Plot training-fraction effects and threshold risk from recorded evaluations."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

from build_task2_experiments import FACTS, MODES, ROOT, record_index


THRESHOLDS = [0., .2, 1., 2., 5., 10., 20.]
COLOURS = {'random_forest': '#087F8C', 'binary_logistic': '#7754A3', 'gbt': '#CE684F'}


def save_figure(figure, output, name):
    for extension in ('pdf', 'png'):
        figure.savefig(output / f'{name}.{extension}', dpi=220, bbox_inches='tight', pad_inches=.05)
    plt.close(figure)


def plot_sampling(facts, output):
    records = record_index(facts)
    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.25), sharey=True)
    settings = [
        ('random_forest', 'Random forest', 'o', -1.5),
        ('binary_logistic', 'Logistic regression', 's', 0),
        ('gbt', 'GBT', '^', 1.5),
    ]
    improvements = [100 * (1 - row['mean_brier'] / records[mode, model, .15]['mean_brier'])
                    for (mode, model, fraction), row in records.items()
                    if model in COLOURS and fraction in (.15, .3, 1.)]
    limits = (min(-.075, min(improvements) - .015), max(.105, max(improvements) + .015))
    for axis, (mode, label) in zip(axes, MODES):
        axis.axhline(0, color='#8B989F', linewidth=.8)
        for model, name, marker, offset in settings:
            reference = records[mode, model, .15]['mean_brier']
            for fraction in (.15, .3, 1.):
                row = records[mode, model, fraction]
                improvement = 100 * (1 - row['mean_brier'] / reference)
                hollow = mode == 'short_term' and model == 'gbt' and fraction == .15
                axis.scatter(100 * fraction + offset, improvement, marker=marker, s=35,
                             facecolors='white' if hollow else COLOURS[model],
                             edgecolors=COLOURS[model], linewidths=1.1, zorder=3,
                             label=name if fraction == .15 else None)
        axis.set(title=f'{label}: ' + ('recent rainfall' if mode == 'short_term' else 'calendar only'),
                 xlabel='Training sample (%)', xticks=[15, 30, 100], xlim=(7, 108),
                 ylim=limits)
        axis.grid(axis='y', alpha=.75)
    axes[0].set_ylabel('Brier improvement over 15% (%)')
    axes[0].set_yticks([-.05, 0, .05, .10])
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:+.2f}' if value else '0'))
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc='lower center', ncol=3, frameon=False,
                  bbox_to_anchor=(.53, -.01), fontsize=8)
    figure.subplots_adjust(left=.12, right=.99, top=.89, bottom=.26, wspace=.15)
    save_figure(figure, output, '22_training_fraction')


def threshold_risk(directory, model):
    """Combine reliability bins using their observation counts as weights."""
    paths = sorted(directory.glob('part-*.csv'))
    if not paths:
        raise ValueError(f'Missing reliability table: {directory}')
    bins = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)
    bins = bins[(bins.model == model) & bins.threshold.isin(THRESHOLDS)].copy()
    if bins.duplicated(['threshold', 'bin']).any():
        raise ValueError(f'Duplicate reliability bins: {directory}')
    bins['predicted_sum'] = bins.n * bins.mean_probability
    bins['event_sum'] = bins.n * bins.event_rate
    totals = bins.groupby('threshold').agg(
        n=('n', 'sum'), predicted_sum=('predicted_sum', 'sum'), event_sum=('event_sum', 'sum'))
    if set(totals.index) != set(THRESHOLDS) or (totals.n <= 0).any():
        raise ValueError(f'Incomplete threshold coverage: {directory}')
    totals['mean_probability'] = totals.predicted_sum / totals.n
    totals['event_rate'] = totals.event_sum / totals.n
    return totals.loc[THRESHOLDS, ['n', 'mean_probability', 'event_rate']]


def plot_threshold_risk(facts, output):
    evidence = pd.DataFrame(facts['matched_threshold_risk'])
    if set(evidence.fraction) != {.3}:
        raise ValueError('Risk figure requires matched 30% fitting')
    values = np.r_[evidence.mean_probability.to_numpy(), evidence.event_rate.to_numpy()] * 100
    limits = (max(.001, min(values[values > 0]) * .7), max(values) * 1.2)
    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.6), sharey=True)
    models = [('random_forest','RF','o'), ('binary_logistic','LR','s'), ('gbt','GBT','^')]
    for axis, (mode, label) in zip(axes, MODES):
        data = evidence[evidence['mode'] == mode]
        reference = data[data.model == 'random_forest'].set_index('threshold').loc[THRESHOLDS]
        x = np.arange(len(THRESHOLDS))
        axis.plot(x, 100*reference.event_rate, 'D--', color='#263C48', markersize=3.4,
                  linewidth=1.1, label='Observed event rate', zorder=4)
        for model, name, marker in models:
            frame = data[data.model == model].set_index('threshold').loc[THRESHOLDS]
            if not np.array_equal(frame.n,reference.n) or not np.allclose(frame.event_rate,reference.event_rate,atol=1e-12,rtol=0):
                raise ValueError('Matched-risk populations differ')
            axis.plot(x,100*frame.mean_probability,marker+'-',color=COLOURS[model],
                      markersize=4.1,linewidth=1.3,label=name+' (30% training)')
        axis.set(title=f'{label}: ' + ('recent rainfall' if mode == 'short_term' else 'calendar only'),
                 xlabel='Rainfall threshold q (mm)',xticks=x,
                 xticklabels=[f'{q:g}' for q in THRESHOLDS],yscale='log',ylim=limits)
        axis.grid(alpha=.65)
    axes[0].set_ylabel('Mean risk / observed event rate (%)')
    axes[0].set_yticks([.1,.2,.5,1,2,5])
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda value,_:f'{value:g}'))
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles,labels,loc='lower center',ncol=2,frameon=False,
                  bbox_to_anchor=(.53,-.015),fontsize=8)
    figure.subplots_adjust(left=.10,right=.99,top=.89,bottom=.28,wspace=.15)
    save_figure(figure,output,'23_threshold_risk')
    evidence.to_csv(ROOT / 'report/task2/threshold_risk.csv',index=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--facts', type=Path, default=FACTS)
    parser.add_argument('--output', type=Path, default=ROOT / 'figures/project-report')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.labelsize': 9,
        'axes.titlesize': 10, 'axes.spines.top': False, 'axes.spines.right': False,
        'axes.edgecolor': '#9BA8AF', 'text.color': '#243844', 'axes.labelcolor': '#243844',
        'grid.color': '#E7ECEF', 'pdf.fonttype': 42,
    })
    facts = json.loads(args.facts.read_text())
    plot_sampling(facts,args.output)
    plot_threshold_risk(facts,args.output)


if __name__ == '__main__':
    main()

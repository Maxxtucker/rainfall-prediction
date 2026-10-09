#!/usr/bin/env python3
"""Summarize downloaded completed dual-model outputs, using standard library only."""
import argparse,csv,json
from pathlib import Path


def rows(folder):
    return [r for p in sorted(folder.glob('part-*.csv')) for r in csv.DictReader(p.open())]


def metadata(folder):
    parts=list(folder.glob('part-*'))
    return json.loads('\n'.join(p.read_text() for p in parts if not p.name.endswith('.crc')))


def number(value):
    return f'{float(value):.5f}' if value else 'undefined'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',required=True,type=Path)
    args=parser.parse_args(); root=args.results
    text=['# Task 2 real-data results','', 'Both models estimate strict P(next 30-minute amount > threshold).',
          'A uses available own-station history; B uses station/calendar only. No neighbor features.', '']
    shared=rows(root/'comparison'/'metrics')
    averages={mode:sum(float(r['brier']) for r in shared if r['model']==mode)/
              sum(r['model']==mode for r in shared) for mode in ['short_term','calendar']}
    common_count=metadata(root/'comparison'/'metadata')['counts']['common']
    text += [f'On {common_count:,} shared 2024 anchors, the equal-threshold mean Brier score is '
             f"{averages['short_term']:.5f} for A and {averages['calendar']:.5f} for B "
             f"({100*(1-averages['short_term']/averages['calendar']):.1f}% lower for A). "
             'This is a reduction in probability squared error, not a percentage-point accuracy gain.',
             'Brier is lower-is-better; PR-AUC is higher-is-better. AUC uses Spark numBins=1000 '
             'downsampling and can vary slightly with partitioning.','']
    for mode,title in [('short_term','A: short-term'),('calendar','B: calendar risk')]:
        model=root/'models'/mode; meta=metadata(model/'metadata')
        if not meta.get('test_evaluation_completed'):raise ValueError(mode+' test evaluation incomplete')
        text += ['## '+title,'',f"RF depth {meta['depth']}, trees {meta['num_trees']}, temperature {meta['temperature']}; train fraction {meta['train_fraction']}, evaluation fraction {meta['eval_fraction']}.",
                 'Training: 2017–2021; validation: 2022; calibration: 2023; test: 2024.',
                 'Split counts: `'+json.dumps(meta['counts'])+'`.','',
                 '| Threshold mm | Model | Test n | Event rate | Brier | PR-AUC |','|---:|---|---:|---:|---:|---:|']
        for r in sorted(rows(model/'metrics'/'test_metrics'),key=lambda r:(float(r['threshold']),r['model'])):
            if r['cutoff_kind']!='default_0.5':continue
            text.append('| '+ ' | '.join([r['threshold'],r['model'],r['n'],number(r['prevalence']),number(r['brier']),number(r['pr_auc'])])+' |')
        text += ['']
    text += ['## Fair comparison on shared 2024 anchors','',
             '| Threshold mm | RF mode | Test n | Brier | PR-AUC |','|---:|---|---:|---:|---:|']
    for r in sorted(rows(root/'comparison'/'metrics'),key=lambda r:(float(r['threshold']),r['model'])):
        text.append('| '+' | '.join([r['threshold'],r['model'],r['n'],number(r['brier']),number(r['pr_auc'])])+' |')
    text += ['', 'Comparison audit: `'+json.dumps(metadata(root/'comparison'/'metadata'))+'`.', '',
             'Individual model metrics can use different eligible populations. Use the shared-anchor table for direct comparisons.',
             'Five-minute windows overlap; samples are not independent storms. Binary LR is uncalibrated.',
             'Calendar risk is a historical seasonal estimate, not a forecast of specific future storm conditions.','']
    (root/'RESULTS.md').write_text('\n'.join(text))
    print(root/'RESULTS.md')


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Generate supplementary GBT and full-training report tables from imported evidence."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def build_section():
    path=ROOT/'report/task2/teammate_facts.json'
    if not path.exists(): return ''
    facts=json.loads(path.read_text());records=facts['summary']
    def row(mode,model,fraction):
        return next(r for r in records if r['mode']==mode and r['model']==model and r['fraction']==fraction)
    gbt_rows=[];full_rows=[];interior_rows=[]
    for mode,label in [('short_term','A'),('calendar','B')]:
        for f in [.15,.3,1.]:
            r=row(mode,'gbt',f)
            gbt_rows.append(f"{label} & {100*f:g}\\% & {r['mean_brier']:.8f} & {r['mean_log_loss']:.8f} & {r['mean_pr_auc']:.5f} & {r['temperature']:g} "+r'\\')
        for model,name in [('random_forest','RF'),('binary_logistic','Logistic regression'),('climatology','Historical frequency')]:
            a,b=row(mode,model,.15),row(mode,model,1.)
            change=100*(b['mean_brier']/a['mean_brier']-1)
            full_rows.append(f"{label} & {name} & {a['mean_brier']:.8f} & {b['mean_brier']:.8f} & {change:+.3f} "+r'\\')
        for r in facts['interior_thresholds']:
            if r['mode']==mode and r['fraction']==1:
                interior_rows.append(f"{label} & {r['threshold']:g} & {r['random_forest_brier']:.6f} & {r['gbt_brier']:.6f} & {r['random_forest_pr_auc']:.4f} & {r['gbt_pr_auc']:.4f} "+r'\\')
    s=(ROOT/'report/task2/teammate.template.tex').read_text()
    for key,rows in [('GBT_ROWS',gbt_rows),('FULL_ROWS',full_rows),('INTERIOR_ROWS',interior_rows)]:s=s.replace('@@'+key+'@@','\n'.join(rows))
    if '@@' in s: raise ValueError('Unfilled teammate section')
    return s


if __name__=='__main__':
    path=ROOT/'report/task2/teammate.tex';path.write_text(build_section());print(path)

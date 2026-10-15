#!/usr/bin/env python3
"""Reconcile teammate GBT/full-training exports and build supplementary report evidence."""
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
Q=[0.,.2,1.,2.,5.,10.,20.]
GBT=ROOT/'outputs/steps/gbt-sampling-20261014-run01'
FULL=ROOT/'outputs/steps/task2-full-20261012'
ORIGINAL=ROOT/'outputs/steps/task2-dual-v2/models'


def document(path):
    files=sorted(path.glob('part-*'))
    if len(files)!=1: raise ValueError(f'Expected one document: {path}')
    return json.loads(files[0].read_text())


def csv(path):
    files=sorted(path.glob('part-*.csv'))
    if not files: raise ValueError(f'Missing table: {path}')
    return pd.concat([pd.read_csv(p) for p in files],ignore_index=True)


def default_metrics(path):
    frame=csv(path)
    frame=frame[frame.cutoff_kind=='default_0.5'].copy()
    if frame.duplicated(['model','threshold']).any(): raise ValueError('Duplicate metric rows')
    return frame


def reconcile_daily(metrics,daily):
    totals=daily.groupby('threshold').agg(n=('n','sum'),sse=('sum_squared_error','sum'))
    expected=metrics.set_index('threshold')
    if set(totals.index)!=set(expected.index): raise ValueError('Daily thresholds differ')
    totals=totals.loc[expected.index]
    if not np.array_equal(totals.n.to_numpy(),expected.n.to_numpy()): raise ValueError('Daily counts differ')
    if not np.allclose(totals.sse/totals.n,expected.brier,rtol=0,atol=1e-12): raise ValueError('Daily Brier does not reconcile')


def compare_cohort(left,right):
    left=left.set_index('threshold').loc[Q];right=right.set_index('threshold').loc[Q]
    if not np.array_equal(left.n.to_numpy(),right.n.to_numpy()): raise ValueError('Evaluation counts differ')
    if not np.allclose(left.prevalence,right.prevalence,rtol=0,atol=1e-14): raise ValueError('Event prevalence differs')


def summary_record(mode,model,fraction,metrics,evidence='raw export'):
    primary=metrics[metrics.threshold.isin(Q)]
    if set(primary.threshold)!=set(Q): raise ValueError('Missing primary thresholds')
    return dict(mode=mode,model=model,fraction=fraction,mean_brier=float(primary.brier.mean()),
                mean_log_loss=float(primary.log_loss.mean()),mean_pr_auc=float(primary.pr_auc.mean()),
                pr_auc_1mm=float(primary.loc[primary.threshold==1,'pr_auc'].iloc[0]),evidence=evidence)


def reported15():
    # Preserve summary-only evidence as reported; do not manufacture raw outputs.
    records=[]
    for line in (GBT/'teammate-summary.md').read_text().splitlines():
        c=[x.strip() for x in line.strip().strip('|').split('|')]
        if len(c)==7 and c[0] in ('short_term','calendar') and c[1]=='15%':
            records.append(dict(mode=c[0],model='gbt',fraction=.15,mean_brier=float(c[2]),mean_log_loss=float(c[3]),
                                mean_pr_auc=float(c[4]),depth=int(c[5]),temperature=float(c[6]),evidence='teammate summary only',pr_auc_1mm=None))
    if len(records)!=2: raise ValueError('Expected two reported 15% GBT rows')
    return records


def main():
    records=reported15();interior=[];violations=[];checks=[]
    calendar15=GBT/'calendar/sample15'
    calendar15_verified=False
    if calendar15.exists():
        meta15=document(calendar15/'metadata')
        ref15=document(ORIGINAL/'calendar/metadata')
        for key in ('split_years','numeric_features','seed','eval_fraction'):
            if meta15[key]!=ref15[key]: raise ValueError('Calendar 15% protocol differs: '+key)
        metric15=default_metrics(calendar15/'metrics/gbt')
        compare_cohort(metric15,default_metrics(ORIGINAL/'calendar/metrics/test_metrics').query("model == 'random_forest'"))
        g=metric15
        if not np.array_equal((g.tp+g.fn).to_numpy(),np.rint(g.prevalence*g.n).astype('int64').to_numpy()):
            raise ValueError('Calendar 15% prevalence/confusion counts differ')
        reported=next(r for r in records if r['mode']=='calendar')
        measured=summary_record('calendar','gbt',.15,metric15,evidence='per-threshold text export')
        if abs(measured['mean_brier']-reported['mean_brier'])>5e-9:raise ValueError('Calendar 15% summary differs')
        measured.update(depth=meta15['depth'],temperature=meta15['temperature'])
        records=[measured if r['mode']=='calendar' else r for r in records]
        calendar15_verified=True
    source=GBT/'source/train_gbt_sampling.py';source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    for mode in ('short_term','calendar'):
        ref_meta=document(ORIGINAL/mode/'metadata')
        ref=default_metrics(ORIGINAL/mode/'metrics/test_metrics')
        for model in ('random_forest','binary_logistic','climatology'):
            records.append(summary_record(mode,model,.15,ref[ref.model==model]))
        full_meta=document(FULL/'models'/mode/'metadata')
        for key in ('split_years','numeric_features','seed','eval_fraction'):
            if full_meta[key]!=ref_meta[key]: raise ValueError('Full-training protocol differs: '+key)
        if full_meta['train_fraction']!=1 or full_meta['counts']['train_sample']!=ref_meta['counts']['train_full']:
            raise ValueError('Not full training')
        if document(FULL/'models'/mode/'empirical_support')!=document(ORIGINAL/mode/'empirical_support'):
            raise ValueError('Full-training amount support differs')
        full_metrics=default_metrics(FULL/'models'/mode/'metrics/test_metrics')
        for model in ('random_forest','binary_logistic','climatology'):
            m=full_metrics[full_metrics.model==model];compare_cohort(m,ref[ref.model==model])
            records.append(summary_record(mode,model,1.,m))
        full_daily=csv(FULL/'models'/mode/'metrics/daily_scores')
        daily_check=full_daily.rename(columns={'sum_sq_error_rf':'sum_squared_error'})
        reconcile_daily(full_metrics[full_metrics.model=='random_forest'],daily_check)
        for sample,fraction in (('sample30',.3),('sample100',1.)):
            base=GBT/mode/sample;meta=document(base/'metadata')
            if not meta['test_evaluation_completed'] or meta['source_sha256']!=source_hash: raise ValueError('GBT source/completion differs')
            for key in ('split_years','numeric_features','seed','eval_fraction'):
                if meta[key]!=ref_meta[key]: raise ValueError('GBT protocol differs: '+key)
            if meta['counts']['test']!=ref_meta['counts']['test']: raise ValueError('Test count differs')
            all_metrics={model:default_metrics(base/'metrics'/model) for model in ('gbt','random_forest','binary_logistic','climatology')}
            for model,m in all_metrics.items():
                compare_cohort(m,ref[ref.model==('random_forest' if model=='gbt' else model)])
                reconcile_daily(m,csv(base/'daily_scores'/model))
                rel=csv(base/'reliability'/model).groupby('threshold').agg(n=('n','sum'))
                if not np.array_equal(rel.loc[m.threshold,'n'],m.n): raise ValueError('Reliability counts differ')
            record=summary_record(mode,'gbt',fraction,all_metrics['gbt']);record.update(depth=meta['depth'],temperature=meta['temperature'],train_anchors=meta['counts']['train_sample'])
            records.append(record)
            order=csv(base/'threshold_order/gbt').iloc[0]
            violations.append(dict(mode=mode,fraction=fraction,**order.to_dict()))
            for q in (3.,7.5,15.):
                row=dict(mode=mode,fraction=fraction,threshold=q)
                for model in ('gbt','random_forest','binary_logistic'):
                    m=all_metrics[model];r=m[m.threshold==q].iloc[0]
                    row[model+'_brier']=float(r.brier);row[model+'_pr_auc']=float(r.pr_auc)
                interior.append(row)
            checks.append(dict(mode=mode,fraction=fraction,daily_brier_reconciled=True,cohort_counts_and_prevalence_match=True,source_hash_matches=True))
    result={'summary':records,'interior_thresholds':interior,'threshold_order':violations,'checks':checks,
            'limitations':['A 15% GBT is summary-only; B 15% has per-threshold text metrics. Neither 15% pipeline is supplied.',
                           'Counts and prevalence agree; row-level input identity is not independently proven.',
                           'Imported 2024 results are supplementary follow-ups; original models remain unchanged.']}
    dest=ROOT/'report/task2/teammate_facts.json';dest.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    pd.DataFrame(records).to_csv(GBT/'integrated_summary.csv',index=False)
    pd.DataFrame(interior).to_csv(GBT/'interior_threshold_comparison.csv',index=False)
    (GBT/'integration_validation.json').write_text(json.dumps({'passed':True,'checks':checks,'full_training_daily_brier_reconciled':True,'source_sha256':source_hash,'gbt15_raw_verified':False,'calendar15_metric_export_verified':calendar15_verified},indent=2)+'\n')
    print(pd.DataFrame(records)[['mode','model','fraction','mean_brier','evidence']].to_string(index=False))


if __name__=='__main__':main()

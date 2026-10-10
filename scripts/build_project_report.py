#!/usr/bin/env python3
"""Combine the preserved Task 1 draft with result-driven Task 2 analysis."""
import json,re
from pathlib import Path
import pandas as pd


def main():
    root=Path('outputs/steps/task2-dual-v2');f=json.loads(Path('report/task2/analysis_facts.json').read_text());t=Path('report/task2/section_template.tex').read_text()
    def rows(lines):return '\n'.join(line+r' \\' for line in lines)
    def pct(x):return f'{100*x:.1f}'
    A=f['models']['short_term'];B=f['models']['calendar'];common=pd.DataFrame(f['common_threshold_results']);c=common.pivot(index='threshold',columns='model',values='brier');skill=100*(1-c.short_term/c.calendar)
    sensitivity=Path('report/task2/rf_sensitivity.tex')
    v={'RF_SENSITIVITY': sensitivity.read_text() if sensitivity.exists() else ''}
    labels=[('train_full','2017--2021 (full)','Empirical supports and baseline'),('train_sample','2017--2021 (15\\%)','RF and binary fitting'),('validation','2022','Model and cutoff selection'),('calibration','2023','RF temperature selection'),('test','2024','Final held-out evaluation')]
    v['SPLIT_ROWS']=rows([f"{name} & {A['counts'][key]:,} & {B['counts'][key]:,} & {role}" for key,name,role in labels])
    cr=[]
    for q in c.index:
        a=common[(common.model=='short_term')&(common.threshold==q)].iloc[0];b=common[(common.model=='calendar')&(common.threshold==q)].iloc[0]
        cr.append(f'{q:g} & {100*a.prevalence:.3f} & {a.brier:.5f} & {b.brier:.5f} & {a.pr_auc:.4f} & {b.pr_auc:.4f}')
    v['COMMON_ROWS']=rows(cr);v.update(COMMON_N=f"{f['comparison']['counts']['common']:,}",COVERAGE=f"{100*f['comparison']['short_term_coverage_of_calendar_test']:.1f}",MAX_TRAIN=f"{A['max_training_amount']:.1f}",MACRO_A=f"{f['common_macro_brier']['short_term']:.5f}",MACRO_B=f"{f['common_macro_brier']['calendar']:.5f}",REDUCTION=pct(f['common_relative_reduction']),CI_LOW=pct(f['bootstrap']['macro_relative_reduction_95'][0]),CI_HIGH=pct(f['bootstrap']['macro_relative_reduction_95'][1]),SKILL_ZERO=f'{skill.loc[0]:.1f}',SKILL_TWENTY=f'{skill.loc[20]:.1f}')
    for mode,label in [('short_term','A'),('calendar','B')]:
        a=common[(common.model==mode)&(common.threshold==1)].iloc[0];v['PR_'+label]=f'{a.pr_auc:.4f}'
    table=[];allmetrics={}
    for mode,label in [('short_term','A'),('calendar','B')]:
        m=pd.concat([pd.read_csv(q) for q in (root/'models'/mode/'metrics'/'test_metrics').glob('part-*.csv')]);allmetrics[mode]=m
        for model,name in [('random_forest','Random forest'),('binary_logistic','Binary LR'),('climatology','Historical frequency')]:
            q=m[(m.model==model)&(m.threshold==1)&(m.cutoff_kind=='default_0.5')].iloc[0]
            table.append(f"{label} & {name} & {f['models'][mode]['macro_brier'][model]:.5f} & {q.pr_auc:.4f} & {q.roc_auc:.4f} & {q.log_loss:.4f}")
            if mode=='short_term':
                if model=='random_forest':v['RF_ROC']=f'{q.roc_auc:.4f}'
                if model=='binary_logistic':v['LR_ROC']=f'{q.roc_auc:.4f}'
    v['BASELINE_ROWS']=rows(table);v.update(B_BASE=f"{B['macro_brier']['climatology']:.5f}",B_RF=f"{B['macro_brier']['random_forest']:.5f}",B_LR=f"{B['macro_brier']['binary_logistic']:.5f}")
    cal=next(r for r in A['calibration'] if r['threshold']==1 and r['model']=='random_forest');v.update(A_MEAN_P=f"{100*cal['mean_probability']:.2f}",A_EVENT=f"{100*cal['event_rate']:.2f}",A_ECE=f"{100*cal['ece_10bin']:.3f}")
    v.update(MONTH_MIN=f"{min(f['monthly_skill_q1'].values()):.1f}",MONTH_MAX=f"{max(f['monthly_skill_q1'].values()):.1f}",STATION_MIN=f"{f['station_skill_q1']['min']:.1f}",STATION_MAX=f"{f['station_skill_q1']['max']:.1f}")
    im={r['feature']:r['importance'] for r in f['importance']}
    for key,name in [('IMP_15','rain_sum_15'),('IMP_MAX','rain_max_30'),('IMP_60','rain_sum_60'),('IMP_DRY','dry_fraction_60')]:v[key]=pct(im[name])
    operating=[]
    for mode,model,kind,name,source in [('short_term','random_forest','default_0.5','A forest','Default'),('short_term','random_forest','validation_f1','A forest','Validation F1'),('short_term','binary_logistic','validation_f1','A binary LR','Validation F1'),('calendar','random_forest','validation_f1','B forest','Validation F1')]:
        a=allmetrics[mode];z=a[(a.model==model)&(a.threshold==1)&(a.cutoff_kind==kind)].iloc[0]
        operating.append(f'{name} & {source} & {z.cutoff:g} & {z.precision:.3f} & {z.recall:.3f} & {z.f1:.3f}')
    v['OPERATING_ROWS']=rows(operating)
    for key,value in v.items():t=t.replace('@@'+key+'@@',value)
    if '@@' in t:raise ValueError('Unfilled Task 2 placeholder')
    Path('report/task2/section.tex').write_text(t)
    template=Path('report/project_report.template.tex').read_text()
    if template.count('@@TASK2@@') != 1:
        raise ValueError('Combined template must contain one Task 2 insertion point')
    report=template.replace('@@TASK2@@',t)
    if '@@' in report:
        raise ValueError('Unfilled combined-report placeholder')
    Path('report/project_report.tex').write_text(report)
    print('report/project_report.tex')

if __name__=='__main__':main()

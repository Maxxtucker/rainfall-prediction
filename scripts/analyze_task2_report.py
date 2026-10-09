#!/usr/bin/env python3
"""Reconcile saved Spark metrics, analyse uncertainty, and build report figures."""
import argparse,json,calendar
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

INK='#233E4A'; TEAL='#087F8C'; CORAL='#CE684F'; GREY='#647780'

def read(path):
    files=sorted(path.glob('part-*.csv'))
    if not files:raise FileNotFoundError(path)
    return pd.concat([pd.read_csv(p) for p in files],ignore_index=True)

def meta(path):return json.loads(next(path.glob('part-*')).read_text())

def clean_json(value):
    if isinstance(value,dict):return {k:clean_json(v) for k,v in value.items()}
    if isinstance(value,list):return [clean_json(v) for v in value]
    if isinstance(value,(float,np.floating)) and not np.isfinite(value):return None
    return value

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,default=Path('outputs/steps/task2-dual-v2'));p.add_argument('--figures',type=Path,default=Path('figures/task2-report'));args=p.parse_args()
    r=args.results;out=args.figures;out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelsize':9,'axes.titlesize':10,'axes.titleweight':'bold','text.color':INK,'axes.labelcolor':INK,'axes.edgecolor':'#B7C3C9','axes.spines.top':False,'axes.spines.right':False,'grid.color':'#E3E9EC','svg.fonttype':'none','pdf.fonttype':42})
    def save(name,fig):
        fig.tight_layout()
        for ext in ['pdf','png','svg']:fig.savefig(out/(name+'.'+ext),dpi=180,bbox_inches='tight',pad_inches=.04)
        plt.close(fig)
    metrics={};facts={'models':{}}
    for mode in ['short_term','calendar']:
        root=r/'models'/mode;m=meta(root/'metadata');assert m['test_evaluation_completed']
        a=read(root/'metrics'/'test_metrics');metrics[mode]=a
        one=a[a.cutoff_kind=='default_0.5']
        assert (one.n==m['counts']['test']).all()
        facts['models'][mode]={'counts':m['counts'],'selection':read(root/'metrics'/'model_selection').to_dict('records'),'binary_selection':read(root/'metrics'/'binary_model_selection').to_dict('records'),'depth':m['depth'],'temperature':m['temperature'],'macro_brier':one.groupby('model').brier.mean().to_dict(),'max_training_amount':m['train_max_y30'],'elapsed_seconds':m['elapsed_seconds']}
        rel=read(root/'metrics'/'reliability');cal=[]
        for (model,q),g in rel.groupby(['model','threshold']):
            n=g.n.sum();event=np.average(g.event_rate,weights=g.n)
            expected=one[(one.model==model)&(one.threshold==q)].iloc[0]
            assert n==expected.n and abs(event-expected.prevalence)<1e-10
            cal.append({'model':model,'threshold':q,'mean_probability':np.average(g.mean_probability,weights=g.n),'event_rate':event,'ece_10bin':np.average(abs(g.mean_probability-g.event_rate),weights=g.n),'occupied_bins':len(g)})
        facts['models'][mode]['calibration']=cal
        known=set(pd.read_parquet(root/'stations').station_id)
        sub=read(root/'metrics'/'subgroups')
        station_rows=sub[(sub.model=='random_forest')&(sub.threshold==1)&(sub.group_type=='station_id')]
        unseen=station_rows[~station_rows.group_value.isin(known)]
        facts['models'][mode]['station_catalogue']={'training_stations':len(known),
            'unseen_test_station_ids':unseen.group_value.tolist(),'unseen_test_anchors':int(unseen.n.sum())}
    common=read(r/'comparison'/'metrics');audit=meta(r/'comparison'/'metadata');facts['comparison']=audit
    assert (common.n==audit['counts']['common']).all()
    c=common.pivot(index='threshold',columns='model',values='brier');skill=100*(1-c.short_term/c.calendar)
    facts['common_macro_brier']=common.groupby('model').brier.mean().to_dict()
    facts['common_relative_reduction']=1-c.short_term.mean()/c.calendar.mean()
    facts['common_threshold_results']=common.to_dict('records')
    # Reconcile every metric with its paired daily sufficient statistics.
    daily=read(r/'comparison'/'daily_scores');dates=pd.date_range('2024-01-01','2024-12-31');daily['date']=pd.to_datetime(daily.date)
    qs=sorted(common.threshold.unique());n=np.zeros((366,len(qs)));sa=n.copy();sb=n.copy()
    for j,q in enumerate(qs):
        g=daily[daily.threshold==q].set_index('date').reindex(dates,fill_value=0)
        n[:,j]=g.n;sa[:,j]=g.short_term_sum_squared_error;sb[:,j]=g.calendar_sum_squared_error
        for mode,s in [('short_term',sa),('calendar',sb)]:
            expected=common[(common.model==mode)&(common.threshold==q)].iloc[0]
            assert n[:,j].sum()==expected.n and abs(s[:,j].sum()/n[:,j].sum()-expected.brier)<1e-10
    rng=np.random.default_rng(2026);reps=2000;boot=[];perq=[]
    for _ in range(reps):
        starts=rng.integers(0,366,size=53);idx=((starts[:,None]+np.arange(7))%366).ravel()[:366]
        aa=sa[idx].sum(axis=0)/n[idx].sum(axis=0);bb=sb[idx].sum(axis=0)/n[idx].sum(axis=0)
        boot.append(1-aa.mean()/bb.mean());perq.append(1-aa/bb)
    facts['bootstrap']={'method':'Circular moving blocks of 7 calendar days; all stations and thresholds kept together; 2000 replicates; seed 2026; conditional on the observed 2024 network','supported_dates':int((n[:,0]>0).sum()),'macro_relative_reduction_95':np.quantile(boot,[.025,.975]).tolist(),'per_threshold_relative_reduction_95':np.quantile(perq,[.025,.975],axis=0).T.tolist()}
    fig,ax=plt.subplots(figsize=(8,2.1));hist=np.arange(-65,-5,5);future=np.arange(5,35,5)
    ax.axvspan(-68,-8,color=TEAL,alpha=.08);ax.axvspan(3,33,color=CORAL,alpha=.08)
    ax.scatter(hist,np.zeros(12),s=42,color=TEAL);ax.scatter(future,np.zeros(6),s=42,color=CORAL)
    ax.axvline(0,color=INK,lw=1.2)
    ax.text(-38,.57,'12 observed history intervals',ha='center',color=TEAL,fontweight='bold',fontsize=9)
    ax.text(18,.57,'6 future label intervals',ha='center',color=CORAL,fontweight='bold',fontsize=9)
    ax.annotate('Latest history: t - 10 min',xy=(-10,0),xytext=(-38,.26),arrowprops={'arrowstyle':'->','color':GREY},ha='center',fontsize=8)
    ax.annotate('Issue time t',xy=(0,0),xytext=(0,-.30),ha='center',fontweight='bold',fontsize=8,bbox={'facecolor':'white','edgecolor':'none','pad':1.5})
    ax.set(xlim=(-72,36),ylim=(-.45,.75),yticks=[],xticks=[-65,-40,-10,5,30],xlabel='Interval endpoint relative to issue time (minutes)')
    ax.spines['left'].set_visible(False);ax.spines['bottom'].set_position(('data',-.45))
    save('17_prediction_timeline',fig)
    fig,axes=plt.subplots(1,2,figsize=(8,2.75));x=np.arange(7);ci=np.array(facts['bootstrap']['per_threshold_relative_reduction_95'])*100
    axes[0].bar(x,skill,color=TEAL,width=.65);axes[0].errorbar(x,skill,yerr=[skill.to_numpy()-ci[:,0],ci[:,1]-skill.to_numpy()],fmt='none',ecolor=INK,capsize=3,lw=1)
    axes[0].set(xticks=x,xticklabels=[f'{q:g}' for q in qs],xlabel='Threshold (mm)',ylabel='Brier reduction of A vs B (%)',title='(a) Paired probability error');axes[0].axhline(0,color=GREY,lw=.7)
    for mode,label,color in [('short_term','A: recent rainfall',TEAL),('calendar','B: calendar only',CORAL)]:
        g=common[common.model==mode].sort_values('threshold');axes[1].plot(x,g.pr_auc,'o-',label=label,color=color)
    g=common[common.model=='short_term'].sort_values('threshold');axes[1].plot(x,g.prevalence,'--',color=GREY,label='Event prevalence (reference)');axes[1].set(xticks=x,xticklabels=[f'{q:g}' for q in qs],xlabel='Threshold (mm)',ylabel='Spark PR-AUC (log scale)',yscale='log',title='(b) Rare-event ranking');axes[1].legend(frameon=False,fontsize=8)
    save('18_common_comparison',fig)
    fig,axes=plt.subplots(1,2,figsize=(8,2.6));colors={'random_forest':TEAL,'binary_logistic':CORAL,'climatology':GREY};labels={'random_forest':'Random forest','binary_logistic':'Binary LR','climatology':'Historical frequency'}
    for ax,mode,title in zip(axes,['short_term','calendar'],['(a) A: own eligible test anchors','(b) B: own eligible test anchors']):
        a=metrics[mode];a=a[a.cutoff_kind=='default_0.5'];pivot=a.pivot(index='threshold',columns='model',values='brier')
        for model in ['random_forest','binary_logistic']:
            ax.plot(x,100*(1-pivot[model]/pivot.climatology),'o-',color=colors[model],label=labels[model])
        ax.axhline(0,color=GREY,lw=1,label='Historical frequency');ax.set(xticks=x,xticklabels=[f'{q:g}' for q in qs],xlabel='Threshold (mm)',ylabel='Brier skill vs historical frequency (%)',title=title);ax.legend(frameon=False,fontsize=7)
    save('19_baseline_skill',fig)
    rel=read(r/'comparison'/'reliability');fig,axes=plt.subplots(1,2,figsize=(8,2.85));q=1
    for ax,mode,title,col in zip(axes,['short_term','calendar'],['(a) A: probability range 0-1','(b) B: low-probability range'],[TEAL,CORAL]):
        g=rel[(rel.model==mode)&(rel.threshold==q)].sort_values('bin');lim=1 if mode=='short_term' else .16
        ax.plot([0,lim],[0,lim],'--',color=GREY,lw=1);ax.plot(g.mean_probability,g.event_rate,'-',color=col,lw=1);ax.scatter(g.mean_probability,g.event_rate,s=18+12*np.log10(g.n),c=col,alpha=.85)
        for row in g.itertuples():
            if mode=='calendar' or row.mean_probability==g.mean_probability.max():ax.annotate(f'n={row.n:,}',(row.mean_probability,row.event_rate),xytext=(5,5),textcoords='offset points',fontsize=7)
        ax.set(xlim=(0,lim),ylim=(0,lim),xlabel='Mean predicted probability',ylabel='Observed event fraction',title=title);ax.grid(alpha=.4)
    save('20_reliability',fig)
    sub=read(r/'models'/'short_term'/'metrics'/'subgroups');s=sub[(sub.threshold==1)&(sub.group_type=='month')].pivot(index='group_value',columns='model',values='brier');s.index=s.index.astype(int);s=s.sort_index();monthlyskill=100*(1-s.random_forest/s.climatology)
    facts['monthly_skill_q1']=monthlyskill.to_dict()
    stations=sub[(sub.threshold==1)&(sub.group_type=='station_id')];sp=stations.pivot(index='group_value',columns='model',values='brier');ss=100*(1-sp.random_forest/sp.climatology);facts['station_skill_q1']={'n_stations':len(ss),'n_positive_skill':int((ss>0).sum()),'min':float(ss.min()),'max':float(ss.max()),'worst_station':ss.idxmin(),'best_station':ss.idxmax()}
    importance=read(r/'models'/'short_term'/'metrics'/'feature_importance').sort_values('importance',ascending=False);facts['importance']=importance.to_dict('records')
    fig,axes=plt.subplots(1,2,figsize=(8,2.8));axes[0].bar(s.index,monthlyskill,color=TEAL);axes[0].axhline(0,color=GREY,lw=.7);axes[0].set(xticks=range(1,13),xticklabels=[calendar.month_abbr[m] for m in range(1,13)],xlabel='Month (2024)',ylabel='Brier skill vs historical\nfrequency (%)',title='(a) A: monthly skill at 1 mm')
    g=importance.head(6).iloc[::-1];names={'rain_sum_15':'15-min total','rain_max_30':'30-min maximum','rain_sum_60':'60-min total','dry_fraction_60':'60-min dry fraction','rain_sum_30':'30-min total','rain_lag_1':'Latest 5-min amount'};axes[1].barh(g.feature.map(lambda v:names.get(v,v)),g.importance*100,color=TEAL);axes[1].set(xlabel='RF impurity importance (%)',title='(b) A: most influential features');axes[0].tick_params(axis='x',labelsize=7,rotation=45);save('21_diagnostics',fig)
    facts['operating_q1']={mode:metrics[mode][(metrics[mode].threshold==1)&(metrics[mode].model.isin(['random_forest','binary_logistic']))].to_dict('records') for mode in metrics}
    (Path('report/task2')/'analysis_facts.json').write_text(json.dumps(clean_json(facts),indent=2,allow_nan=False))
    common.to_csv(out/'common_metrics.csv',index=False);pd.DataFrame(facts['models']['short_term']['calibration']).to_csv(out/'calibration_A.csv',index=False)
    print(json.dumps({k:facts[k] for k in ['common_macro_brier','bootstrap','monthly_skill_q1','station_skill_q1']},indent=2))

if __name__=='__main__':main()

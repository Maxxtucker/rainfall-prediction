#!/usr/bin/env python3
"""Report-sized Task 1 figures from all-month Spark outputs (no raw data reads).

Writes vector PDFs/SVGs, PNG previews, supporting CSVs, a gallery and an offline
96-period station-map explorer. Captions belong in LaTeX, not inside the image.
"""
import argparse,calendar,html,json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize,TwoSlopeNorm
from matplotlib.patches import Polygon
from plot_task1 import polygons,land_mask

INK='#233E4A'; TEAL='#087F8C'; CORAL='#CE684F'; GREY='#E8ECEE'
YEARS=list(range(2017,2025)); MONTHS=list(range(1,13))

def read(root,name):
    files=sorted((root/'eda'/name).glob('part-*.csv'))
    if not files: raise FileNotFoundError(name)
    return pd.concat([pd.read_csv(f) for f in files],ignore_index=True)


def setup():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':9,'axes.labelsize':8,
        'axes.titleweight':'bold','text.color':INK,'axes.labelcolor':INK,'axes.edgecolor':'#B7C3C9',
        'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white','axes.facecolor':'white',
        'grid.color':'#E3E9EC','svg.fonttype':'none','pdf.fonttype':42})


class Figures:
    def __init__(self,path,refresh=None):
        if path.exists() and not refresh: raise FileExistsError('Use a fresh output directory: '+str(path))
        path.mkdir(parents=True,exist_ok=True);self.path=path;self.filter=set(refresh or [])
        self.items=json.loads((path/'figure_manifest.json').read_text()) if refresh else []
        if refresh and not self.filter.issubset({x['id'] for x in self.items}): raise ValueError('Unknown refresh figure ID')
    def save(self,name,fig,caption):
        if self.filter and name not in self.filter:
            plt.close(fig);return
        self.items=[x for x in self.items if x['id']!=name]
        for ext in ('pdf','png','svg'): fig.savefig(self.path/f'{name}.{ext}',dpi=220,bbox_inches='tight',pad_inches=.04)
        plt.close(fig);self.items.append({'id':name,'caption':caption})


def heat(ax,p,label,cmap='YlGnBu',percent=False,limits=None,annot=True,diverging=False):
    values=p.to_numpy(float);finite=values[np.isfinite(values)]
    if diverging:
        vmax=max(np.max(abs(finite)) if len(finite) else 1,1);norm=TwoSlopeNorm(vmin=-vmax,vcenter=0,vmax=vmax)
    else: norm=Normalize(*(limits or (0,max(float(np.max(finite)) if len(finite) else 1,1))))
    cm=plt.get_cmap(cmap).copy();cm.set_bad(GREY)
    im=ax.imshow(np.ma.masked_invalid(values),aspect='auto',cmap=cm,norm=norm)
    ax.set_xticks(range(len(p.columns)),p.columns);ax.set_yticks(range(len(p.index)),p.index)
    ax.tick_params(length=0,labelsize=7)
    for side in ax.spines.values():side.set_visible(False)
    if annot:
        for (i,j),v in np.ndenumerate(values):
            if np.isfinite(v):
                ax.text(j,i,f'{v:.0f}',ha='center',va='center',fontsize=6.8,color='white' if ((not diverging and norm(v)>.68) or (diverging and abs(norm(v)-.5)>.30)) else INK)
            else: ax.text(j,i,'—',ha='center',va='center',fontsize=7,color='#8D999E')
    ax.figure.colorbar(im,ax=ax,pad=.02,fraction=.035,label=label)
    return im


def pivot(d,v):
    p=d.pivot(index='year',columns='month',values=v).reindex(index=YEARS,columns=MONTHS)
    p.columns=[calendar.month_abbr[m] for m in MONTHS];return p


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--assets',type=Path,default=Path('assets'));p.add_argument('--refresh',nargs='+',help='Refresh named existing figures after a layout change');args=p.parse_args();setup();g=Figures(args.output,args.refresh)
    names=['station_month','station_year','monthly_available_qualified','annual_available_qualified','annual_station_qualified',
        'monthly_pair_comparisons','annual_pair_comparisons','coverage','hourly_available','daily_distribution_available',
        'rainfall_distribution','positive_histogram','coverage_sensitivity_results','daily_record_audit','spatial_month_available','raw_quality']
    d={n:read(args.results,n) for n in names};profile=d['rainfall_distribution'].sort_values('year');coverage=d['coverage']
    profile.to_csv(g.path/'data_profile.csv',index=False)
    fig,ax=plt.subplots(1,3,figsize=(6.8,2.35),layout='constrained')
    ax[0].bar(profile.year,profile.observations/1e6,color=TEAL);ax[0].set(ylabel='Observations (millions)',title='(a) Sample size')
    ax[1].plot(profile.year,profile.zero_fraction*100,'o-',color=TEAL);ax[1].set(ylabel='Zero rainfall (%)',ylim=(0,100),title='(b) Recorded dry intervals')
    for col,label in [('positive_p50_mm','P50'),('positive_p95_mm','P95'),('positive_p99_mm','P99')]: ax[2].plot(profile.year,profile[col],'o-',ms=3,label=label)
    ax[2].set(ylabel='Positive five-minute amount (mm)',title='(c) Wet-interval quantiles');ax[2].legend(fontsize=6)
    for a in ax:a.set_xticks(YEARS);a.tick_params(axis='x',rotation=60);a.grid(axis='y',alpha=.5);a.set_axisbelow(True)
    g.save('01_data_profile',fig,'Sample size, observed zeros and positive-rainfall quantiles. Zero observations are real measurements; missing records are absent.')
    h=d['positive_histogram'].sort_values('lower_mm');fig,ax=plt.subplots(figsize=(6.8,2.3),layout='constrained')
    ax.bar(h.lower_mm,h['count']/h['count'].sum()*100,width=h.upper_mm-h.lower_mm,align='edge',color=TEAL,edgecolor='white',lw=.3)
    ax.set(xscale='log',xlabel='Positive five-minute rainfall (mm; log scale)',ylabel='Share of positive observations (%)')
    ax.grid(axis='y',alpha=.5);ax.set_axisbelow(True)
    g.save('02_positive_distribution',fig,'Positive observations only; logarithmic bin widths. Large recorded values are retained, not automatically validated or rejected.')
    fig,axes=plt.subplots(2,1,figsize=(6.8,4.5),layout='constrained')
    heat(axes[0],pivot(coverage,'median_active_coverage')*100,'Coverage (%)',limits=(0,100));axes[0].set_title('(a) Median coverage among stations with records',loc='left')
    heat(axes[1],pivot(coverage,'qualified_stations').replace(0,np.nan),'Qualified stations');axes[1].set_title('(b) Stations with monthly coverage ≥90%',loc='left')
    g.save('03_coverage',fig,'All 96 calendar combinations. In (a), inactive stations are excluded from the median; in (b), grey means no qualified stations.')
    audit=d['daily_record_audit'];audit['date']=pd.to_datetime(audit.date)
    aug=audit[(audit.date.dt.year==2018)&(audit.date.dt.month==8)]
    fig,ax=plt.subplots(figsize=(6.8,2.0),layout='constrained');ax.bar(aug.date.dt.day-.16,aug.raw_records,width=.32,label='Raw',color='#A7C2D2');ax.bar(aug.date.dt.day+.16,aug.clean_records,width=.32,label='Clean',color=TEAL)
    ax.set(xlabel='Day of August 2018',ylabel='Network records',xticks=[1,3,5,10,15,20,25,31]);ax.legend(frameon=False);ax.axvspan(3.5,31.5,color=GREY,alpha=.6);ax.text(17,aug.raw_records.max()*.6,'No raw records: 4–31 August',ha='center',fontsize=8)
    g.save('04_source_gap',fig,'Raw and cleaned daily counts distinguish a source gap from cleaning losses. Calendar days with zero records remain visible.')
    m=d['monthly_available_qualified'];fig,ax=plt.subplots(figsize=(6.8,3.0),layout='constrained');heat(ax,pivot(m,'mean_station_rainfall_mm'),'Station mean (mm)')
    g.save('05_monthly_amount',fig,'Observed monthly station totals averaged across qualified stations. Composition varies; grey is insufficient data, never zero rainfall.')
    fig,axes=plt.subplots(1,3,figsize=(6.8,2.5),layout='constrained')
    seasonal=[]
    for ax,col,label,factor in zip(axes,['mean_station_rainfall_mm','wet_fraction','mean_wet_interval_mm'],['Monthly amount (mm)','Wet intervals (%)','Wet-interval amount (mm)'],[1,100,1]):
        s=m.groupby('month')[col].agg(['mean','min','max','count']).reindex(MONTHS)*factor
        ax.fill_between(MONTHS,s['min'],s['max'],color=TEAL,alpha=.13);ax.plot(MONTHS,s['mean'],color=TEAL,marker='o',ms=3)
        ax.set(ylabel=label,xticks=[1,3,5,7,9,11],xlabel='Calendar month');ax.grid(axis='y',alpha=.5)
    s=m.groupby('month').agg(mean_mm=('mean_station_rainfall_mm','mean'),years=('year','nunique'),min_stations=('stations','min'),max_stations=('stations','max'))
    s.to_csv(g.path/'seasonal_support.csv');g.save('06_seasonality',fig,'Equal eligible-year means; shading is the observed range, not a confidence interval. Month lengths, stations and available years differ.')
    fig,axes=plt.subplots(3,4,figsize=(6.8,4.05),layout='constrained',sharex=True)
    for month,ax in zip(MONTHS,axes.flat):
        z=m[m.month==month].set_index('year').reindex(YEARS);ax.plot(YEARS,z.mean_station_rainfall_mm,'o-',color=TEAL,ms=3)
        ax.set_title(calendar.month_name[month],fontsize=8);ax.set_xticks([2017,2020,2024]);ax.grid(alpha=.4)
    fig.supylabel('Mean observed monthly station total (mm)',fontsize=8)
    g.save('07_monthly_trends',fig,'Each month is compared across all eight years; gaps break lines. Each small panel has its own vertical range; use the heatmap for magnitude comparisons.')
    annual=d['annual_station_qualified'];summ=d['annual_available_qualified'].sort_values('year');fig,ax=plt.subplots(figsize=(6.8,2.65),layout='constrained')
    for year in YEARS:
        z=annual[annual.year==year].rainfall_total_mm.to_numpy()
        if len(z):
            xs=year+np.linspace(-.14,.14,len(z));ax.scatter(xs,z,s=10,color=TEAL,alpha=.35)
            ax.scatter(year,np.mean(z),marker='D',s=28,color=CORAL,zorder=5);ax.text(year,80,f'n={len(z)}',ha='center',fontsize=7)
        else:ax.axvspan(year-.35,year+.35,color=GREY);ax.text(year,1700,'Insufficient\ncoverage',ha='center',va='center',rotation=90,fontsize=7)
    ax.set(xticks=YEARS,ylabel='Observed calendar-year total (mm)',ylim=(0,max(annual.rainfall_total_mm)*1.12));ax.grid(axis='y',alpha=.4)
    g.save('08_annual_totals',fig,'Dots are eligible station-year totals; diamonds are station means. Annual ≥95% and every month ≥90% coverage are required. No line bridges unsupported years.')
    pairs=d['monthly_pair_comparisons'];adj=pairs[pairs.year_b==pairs.year_a+1].copy();adj['pair']=adj.year_a.astype(str)+'→'+adj.year_b.astype(str)
    order=[f'{y}→{y+1}' for y in range(2017,2024)]
    for name,val,label,div in [('09_paired_changes','change_percent','Paired change (%)',True),('09b_paired_support','stations','Common stations',False)]:
        z=adj.pivot(index='pair',columns='month',values=val).reindex(index=order,columns=MONTHS)
        if div:z=z.where(adj.pivot(index='pair',columns='month',values='stations').reindex(index=order,columns=MONTHS)>=5)
        z.columns=[calendar.month_abbr[x] for x in MONTHS];fig,ax=plt.subplots(figsize=(6.8,2.9),layout='constrained');heat(ax,z,label,cmap='BrBG' if div else 'YlGnBu',diverging=div)
        g.save(name,fig,'Adjacent-year comparison at the same calendar month using common stable-location stations. Changes with fewer than five common stations are not displayed; each pair has a different panel.')
    hours=d['hourly_available'];fig,axes=plt.subplots(1,2,figsize=(6.8,2.65),layout='constrained')
    hm=hours.groupby(['month','hour'])[['wet_intervals','observed_intervals','observed_mm']].sum();hm['wet_percent']=100*hm.wet_intervals/hm.observed_intervals
    hp=hm.wet_percent.unstack().reindex(index=MONTHS,columns=range(24));hp.index=[calendar.month_abbr[x] for x in MONTHS]
    heat(axes[0],hp,'Wet intervals (%)',annot=False);axes[0].set_xticks([0,6,12,18],['0','6','12','18']);axes[0].set_xlabel('Hour (SGT)')
    hy=hours.groupby(['year','hour'])[['wet_intervals','observed_intervals']].sum();hy['wet_percent']=100*hy.wet_intervals/hy.observed_intervals
    for year in YEARS: axes[1].plot(range(24),hy.loc[year].reindex(range(24)).wet_percent,label=str(year),lw=1)
    axes[1].set(xlabel='Hour (SGT)',ylabel='Wet intervals (%)',xticks=[0,6,12,18,23]);axes[1].legend(ncol=2,fontsize=6,frameon=False)
    g.save('10_diurnal',fig,'Observed-interval-weighted wet frequencies using all eligible station-months. Available months and station composition differ between years.')
    daily=d['daily_distribution_available'];fig,axes=plt.subplots(2,1,figsize=(6.8,3.85),layout='constrained')
    heat(axes[0],pivot(daily,'p99_mm'),'P99 daily amount (mm)');heat(axes[1],pivot(daily,'wet_day_fraction')*100,'Wet station-days (%)',limits=(0,100))
    axes[0].set_title('(a) Daily upper tail',loc='left');axes[1].set_title('(b) Observed wet-day frequency',loc='left')
    g.save('11_daily_tails',fig,'Eligible station-months and ≥95% complete station-days. Approximate quantiles include dry days; a wet day has an observed total >0.')
    sens=d['coverage_sensitivity_results'];fig,axes=plt.subplots(1,2,figsize=(6.8,2.65),layout='constrained')
    for cut,part in sens.groupby('threshold'):
        z=part.groupby('month').mean(numeric_only=True).reindex(MONTHS)
        axes[0].plot(MONTHS,z.mean_station_rainfall_mm,'o-',ms=3,label=f'{cut:.0%}')
        axes[1].plot(MONTHS,z.wet_fraction*100,'o-',ms=3,label=f'{cut:.0%}')
    for ax in axes:ax.set(xlabel='Calendar month',xticks=[1,3,5,7,9,11]);ax.legend(fontsize=7,frameon=False);ax.grid(alpha=.4)
    axes[0].set_ylabel('Eligible-year mean monthly amount (mm)');axes[1].set_ylabel('Eligible-year mean wet intervals (%)')
    # Pointwise differences use the same year-months available at both cutoffs.
    base=sens[sens.threshold==.9];checks=[]
    for c in [.8,.95]:
        z=base.merge(sens[sens.threshold==c],on=['year','month'],suffixes=('_90','_other'))
        delta=100*(z.mean_station_rainfall_mm_other/z.mean_station_rainfall_mm_90-1)
        checks.append({'threshold':c,'shared_year_months':len(z),'median_absolute_change_percent':delta.abs().median(),'max_absolute_change_percent':delta.abs().max()})
    pd.DataFrame(checks).to_csv(g.path/'sensitivity_checks.csv',index=False)
    g.save('12_sensitivity',fig,'Seasonal results rerun at 80%, 90% and 95% monthly coverage. The sample changes with the threshold; this is robustness evidence, not missing-data recovery.')
    make_maps(d['spatial_month_available'],annual,args.assets,g)
    findings={'observations':int(profile.observations.sum()),'stations':int(d['station_month'].station_id.nunique()),
        'zero_fraction':float(profile.zero_observations.sum()/profile.observations.sum()),'qualified_year_months':len(m),
        'raw_records':int(d['raw_quality'].raw_records.iloc[0]),'unparsed_raw_timestamps':int(d['raw_quality'].unparsed_timestamps.iloc[0]),
        'network_empty_raw_days':int((audit.raw_records==0).sum()),'qualified_station_months':int(m.stations.sum())}
    (g.path/'findings.json').write_text(json.dumps(findings,indent=2))
    g.items.sort(key=lambda x:x['id'])
    (g.path/'figure_manifest.json').write_text(json.dumps(g.items,indent=2))
    cards=''.join(f'<article><h2>{x["id"]}</h2><img loading="lazy" src="{x["id"]}.png"><p>{html.escape(x["caption"])}</p><a href="{x["id"]}.pdf">Vector PDF</a></article>' for x in g.items)
    (g.path/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Task 1 | All months</title><style>body{font:16px system-ui;max-width:1050px;margin:40px auto;color:#233e4a}article{margin:35px 0;padding:25px;border:1px solid #ddd}img{width:100%}p{line-height:1.6}</style><h1>Singapore rainfall | 2017–2024</h1><p>All 96 calendar combinations. Missing data stay missing. <a href="spatial_explorer.html">Open the 96-period interactive station map</a></p>'+cards)
    print(json.dumps(findings,indent=2));print('Created',len(g.items),'report and supplementary figures in',g.path)


def make_maps(spatial,annual,assets,g):
    rings=polygons(json.loads((assets/'singapore.geojson').read_text()));regions=json.loads((assets/'planning_areas.geojson').read_text())['features']
    rr=[polygons({'features':[f]}) for f in regions];vertices=np.concatenate([np.array(p[0])[:,:2] for p in rings]);bounds=(vertices[:,0].min()-.01,vertices[:,0].max()+.01,vertices[:,1].min()-.01,vertices[:,1].max()+.01)
    norm=Normalize(0,spatial.rainfall_total_mm.max());cm=plt.get_cmap('YlGnBu')
    def base(ax):
        for poly in rings:
            for i,ring in enumerate(poly):ax.add_patch(Polygon(np.array(ring)[:,:2],facecolor='#F0F3F1' if i==0 else 'white',edgecolor='#A2B2B9',lw=.25))
        ax.set(xlim=bounds[:2],ylim=bounds[2:]);ax.set_aspect(1/np.cos(np.deg2rad(1.35)));ax.set_xticks([]);ax.set_yticks([])
        for s in ax.spines.values():s.set_visible(False)
    def points(ax,z,norm):
        base(ax)
        if z.empty:ax.text(.5,.5,'Insufficient data',transform=ax.transAxes,ha='center',fontsize=7)
        else:ax.scatter(z.longitude,z.latitude,c=z.rainfall_total_mm,cmap=cm,norm=norm,s=9,edgecolors='white',linewidths=.25,zorder=3)
    for month in MONTHS:
        fig,axes=plt.subplots(2,4,figsize=(6.8,3.05),layout='constrained')
        for year,ax in zip(YEARS,axes.flat):
            z=spatial[(spatial.year==year)&(spatial.month==month)];points(ax,z,norm);ax.set_title(f'{year} · n={len(z)}',fontsize=8)
        fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cm),ax=list(axes.flat),fraction=.025,pad=.01,label='Observed monthly total (mm)')
        g.save(f'13_spatial_month_{month:02d}',fig,f'{calendar.month_name[month]} across eight years. Qualified station observations; all monthly maps share the same linear colour scale. No interpolated values.')
    for year in YEARS:
        fig,axes=plt.subplots(3,4,figsize=(6.8,3.8),layout='constrained')
        for month,ax in zip(MONTHS,axes.flat):
            z=spatial[(spatial.year==year)&(spatial.month==month)];points(ax,z,norm);ax.set_title(f'{calendar.month_abbr[month]} · n={len(z)}',fontsize=8)
        fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cm),ax=list(axes.flat),fraction=.025,pad=.01,label='Observed monthly total (mm)')
        g.save(f'14_spatial_year_{year}',fig,f'All twelve months of {year}; same colour scale across all 96 periods. Grey/empty panels mean insufficient coverage, not dry weather.')
    # Monthly planning-area means and counts for all 96 combinations, not just a snapshot year.
    membership=np.column_stack([land_mask(spatial.longitude.to_numpy(),spatial.latitude.to_numpy(),r) for r in rr]);valid=membership.sum(axis=1)==1
    assigned=spatial.copy();assigned['area_index']=[int(np.flatnonzero(membership[i])[0]) if valid[i] else -1 for i in range(len(spatial))]
    assigned[['station_id','year','month','area_index']].to_csv(g.path/'planning_area_assignments.csv',index=False)
    area=assigned[assigned.area_index>=0].groupby(['year','month','area_index']).agg(stations=('station_id','nunique'),mean_mm=('rainfall_total_mm','mean')).reset_index()
    area['area']=area.area_index.map(lambda i:regions[i]['properties'].get('shapeName',str(i)));area.to_csv(g.path/'planning_area_monthly.csv',index=False)
    for month in MONTHS:
        fig,axes=plt.subplots(2,4,figsize=(6.8,3.05),layout='constrained')
        for year,ax in zip(YEARS,axes.flat):
            base(ax);sub=area[(area.year==year)&(area.month==month)].set_index('area_index')
            for idx,polys in enumerate(rr):
                value=sub.loc[idx,'mean_mm'] if idx in sub.index else np.nan
                for poly in polys:
                    for j,ring in enumerate(poly):ax.add_patch(Polygon(np.array(ring)[:,:2],facecolor=('white' if j else cm(norm(value)) if np.isfinite(value) else GREY),edgecolor='white',lw=.2))
            z=assigned[(assigned.year==year)&(assigned.month==month)&(assigned.area_index>=0)];ax.scatter(z.longitude,z.latitude,s=2,c=INK)
            ax.set_title(f'{year} · {len(sub)} areas',fontsize=8)
        fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cm),ax=list(axes.flat),fraction=.025,pad=.01,label='Area station mean (mm)')
        g.save(f'15_regions_month_{month:02d}',fig,f'{calendar.month_name[month]} planning-area station means, not area-weighted rainfall. Grey: no assigned eligible station; dots: contributing locations. Counts and assignments are in the accompanying CSVs.')
    fig,axes=plt.subplots(2,4,figsize=(6.8,3.05),layout='constrained');anorm=Normalize(0,annual.rainfall_total_mm.max())
    for year,ax in zip(YEARS,axes.flat):
        z=annual[annual.year==year];points(ax,z,anorm);ax.set_title(f'{year} · n={len(z)}',fontsize=8)
    fig.colorbar(plt.cm.ScalarMappable(norm=anorm,cmap=cm),ax=list(axes.flat),fraction=.025,pad=.01,label='Observed yearly total (mm)')
    g.save('16_annual_spatial',fig,'Annual ≥95% and every month ≥90% coverage. Unsupported years are displayed explicitly rather than estimated from incomplete totals.')
    # Self-contained Plotly browser, one trace per year-month with all values and coverage in hover.
    import plotly.graph_objects as go
    fig=go.Figure();bx=[];by=[]
    for poly in rings:
        for ring in poly:
            xy=np.array(ring);bx+=xy[:,0].tolist()+[None];by+=xy[:,1].tolist()+[None]
    fig.add_trace(go.Scatter(x=bx,y=by,mode='lines',line={'color':'#A2B2B9','width':1},hoverinfo='skip',showlegend=False))
    options=[]
    for index,(year,month) in enumerate((y,m) for y in YEARS for m in MONTHS):
        z=spatial[(spatial.year==year)&(spatial.month==month)]
        fig.add_trace(go.Scatter(x=z.longitude,y=z.latitude,mode='markers',visible=index==0,showlegend=False,
            marker={'size':10,'color':z.rainfall_total_mm,'colorscale':'YlGnBu','cmin':0,'cmax':norm.vmax,'showscale':True,'colorbar':{'title':'mm'}},
            customdata=np.column_stack([z.station_id,z.rainfall_total_mm.round(2),(100*z.coverage).round(2)]),hovertemplate='%{customdata[0]}<br>%{customdata[1]} mm<br>Coverage %{customdata[2]}%<extra></extra>'))
        label=f'{year}-{month:02d} · {len(z)} qualified stations';vis=[True]+[i==index for i in range(96)]
        options.append({'label':label,'method':'update','args':[{'visible':vis},{'title':label+(' — insufficient data' if z.empty else '')}]})
    fig.update_layout(title=options[0]['label'],template='plotly_white',height=650,updatemenus=[{'buttons':options,'x':0,'y':1.14}],
        xaxis={'range':bounds[:2],'title':'Longitude'},yaxis={'range':bounds[2:],'title':'Latitude','scaleanchor':'x'},margin={'t':100})
    fig.write_html(g.path/'spatial_explorer.html',include_plotlyjs=True)

if __name__=='__main__':main()

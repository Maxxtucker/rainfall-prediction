#!/usr/bin/env python3
"""Render the Task 1 LaTeX template using verified Spark/figure outputs.

Compile the resulting multi-file LaTeX project separately with Tectonic.
"""
import argparse,calendar,json,re
from pathlib import Path
import pandas as pd
from plot_task1_report import read

def main():
 p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--figures',type=Path,required=True);p.add_argument('--output',type=Path,default=Path('report/task1/task1_report.tex'));a=p.parse_args()
 v=json.loads((a.results/'validation.json').read_text());assert v['status']=='passed'
 facts=json.loads((a.figures/'findings.json').read_text());profile=read(a.results,'rainfall_distribution');monthly=read(a.results,'monthly_available_qualified')
 season=monthly.groupby('month').mean_station_rainfall_mm.mean();wet=int(season.idxmax());dry=int(season.idxmin())
 annual=read(a.results,'annual_available_qualified').set_index('year');rows=[]
 for y in range(2017,2025):
  if y in annual.index:
   z=annual.loc[y];rows.append(f'{y} & {int(z.stations)} & {z.mean_station_rainfall_mm:,.1f} & {100*z.mean_coverage:.2f} '+r'\\')
  else:rows.append(f'{y} & 0 & --- & --- '+r'\\')
 supported=', '.join(map(str,sorted(annual.index))); annualtext=f'Only {supported} support this full-year summary under the stated thresholds. '
 for y in sorted(annual.index):
  z=annual.loc[y];annualtext+=f'In {y}, {int(z.stations)} eligible stations have a mean observed total of {z.mean_station_rainfall_mm:,.1f} mm. '
 annualtext+='These values use different station sets and therefore do not by themselves establish a like-for-like ordering of national annual rainfall.'
 pairs=read(a.results,'monthly_pair_comparisons');eligible=pairs[(pairs.year_b==pairs.year_a+1)&(pairs.stations>=5)]
 # A fixed, transparent example rather than selecting the largest observed contrast.
 sample=eligible[(eligible.year_a==2023)&(eligible.month==12)]
 if sample.empty:sample=eligible.sort_values(['year_a','month']).head(1)
 r=sample.iloc[0];word='higher' if r.change_percent>=0 else 'lower'
 pairtext=f'For example, {calendar.month_name[int(r.month)]} {int(r.year_b)} is {abs(r.change_percent):.1f}\\% {word} than the same month in {int(r.year_a)} among their {int(r.stations)} common stations (means {r.mean_b_mm:.1f} versus {r.mean_a_mm:.1f} mm).'
 ap=read(a.results,'annual_pair_comparisons');parts=[]
 for r in ap.sort_values(['year_a','year_b']).itertuples():
  parts.append(f'{int(r.year_a)}--{int(r.year_b)} has {int(r.stations)} common stations and a mean within-station change of {r.mean_change_mm:+.1f} mm ({r.change_percent:+.1f}\\%).')
 annualpair=' '.join(parts) if parts else 'No supported common-station annual pair is available.'
 hours=read(a.results,'hourly_available').groupby('hour')[['wet_intervals','observed_intervals']].sum();freq=100*hours.wet_intervals/hours.observed_intervals
 hi=int(freq.idxmax());lo=int(freq.idxmin());hourtext=f'Pooling valid intervals across the qualified month sample, wet frequency peaks at {hi:02d}:00--{hi:02d}:59 ({freq[hi]:.2f}\\%) and is lowest at {lo:02d}:00--{lo:02d}:59 ({freq[lo]:.2f}\\%).'
 audit=read(a.results,'daily_record_audit');aug=audit[audit.date.str.startswith('2018-08')]
 spatial=read(a.results,'spatial_month_available');dec=spatial[spatial.month==12];counts=dec.groupby('year').station_id.nunique()
 spatialtext=f'December maps retain between {int(counts.min())} and {int(counts.max())} qualified stations per year, providing geographical support throughout the study period. '
 # Describe one fixed latest-year monthly comparison, without selecting a wettest-year story.
 ss=dec[dec.year==2024].sort_values('rainfall_total_mm');low=ss.iloc[0];high=ss.iloc[-1]
 spatialtext+=f'In December 2024, qualified station totals range from {low.rainfall_total_mm:.1f} mm at {low.station_id} to {high.rainfall_total_mm:.1f} mm at {high.station_id}. This spread shows spatial heterogeneity within the observed network, not an area-weighted regional contrast.'
 sc=pd.read_csv(a.figures/'sensitivity_checks.csv');sen=[]
 for r in sc.itertuples():sen.append(f'Comparing {r.threshold:.0%} with 90% on {r.shared_year_months} shared year-months gives a median absolute change in monthly mean amount of {r.median_absolute_change_percent:.2f}% and a maximum of {r.max_absolute_change_percent:.2f}%.'.replace('%',r'\%'))
 replacements={'OBS':f'{facts["observations"]:,}','STATIONS':str(facts['stations']),'ZERO':f'{100*facts["zero_fraction"]:.2f}',
 'ELIGIBLE':str(facts['qualified_year_months']),'MAX':f'{profile.max_mm.max():.1f}','EMPTY':str(facts['network_empty_raw_days']),
 'AUGRAW':f'{int(aug.raw_records.sum()):,}','RAW':f'{facts["raw_records"]:,}','REMOVED':str(facts['raw_records']-facts['observations']),
 'PARSE':str(facts['unparsed_raw_timestamps']),'WETMONTH':calendar.month_name[wet],'DRYMONTH':calendar.month_name[dry],
 'WETMM':f'{season[wet]:.1f}','DRYMM':f'{season[dry]:.1f}','PAIRTEXT':pairtext,'ANNUALROWS':'\n'.join(rows),
 'ANNUALTEXT':annualtext,'ANNUALPAIR':annualpair,'HOURTEXT':hourtext,'SPATIALTEXT':spatialtext,'SENSTEXT':' '.join(sen)}
 template=Path('report/task1/report_template.tex').read_text()
 for k,value in replacements.items():template=template.replace('@@'+k+'@@',value)
 assert not re.search(r'@@[A-Z]+@@',template),'Unfilled template'
 # Relative path makes the report portable with its associated repository figures.
 import os
 rel=os.path.relpath(a.figures.resolve(),a.output.parent.resolve()).replace(os.sep,'/')+'/'
 template=template.replace('../../figures/task1-v5-report/',rel)
 a.output.write_text(template);print(a.output)
 (a.output.parent/'report_facts.json').write_text(json.dumps(replacements,indent=2))
if __name__=='__main__':main()

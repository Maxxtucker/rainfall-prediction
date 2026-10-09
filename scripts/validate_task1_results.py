#!/usr/bin/env python3
"""Independently verify all-month Spark tables using small pandas aggregates."""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from plot_task1_report import read

def main():
 p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);a=p.parse_args();checks=[]
 m=read(a.results,'station_month');q=m[m.coverage>=.9];c=read(a.results,'coverage')
 assert len(c)==96 and not c.duplicated(['year','month']).any();checks.append('96 unique year-month coverage rows')
 assert not m.duplicated(['station_id','year','month']).any();assert len(m)==m.station_id.nunique()*96
 assert m.loc[m.observed_intervals==0,'rainfall_total_mm'].isna().all();checks.append('calendar skeleton preserves missing rainfall as null')
 # Timestamp snapping may move a few midnight observations between adjacent dates;
 # daily raw >= clean is therefore not a valid invariant. Reconcile global counts.
 profile=read(a.results,'rainfall_distribution');audit=read(a.results,'daily_record_audit');raw=read(a.results,'raw_quality')
 assert int(m.observed_intervals.sum())==int(profile.observations.sum())==int(audit.clean_records.sum())
 assert int(raw.raw_records.iloc[0])==int(audit.raw_records.sum())+int(raw.unparsed_timestamps.iloc[0]);assert int(audit.raw_records.sum())>=int(audit.clean_records.sum());checks.append('raw, daily, monthly and annual profile count reconciliation')
 available=read(a.results,'monthly_available_qualified');expected=q.groupby(['year','month']).rainfall_total_mm.mean();actual=available.set_index(['year','month']).mean_station_rainfall_mm
 np.testing.assert_allclose(actual.sort_index(),expected.sort_index(),rtol=1e-9);checks.append('monthly means reproduced independently')
 annual=read(a.results,'annual_station_qualified');assert (annual.coverage>=.95).all() and (annual.min_month_coverage>=.9).all();checks.append('annual inclusion requires annual and every-month coverage')
 hours=read(a.results,'hourly_available');assert int(hours.observed_intervals.sum())==int(q.observed_intervals.sum());checks.append('hourly analysis uses all qualified month observations')
 pairs=read(a.results,'monthly_pair_comparisons');stable=q[(q.latitude_span<=.005)&(q.longitude_span<=.005)]
 # Check every pair, including non-adjacent years and small station panels.
 for r in pairs.itertuples():
  aa=stable[(stable.year==r.year_a)&(stable.month==r.month)];bb=stable[(stable.year==r.year_b)&(stable.month==r.month)]
  ab=aa.merge(bb,on='station_id',suffixes=('_a','_b'))
  ab=ab[(abs(ab.latitude_a-ab.latitude_b)<=.005)&(abs(ab.longitude_a-ab.longitude_b)<=.005)]
  assert len(ab)==r.stations
  np.testing.assert_allclose((ab.rainfall_total_mm_b-ab.rainfall_total_mm_a).mean(),r.mean_change_mm,atol=1e-8)
 checks.append('all paired year-month differences independently matched and reproduced')
 s=read(a.results,'coverage_sensitivity_results')
 for cut in [.8,.9,.95]:
  want=m[m.coverage>=cut].groupby(['year','month']).rainfall_total_mm.mean().sort_index()
  got=s[s.threshold==cut].set_index(['year','month']).mean_station_rainfall_mm.sort_index()
  np.testing.assert_allclose(want,got,rtol=1e-9)
 checks.append('rainfall results at all three coverage cutoffs reproduced')
 result={'status':'passed','checks':checks,'rows':int(m.observed_intervals.sum())}
 (a.results/'validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()

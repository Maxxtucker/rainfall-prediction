#!/usr/bin/env python3
"""Audit observation-to-update delays from saved clean Parquet; no cloud compute.

Update metadata are availability proxies, not an archive of first publication.
Quantiles are exact linear-interpolated quantiles of integer-nanosecond delays.
"""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re

import numpy as np
import pyarrow.parquet as pq


def summarize(histogram, total):
    ordered = sorted(histogram.items())
    n = sum(histogram.values())
    def quantile(q):
        if not n:
            return None
        rank = (n - 1) * q
        lo, hi = math.floor(rank), math.ceil(rank)
        values = []
        for target in (lo, hi):
            cumulative = 0
            for value, count in ordered:
                cumulative += count
                if cumulative > target:
                    values.append(value)
                    break
        return (values[0] + (values[1] - values[0]) * (rank - lo)) / 60e9
    return dict(observations=total, known_updates=n, missing_updates=total-n,
                median_minutes=quantile(.5), p90_minutes=quantile(.9), p99_minutes=quantile(.99),
                negative_delay_count=sum(c for v,c in ordered if v < 0),
                fraction_known_within_10m=sum(c for v,c in ordered if v <= 600e9)/n if n else None,
                fraction_known_over_10m=sum(c for v,c in ordered if v > 600e9)/n if n else None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args=parser.parse_args()
    histograms=defaultdict(Counter); totals=Counter(); files=[]
    columns=['timestamp','update_timestamp','reading_update_timestamp','availability_missing']
    for path in sorted(args.clean.rglob('*.parquet')):
        match=re.search(r'year=(\d{4})',str(path))
        if not match:
            raise ValueError(f'Missing year partition: {path}')
        year=int(match.group(1)); files.append(str(path.relative_to(args.clean)))
        for batch in pq.ParquetFile(path).iter_batches(columns=columns, batch_size=131072):
            arrays=[batch.column(i).to_numpy(zero_copy_only=False) for i in range(3)]
            valid=(~np.isnat(arrays[0]) & ~np.isnat(arrays[1]) & ~np.isnat(arrays[2]))
            flags=batch.column(3).to_pylist()
            valid &= np.array([v is False for v in flags])
            totals[year]+=len(batch)
            delay=(np.maximum(arrays[1][valid],arrays[2][valid])-arrays[0][valid]).astype('timedelta64[ns]').astype(np.int64)
            values,counts=np.unique(delay,return_counts=True)
            histograms[year].update({int(v):int(c) for v,c in zip(values,counts)})
    def pooled(years):
        h=Counter()
        for year in years:
            h.update(histograms[year])
        return summarize(h,sum(totals[y] for y in years))
    result={'source':'gs://rainfall-project-511007-rainfall-maxiaoxiao/project/steps/clean-all-v1/clean',
            'definition':'max(update_timestamp, reading_update_timestamp) - aligned observation timestamp',
            'interpretation':'Recorded update delay; not independently observed first-publication latency.',
            'quantiles':'Exact linear interpolation, known-update records only; negative delays retained and counted.',
            'files_read':len(files),'by_year':{str(y):summarize(histograms[y],totals[y]) for y in sorted(totals)},
            'training_2017_2021':pooled(range(2017,2022)), 'all_2017_2024':pooled(range(2017,2025))}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()

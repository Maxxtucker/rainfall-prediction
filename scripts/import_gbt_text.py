#!/usr/bin/env python3
"""Parse concatenated JSON metadata and CSV blocks from a teammate text export."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def parse_export(text):
    metadata,end=json.JSONDecoder().raw_decode(text.lstrip())
    if metadata.get('feature_mode')!='calendar_risk_v2' or metadata.get('train_fraction')!=.15:
        raise ValueError('Expected calendar 15% GBT metadata')
    tables=[];header=None;rows=[]
    for line in text.lstrip()[end:].splitlines()+['END']:
        line=line.strip()
        if line.startswith('threshold,n,prevalence,'):
            if rows: tables.append(pd.read_csv(io.StringIO(header+'\n'+'\n'.join(rows))))
            header=line;rows=[]
        elif header and line and line[0] in '-0123456789' and len(line.split(','))==len(header.split(',')):
            rows.append(line)
        elif rows:
            tables.append(pd.read_csv(io.StringIO(header+'\n'+'\n'.join(rows))));rows=[];header=None
    if not tables:raise ValueError('No metric blocks')
    frame=pd.concat(tables,ignore_index=True)
    if frame.duplicated(['model','threshold','cutoff_kind']).any():raise ValueError('Duplicate metric blocks')
    if 'gbt' not in set(frame.model):raise ValueError('No GBT metrics')
    return metadata,frame


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True,type=Path);args=p.parse_args()
    metadata,frame=parse_export(args.input.read_text())
    root=ROOT/'outputs/steps/gbt-sampling-20261014-run01/calendar/sample15'
    if root.exists():raise ValueError('15% text export already imported')
    (root/'metadata').mkdir(parents=True);(root/'metadata/part-00000').write_text(json.dumps(metadata)+'\n')
    for model,rows in frame.groupby('model'):
        dest=root/'metrics'/model;dest.mkdir(parents=True);rows.to_csv(dest/'part-00000.csv',index=False)
    (root/'source-export.txt').write_bytes(args.input.read_bytes())
    (root/'import_manifest.json').write_text(json.dumps({'source_file':args.input.name,'sha256':hashlib.sha256(args.input.read_bytes()).hexdigest(),
        'evidence':'Metadata and per-threshold metrics only; no pipeline or daily errors supplied.',
        'threshold_order':'Unlabelled diagnostic blocks are preserved in the source text but not assigned to models.'},indent=2)+'\n')
    print(root)


if __name__=='__main__':main()

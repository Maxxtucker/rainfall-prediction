#!/usr/bin/env python3
"""Safely import supplied experiment archives without replacing original models."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def safe_target(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Unsafe archive member: ' + name)
    return path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gbt', type=Path, required=True)
    p.add_argument('--full', type=Path, required=True)
    p.add_argument('--summary', type=Path, required=True)
    args=p.parse_args()
    gbt=ROOT/'outputs/steps/gbt-sampling-20261014-run01'
    full=ROOT/'outputs/steps/task2-full-20261012'
    if gbt.exists() or full.exists():
        raise ValueError('Imported result paths exist; refusing to overwrite')
    with tempfile.TemporaryDirectory() as temp:
        base=Path(temp)
        with zipfile.ZipFile(args.gbt) as archive:
            for item in archive.infolist():
                target=safe_target(base/'gbt',item.filename)
                if item.is_dir(): continue
                if (item.external_attr>>16)&0o170000==0o120000: raise ValueError('Symlink in ZIP')
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(item))
        with tarfile.open(args.full) as archive:
            for item in archive:
                target=safe_target(base/'full',item.name)
                if item.isdir(): continue
                if not item.isfile(): raise ValueError('Nonregular TAR member')
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.extractfile(item).read())
        shutil.copytree(base/'gbt/outputs/gbt-sampling-20261014-run01/results',gbt)
        full.mkdir();shutil.copytree(base/'full/models',full/'models')
        (full/'records').mkdir()
        for name in ('cluster.json','short.json','calendar.json'):
            shutil.copy2(base/'full/records'/name,full/'records'/name)
        shutil.copy2(base/'full/acceptance.json',full/'acceptance.json')
    shutil.copy2(args.summary,gbt/'teammate-summary.md')
    manifest={'imported_on':'2026-10-15','archives':[{ 'name':x.name,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in (args.gbt,args.full,args.summary)],
              'original_models_preserved':True,'gbt15_evidence':'Summary only; no 15% pipeline or raw metrics supplied in these archives.',
              'excluded':'Raw environment file and driver logs; archives are not copied into the repository.'}
    (gbt/'import_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (full/'import_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(gbt);print(full)


if __name__=='__main__': main()

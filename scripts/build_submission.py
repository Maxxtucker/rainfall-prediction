#!/usr/bin/env python3
"""Validate and package the final report, source, real models and supporting evidence.

No cloud access, training or report compilation is performed. Run from any directory.
"""
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
TOP = 'rainfall-submission'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def json_part(directory):
    parts = sorted(directory.glob('part-*'))
    if len(parts) != 1:
        raise ValueError(f'Expected one final JSON part: {directory}')
    return json.loads(parts[0].read_text())


def main():
    required = ['README.md', 'requirements.txt', 'report/project_report.pdf',
                'report/project_report.tex', 'report/project_report.template.tex',
                'report/task2/analysis_facts.json', 'outputs/steps/task1-v5/validation.json',
                'outputs/steps/task2-dual-v2/local_model_verification.json']
    for name in required:
        if not (ROOT / name).is_file():
            raise FileNotFoundError(name)
    text = (ROOT / 'report/project_report.tex').read_text()
    if '@@' in text:
        raise ValueError('Unfilled report-generation marker')
    used = re.findall(r'\\plot\{([^}]+)\}', text)
    for figure in used:
        if not any((ROOT / 'figures' / folder / (figure + '.pdf')).is_file()
                   for folder in ['project-report', 'task1-v5-report', 'task2-report']):
            raise FileNotFoundError('Missing report vector: ' + figure)
    if json.loads((ROOT / 'outputs/steps/task1-v5/validation.json').read_text())['status'] != 'passed':
        raise ValueError('Task 1 independent validation did not pass')
    model_root = ROOT / 'outputs/steps/task2-dual-v2/models'
    for mode in ['calendar', 'short_term']:
        base = model_root / mode
        meta = json_part(base / 'metadata')
        if not meta.get('test_evaluation_completed'):
            raise ValueError('Incomplete test evaluation: ' + mode)
        for folder in ['pipeline', 'binary_pipeline', 'stations', 'empirical_support',
                       'climatology', 'global_climatology', 'metrics/test_metrics']:
            if not (base / folder).is_dir() or not any((base / folder).rglob('part-*')):
                raise FileNotFoundError(base / folder)
    verified = json.loads((ROOT / 'outputs/steps/task2-dual-v2/local_model_verification.json').read_text())
    if not verified.get('passed'):
        raise ValueError('Saved model verification did not pass')
    selections = ['assets', 'cloud', 'config', 'docs', 'figures', 'jobs', 'report',
                  'scripts', 'src', 'tests', 'outputs/steps/task1-v5',
                  'outputs/steps/task2-dual-v1', 'outputs/steps/task2-dual-v2']
    sensitivity = ROOT / 'outputs/steps/rf-sensitivity-20261010'
    if sensitivity.exists():
        if not json_part(sensitivity / 'completion').get('complete'):
            raise ValueError('Incomplete RF sensitivity experiment')
        if not (sensitivity / 'local_model_verification.json').is_file():
            raise ValueError('RF sensitivity models have not been verified locally')
        if not json.loads((sensitivity / 'local_model_verification.json').read_text()).get('passed'):
            raise ValueError('RF sensitivity model verification failed')
        selections.append(str(sensitivity.relative_to(ROOT)))
    paths = [ROOT / n for n in ['README.md', '.gitignore', 'requirements.txt',
                              'requirements-local.txt', 'requirements-plot.txt',
                              'requirements-report.txt']]
    for selection in selections:
        paths.extend(p for p in (ROOT / selection).rglob('*') if p.is_file())
    def include(path):
        rel = path.relative_to(ROOT)
        return not (path.is_symlink() or '__pycache__' in rel.parts or '.qa' in rel.parts
                    or path.suffix in {'.pyc', '.svg', '.log', '.aux', '.out', '.xdv', '.synctex'}
                    or path.name in {'.DS_Store', 'env.sh', 'gcloud.json'}
                    or 'models-pre-final-sync' in rel.parts
                    or ('task2-dual-v1' in rel.parts and 'features' in rel.parts))
    paths = sorted(set(p for p in paths if include(p)))
    records = [{'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size,
                'sha256': sha256(p)} for p in paths]
    manifest = {'format': 1, 'project': 'DSA5208 Singapore rainfall 2017-2024',
                'report': 'report/project_report.pdf', 'file_count': len(records),
                'uncompressed_bytes': sum(r['bytes'] for r in records),
                'group_details': 'Intentionally blank; fill before final Canvas submission',
                'excluded': ['local cloud/env.sh', 'credentials and local runtime configuration',
                             'raw CSV/clean Parquet/large feature caches', 'old runs and caches',
                             'duplicate SVG exports'], 'files': records}
    dist = ROOT / 'dist';dist.mkdir(exist_ok=True)
    archive = dist / 'rainfall-submission.zip'
    with ZipFile(archive, 'w', ZIP_DEFLATED, compresslevel=6) as output:
        for p in paths:
            output.write(p, TOP + '/' + str(p.relative_to(ROOT)))
        output.writestr(TOP + '/SUBMISSION_MANIFEST.json', json.dumps(manifest, indent=2))
    with ZipFile(archive) as output:
        bad = output.testzip()
        if bad:
            raise ValueError('Archive CRC failure: ' + bad)
        for record in records:
            data = output.read(TOP + '/' + record['path'])
            if hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('Archive hash mismatch: ' + record['path'])
    summary = {'archive': str(archive.relative_to(ROOT)), 'bytes': archive.stat().st_size,
               'sha256': sha256(archive), 'packaged_files': len(records),
               'archive_hash_verification': 'passed'}
    (dist / 'rainfall-submission.sha256.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

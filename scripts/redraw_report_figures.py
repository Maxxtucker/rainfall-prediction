#!/usr/bin/env python3
"""Refresh the two edited report figures from saved summary tables."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / 'figures/project-report'
    commands = [
        ('plot_report_reliability.py', '--input', ROOT / 'outputs/steps/task2-dual-v2/comparison/reliability',
         '--output', output / '20_reliability'),
        ('plot_report_december.py', '--input', ROOT / 'outputs/steps/task1-v5/eda/spatial_month_available',
         '--boundary', ROOT / 'assets/singapore.geojson', '--output', output / '13_spatial_month_12'),
    ]
    for script, *arguments in commands:
        subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *map(str, arguments)], check=True)


if __name__ == '__main__':
    main()

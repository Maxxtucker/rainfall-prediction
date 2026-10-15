#!/usr/bin/env python3
"""Compatibility entry point; use analyze_task2_experiments.py for new work."""
from analyze_task2_experiments import (
    FULL, GBT, ORIGINAL, Q, ROOT, collect_facts, compare_cohort, csv,
    default_metrics, document, main, reconcile_daily, reported15, summary_record,
)


if __name__ == '__main__':
    main()

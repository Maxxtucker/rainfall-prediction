#!/usr/bin/env python3
"""Run semantic correctness checks under the cluster's real Spark runtime.

Submit with rainfall.zip (containing rainfall/ and tests/) as --py-files. A
failure exits non-zero, so the cloud workflow stops before expensive processing.
All records created by these tests are fabricated.
"""
import sys
import unittest


def main():
    suite = unittest.defaultTestLoader.loadTestsFromNames([
        "tests.test_spark_semantics",
        "tests.test_probability",
        "tests.test_calendar_risk",
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

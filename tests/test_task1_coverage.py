"""Exercise the public coverage-only CLI without Spark or a comparison panel."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


class CoveragePlotTests(unittest.TestCase):
    def test_legacy_tables_plot_gaps_without_turning_them_into_dry_weather(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            # One active station, one inactive station and a fully missing month.
            pd.DataFrame([
                ("A", 2018, 8, 600, .075), ("B", 2018, 8, 0, 0.),
                ("A", 2018, 9, 0, 0.), ("B", 2018, 9, 0, 0.),
            ], columns=["station_id", "year", "month", "observed_intervals", "coverage"]).to_csv(base / "station_month.csv", index=False)
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/plot_task1.py"),
                "--results", str(base), "--output", str(base / "figures"),
                "--only", "coverage"], capture_output=True, text=True,
                env={**os.environ, "MPLCONFIGDIR": str(base / "mpl")})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = pd.read_csv(base / "figures/monthly_coverage_summary.csv")
            august = summary[(summary.year == 2018) & (summary.month == 8)].iloc[0]
            september = summary[(summary.year == 2018) & (summary.month == 9)].iloc[0]
            self.assertAlmostEqual(august.median_coverage, .075)
            self.assertEqual(august.active_stations, 1)
            self.assertTrue(pd.isna(september.median_coverage))
            self.assertEqual(len(summary), 96)
            for extension in ("png", "svg"):
                self.assertTrue((base / f"figures/08b_monthly_coverage.{extension}").is_file())
            manifest = json.loads((base / "figures/figure_manifest.json").read_text())
            self.assertEqual(manifest["stage"], "coverage")


if __name__ == "__main__":
    unittest.main()

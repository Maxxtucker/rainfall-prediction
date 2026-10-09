"""Local spatial safeguards; independent of Spark and fabricated weather scores."""
import sys
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from plot_task1 import interpolate, land_mask


class SpatialSafeguardsTests(unittest.TestCase):
    def setUp(self):
        self.rings = [[[[103.7, 1.2], [104., 1.2], [104., 1.5], [103.7, 1.5], [103.7, 1.2]]]]
        self.stations = pd.DataFrame({"longitude": [103.8, 103.9, 103.8, 103.9],
            "latitude": [1.3, 1.3, 1.4, 1.4], "rainfall_total_mm": [100., 100., 100., 100.]})

    def test_constant_field_and_no_extrapolation(self):
        x, y = np.array([103.85, 103.75]), np.array([1.35, 1.35])
        values = interpolate(self.stations, x, y, self.rings, 10)
        self.assertAlmostEqual(values[0], 100.)
        self.assertTrue(np.isnan(values[1]))  # On land, but outside station hull.

    def test_distance_limit_masks_even_inside_hull(self):
        values = interpolate(self.stations, np.array([103.85]), np.array([1.35]), self.rings, 1)
        self.assertTrue(np.isnan(values[0]))

    def test_holes_are_not_rainfall_surfaces(self):
        rings = self.rings[0] + [[[103.84, 1.34], [103.86, 1.34], [103.86, 1.36], [103.84, 1.36], [103.84, 1.34]]]
        result = land_mask(np.array([103.85, 103.81]), np.array([1.35, 1.31]), [rings])
        self.assertEqual(result.tolist(), [False, True])

    def test_sparse_and_collinear_locations_do_not_interpolate(self):
        self.assertIsNone(interpolate(self.stations.iloc[:2], np.array([103.85]), np.array([1.35]), self.rings, 10))
        collinear = self.stations.iloc[:3].copy(); collinear["latitude"] = 1.3
        self.assertIsNone(interpolate(collinear, np.array([103.85]), np.array([1.3]), self.rings, 10))


if __name__ == "__main__":
    unittest.main()

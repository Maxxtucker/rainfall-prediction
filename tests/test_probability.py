"""Probability contracts that run without Spark or the annual datasets."""
import math
import unittest

from rainfall.probability import N_CLASSES, survival_weights


def empirical(values, counts=None):
    counts = counts or [1] * len(values)
    n = sum(counts)
    cumulative = []
    total = 0
    for count in counts:
        total += count
        cumulative.append(total / n)
    return {"amounts": values, "counts": counts, "cumulative": cumulative, "n": n}


class ProbabilityTests(unittest.TestCase):
    def setUp(self):
        self.supports = [
            empirical([0.0], [4]),
            empirical([0.2, 0.4, 1.0], [1, 2, 1]),
            empirical([1.2, 2.0]),
            empirical([3.0, 5.0]),
            empirical([6.0, 10.0]),
            empirical([12.0, 20.0]),
            empirical([21.0, 40.0]),
        ]
        self.mass = [0.50, 0.15, 0.10, 0.10, 0.07, 0.05, 0.03]

    def probability(self, threshold, mass=None):
        return sum(p * w for p, w in zip(mass or self.mass,
                   survival_weights(self.supports, threshold)))

    def test_strict_exceedance_excludes_equal_amount(self):
        self.assertEqual(survival_weights(self.supports, 0.0)[0], 0.0)
        self.assertAlmostEqual(survival_weights(self.supports, 0.2)[1], 0.75)
        self.assertAlmostEqual(survival_weights(self.supports, 0.4)[1], 0.25)
        self.assertEqual(survival_weights(self.supports, 1.0)[1], 0.0)
        self.assertAlmostEqual(self.probability(0.0), 0.5)

    def test_mixture_is_monotone_and_bounded(self):
        # Test points include exact support values, boundaries, and arbitrary q.
        thresholds = [-2.0, 0.0, 0.001, 0.2, 0.35, 0.4, 1.0, 1.7,
                      2.0, 5.0, 7.25, 10.0, 20.0, 21.0, 40.0, 1000.0]
        probabilities = [self.probability(q) for q in thresholds]
        self.assertTrue(all(0 <= p <= 1 for p in probabilities))
        self.assertTrue(all(a + 1e-12 >= b for a, b in zip(probabilities, probabilities[1:])))
        self.assertAlmostEqual(probabilities[0], 1.0)
        self.assertEqual(probabilities[-1], 0.0)

    def test_bin_edge_tail_mass(self):
        # At q=5, only amount classes wholly above 5 can contribute mass.
        self.assertAlmostEqual(self.probability(5.0), sum(self.mass[4:]))
        self.assertAlmostEqual(self.probability(20.0), self.mass[6])

    def test_empty_training_class_has_no_survival_mass(self):
        self.supports[-1] = empirical([])
        weights = survival_weights(self.supports, 20.0)
        self.assertEqual(len(weights), N_CLASSES)
        self.assertEqual(weights[-1], 0.0)

    def test_nonfinite_thresholds_fail(self):
        for threshold in [math.nan, math.inf, -math.inf]:
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValueError):
                    survival_weights(self.supports, threshold)


if __name__ == "__main__":
    unittest.main()

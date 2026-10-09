"""Pure-Python threshold survival calculations used by Spark scoring.

No Spark installation is needed to check strict exceedance and monotonicity.
The support table is estimated from training observations, never test labels.
"""
from bisect import bisect_right
import math

AMOUNT_EDGES = [0.0, 1.0, 2.0, 5.0, 10.0, 20.0]
N_CLASSES = len(AMOUNT_EDGES) + 1


def survival_weights(supports, threshold):
    """Return P(Y > threshold | amount bin) using each empirical support.

    ``bisect_right`` removes all mass equal to the threshold. Thus the event is
    strictly greater, including at zero and at every amount-bin boundary.
    """
    if not math.isfinite(threshold):
        raise ValueError("Rainfall threshold must be a finite number.")
    if threshold < 0:
        return [1.0] * N_CLASSES
    result = []
    for item in supports:
        index = bisect_right(item["amounts"], threshold)
        if not item["n"]:
            result.append(0.0)
        elif index == 0:
            result.append(1.0)
        else:
            result.append(max(0.0, 1.0 - item["cumulative"][index - 1]))
    return result

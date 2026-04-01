"""Test engine speed."""

import numba as nb
import numpy as np


@nb.njit(fastmath=True, cache=False)
def test_engine_speed(active_part: np.ndarray) -> np.int64:
    """Test engine speed."""
    prices_sum = np.int64(0)
    for i in range(active_part.size):
        prices_sum += active_part[i]
    return prices_sum

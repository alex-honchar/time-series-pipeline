"""Compute EMA and variance state for correct subsequent segment processing."""
import numba as nb
import numpy as np


@nb.njit(fastmath=True, cache=False)
def run_warmup(
    warmup_part: np.ndarray,
    windows: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Warm up EMA and variance state over the warmup segment."""
    first_price = np.float64(warmup_part[0])
    windows_count = windows.size

    alphas = 2.0 / (windows + 1.0)
    betas = 1.0 - alphas

    emas = np.full(windows_count, first_price, dtype=np.float64)
    variances = np.zeros(windows_count, dtype=np.float64)

    for i in range(1, warmup_part.size):
        float_price = np.float64(warmup_part[i])
        for j in range(windows_count):
            diff = float_price - emas[j]
            emas[j] += alphas[j] * diff
            variances[j] = betas[j] * variances[j] + alphas[j] * diff * diff

    return emas, variances

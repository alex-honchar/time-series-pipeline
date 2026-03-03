"""Run warmup and active segment calculations."""

import numba as nb
import numpy as np

T_ZERO = 10  # seconds
T_MAX = 86400
EXPONENTA = 1.5
bins = []

while T_ZERO <= T_MAX:
    bins.append(T_ZERO)
    T_ZERO *= EXPONENTA
    T_ZERO = int(T_ZERO)

n_bins = len(bins)
print(f"MAX {max(bins)} / MIN {min(bins)} / LEN {len(bins)}")

time_bins = np.asarray(bins, dtype=np.int32)


my_dtype = np.dtype(
    [
        ("average_move", np.float32, (n_bins,)),
        ("count", np.int32),
    ],
    align=True,
)

stats = np.zeros(shape=(61, 61, 61, 61), dtype=my_dtype)


@nb.njit(fastmath=True, cache=True)  # WIP
def do_warmup(
    warmup_part: np.ndarray, windows: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Warm up EMA and variance state over the warmup segment."""
    first_price = np.float64(warmup_part[0])

    n_windows = windows.size

    alphas = 2.0 / (windows + 1.0)
    anti_alphas = 1.0 - alphas

    emas = np.full(n_windows, first_price, dtype=np.float64)
    variances = np.zeros(n_windows, dtype=np.float64)

    for i in range(1, warmup_part.size):
        float_price = np.float64(warmup_part[i])
        for j in range(n_windows):
            diff = float_price - emas[j]
            emas[j] += alphas[j] * diff
            variances[j] = anti_alphas[j] * variances[j] + alphas[j] * diff * diff

    return emas, variances


@nb.njit(fastmath=True, cache=True)  # WIP
def do_active(
    active_part: np.ndarray,
    windows: np.ndarray,
    emas: np.ndarray,
    variances: np.ndarray,
) -> np.ndarray:
    """Calculate active-segment z-score bins."""
    n_windows = windows.size
    alphas = 2.0 / (windows + 1.0)
    anti_alphas = 1.0 - alphas
    zscores = np.zeros(n_windows, dtype=np.int32)

    for i in range(active_part.size):
        float_price = np.float64(active_part[i])
        for j in range(n_windows):
            diff = float_price - emas[j]
            emas[j] += alphas[j] * diff
            variances[j] = anti_alphas[j] * variances[j] + alphas[j] * diff * diff

            zscores[j] = (((diff) / np.sqrt((variances[j] + 1e-9))) * 2) + 30

    return zscores

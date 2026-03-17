"""Process segment and update statistics."""

import numba as nb
import numpy as np

from config import Config

cfg = Config()

TIME_BINS = cfg.TIME_BINS

Z_HALF = cfg.Z_HALF
Z_DUMMY = cfg.Z_DUMMY
ZSCORE_STEP = cfg.ZSCORE_STEP

EMA_ALPHA = cfg.EMA_ALPHA
RING_BUFFER_DTYPE = cfg.RING_BUFFER_DTYPE


@nb.njit(fastmath=True, cache=False)
def run_passive_segment(
    active_part: np.ndarray,
    windows: np.ndarray,
    emas: np.ndarray,
    variances: np.ndarray,
    stats: np.ndarray,
) -> np.ndarray:
    """Process active ticks and update statistics."""
    max_horizon = TIME_BINS[-1]
    windows_count = windows.size
    zscores = np.zeros(windows_count, dtype=np.int32)

    alphas = 2.0 / (windows + 1.0)
    betas = 1.0 - alphas

    rb_size = max_horizon + 1
    rb_cursor = np.int32(0)
    ring_buffer = np.empty(rb_size, dtype=RING_BUFFER_DTYPE)
    init_ring_buffer(ring_buffer, rb_size, windows_count)

    for i in range(active_part.size):
        float_price = np.float64(active_part[i])
        log_price = np.log(float_price)

        for j in range(windows_count):
            update_zscore(float_price, emas, variances, zscores, alphas, betas, j)

        for x_coord, time_bin in enumerate(TIME_BINS):
            update_bin_stats(
                log_price,
                ring_buffer,
                rb_cursor,
                time_bin,
                rb_size,
                stats,
                x_coord
            )

        z1, z2, z3, z4 = zscores
        write_key_to_buffer(z1, z2, z3, z4, log_price, ring_buffer, rb_cursor)

        rb_cursor = (rb_cursor + 1) % rb_size

    return stats

@nb.njit(fastmath=True, cache=False)
def init_ring_buffer(
    ring_buffer: np.ndarray, rb_size: np.int32, windows_count: np.int64
) -> None:
    """Fill rolling buffer with dummy keys to prevent index errors."""
    for buffer_slot in range(rb_size):
        ring_buffer[buffer_slot].price = 0.1
        for key_idx in range(windows_count):
            ring_buffer[buffer_slot].key[key_idx] = Z_DUMMY

@nb.njit(fastmath=True, cache=False)
def update_zscore(
    float_price: np.float64,
    emas: np.ndarray,
    variances: np.ndarray,
    zscores: np.ndarray,
    alphas: np.ndarray,
    betas: np.ndarray,
    j: np.int32
) -> None:
    """Update EMA and variance, calculate and bin Z-score."""
    diff = float_price - emas[j]
    emas[j] += alphas[j] * diff
    zscore_j = diff / np.sqrt(variances[j]+1e-9)
    scaled = np.int32(np.abs(zscore_j)*ZSCORE_STEP)
    offset = np.int32(np.sign(zscore_j) * np.minimum(Z_HALF, scaled))
    zscores[j] = Z_HALF + offset
    variances[j] = betas[j] * variances[j] + alphas[j] * diff * diff

@nb.njit(fastmath=True, cache=False)
def update_bin_stats(
    log_price: np.float64,
    ring_buffer: np.ndarray,
    rb_cursor: np.int32,
    time_bin: np.int32,
    rb_size: np.int32,
    stats: np.ndarray,
    x_coord: np.int32,
) -> None:
    """Update price-delta for the buffered key at the current time bin."""
    current_bin = (rb_cursor - time_bin + rb_size) % rb_size
    z1, z2, z3, z4 = ring_buffer[current_bin].key
    past_log = ring_buffer[current_bin].price

    log_diff = log_price-past_log
    stats[z1, z2, z3, z4].ema[x_coord] += EMA_ALPHA * (
        (log_diff) - stats[z1, z2, z3, z4].ema[x_coord]
    )
    stats[z1, z2, z3, z4].count[x_coord] += 1

@nb.njit(fastmath=True, cache=False)
def write_key_to_buffer(
    z1: np.int32,
    z2: np.int32,
    z3: np.int32,
    z4: np.int32,
    log_price: np.float64,
    ring_buffer: np.ndarray,
    rb_cursor: np.int32
) -> None:
    """Add Z-key and its met-price to the ring buffer for future price-delta update."""
    ring_buffer[rb_cursor].key[0] = z1
    ring_buffer[rb_cursor].key[1] = z2
    ring_buffer[rb_cursor].key[2] = z3
    ring_buffer[rb_cursor].key[3] = z4
    ring_buffer[rb_cursor].price = log_price

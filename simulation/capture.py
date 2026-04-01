"""Process segment, update statistics, and capture frames for rendering."""

import numba as nb
import numpy as np

from config import Config

cfg = Config()

TIME_BINS = cfg.TIME_BINS
PRICE_BINS = cfg.PRICE_BINS
CENTER_BIN = cfg.CENTER_BIN

Z_HALF = cfg.Z_HALF
Z_DUMMY = cfg.Z_DUMMY
ZSCORE_STEP = cfg.ZSCORE_STEP

MIN_Z_WEIGHT = cfg.MIN_Z_WEIGHT
MIN_COUNT = cfg.MIN_COUNT
MIN_EMA = cfg.MIN_EMA

PRICE_STEP = cfg.PRICE_STEP
EMA_ALPHA = cfg.EMA_ALPHA
DECAYS = cfg.DECAYS

WARMUP = cfg.WARMUP
CAPTURE_INTERVAL = cfg.CAPTURE_INTERVAL
RING_BUFFER_DTYPE = cfg.RING_BUFFER_DTYPE
TRAPPED_META_DTYPE = cfg.TRAPPED_META_DTYPE


@nb.njit(fastmath=True, cache=False)
def run_capture_segment(
    active_part: np.ndarray,
    windows: np.ndarray,
    emas: np.ndarray,
    variances: np.ndarray,
    stats: np.ndarray,
    timestamp: np.int32,
) -> tuple[np.ndarray, np.ndarray]:
    """Process active ticks, update statistics and capture frames for rendering."""
    max_horizon = TIME_BINS[-1]
    time_bins_count = TIME_BINS.size

    windows_count = windows.size
    zscores = np.zeros(windows_count, dtype=np.int32)

    alphas = 2.0 / (windows + 1.0)
    betas = 1.0 - alphas

    rb_size = max_horizon + 1
    rb_cursor = np.int32(0)
    ring_buffer = np.empty(rb_size, dtype=RING_BUFFER_DTYPE)
    init_ring_buffer(ring_buffer, rb_size, windows_count)

    weight_matrix = np.zeros(shape=(time_bins_count, PRICE_BINS), dtype=np.float32)

    frames_count = max(0, ((active_part.size - max_horizon) // CAPTURE_INTERVAL) + 1)
    video_frames = np.zeros(
        shape=(frames_count, time_bins_count, PRICE_BINS), dtype=np.uint32
    )
    frame_meta = np.zeros(shape=(frames_count,), dtype=TRAPPED_META_DTYPE)

    for i in range(active_part.size):
        float_price = np.float64(active_part[i])
        log_price = np.log(float_price)
        tick_timestamp = timestamp + i + WARMUP

        update_zscores(float_price, emas, variances, zscores, alphas, betas)

        for x_coord in range(time_bins_count):
            time_bin = TIME_BINS[x_coord]
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
        write_key_to_buffer( z1, z2, z3, z4, log_price, ring_buffer, rb_cursor)

        decay_weight_matrix(weight_matrix, DECAYS)
        y_coords = calculate_y_coords(z1, z2, z3, z4, stats)
        bin_counts = stats[z1, z2, z3, z4].count
        z_weight = (
            abs(z1 - Z_HALF) + abs(z2 - Z_HALF) + abs(z3 - Z_HALF) + abs(z4 - Z_HALF)
        )
        avg_ema = np.mean(stats[z1, z2, z3, z4].ema)
        for x_coord in range(time_bins_count):
            add_weight_to_matrix(
                z_weight, bin_counts, y_coords, x_coord, weight_matrix, avg_ema
            )

        if (i <= active_part.size - max_horizon) and (i % CAPTURE_INTERVAL == 0):
            meta_number = i // CAPTURE_INTERVAL
            capture_frame(weight_matrix, video_frames, meta_number)
            frame_meta[meta_number].timestamp = tick_timestamp

        if (i >= max_horizon) and ((i - max_horizon) % CAPTURE_INTERVAL) == 0:
            meta_number = (i - max_horizon) // CAPTURE_INTERVAL
            capture_frame_meta(
                ring_buffer,
                rb_cursor,
                max_horizon,
                rb_size,
                frame_meta,
                meta_number,
            )

        rb_cursor += 1
        if rb_cursor == rb_size:
            rb_cursor = 0

    return video_frames, frame_meta


@nb.njit(fastmath=True, cache=False, inline='always')
def init_ring_buffer(
    ring_buffer: np.ndarray, rb_size: np.int32, windows_count: np.int64
) -> None:
    """Fill rolling buffer with dummy keys to prevent index errors."""
    for buffer_slot in range(rb_size):
        ring_buffer[buffer_slot].price = 0.1
        for key_idx in range(windows_count):
            ring_buffer[buffer_slot].key[key_idx] = Z_DUMMY


@nb.njit(fastmath=True, cache=False, inline='always')
def update_zscores(
    float_price: np.float64,
    emas: np.ndarray,
    variances: np.ndarray,
    zscores: np.ndarray,
    alphas: np.ndarray,
    betas: np.ndarray
) -> None:
    """Update EMA and variance, calculate and bin Z-score."""
    diff = float_price - emas[0]
    emas[0] += alphas[0] * diff
    zscore = diff / np.sqrt(variances[0] + 1e-9)
    scaled = np.int32(np.abs(zscore) * ZSCORE_STEP)
    if scaled > Z_HALF:
        scaled = Z_HALF
    if zscore >= 0.0:
        zscores[0] = Z_HALF + scaled
    else:
        zscores[0] = Z_HALF - scaled
    variances[0] = betas[0] * variances[0] + alphas[0] * diff * diff

    diff = float_price - emas[1]
    emas[1] += alphas[1] * diff
    zscore = diff / np.sqrt(variances[1] + 1e-9)
    scaled = np.int32(np.abs(zscore) * ZSCORE_STEP)
    if scaled > Z_HALF:
        scaled = Z_HALF
    if zscore >= 0.0:
        zscores[1] = Z_HALF + scaled
    else:
        zscores[1] = Z_HALF - scaled
    variances[1] = betas[1] * variances[1] + alphas[1] * diff * diff

    diff = float_price - emas[2]
    emas[2] += alphas[2] * diff
    zscore = diff / np.sqrt(variances[2] + 1e-9)
    scaled = np.int32(np.abs(zscore) * ZSCORE_STEP)
    if scaled > Z_HALF:
        scaled = Z_HALF
    if zscore >= 0.0:
        zscores[2] = Z_HALF + scaled
    else:
        zscores[2] = Z_HALF - scaled
    variances[2] = betas[2] * variances[2] + alphas[2] * diff * diff

    diff = float_price - emas[3]
    emas[3] += alphas[3] * diff
    zscore = diff / np.sqrt(variances[3] + 1e-9)
    scaled = np.int32(np.abs(zscore) * ZSCORE_STEP)
    if scaled > Z_HALF:
        scaled = Z_HALF
    if zscore >= 0.0:
        zscores[3] = Z_HALF + scaled
    else:
        zscores[3] = Z_HALF - scaled
    variances[3] = betas[3] * variances[3] + alphas[3] * diff * diff

@nb.njit(fastmath=True, cache=False, inline='always')
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
    current_bin = rb_cursor - time_bin
    if current_bin < 0:
        current_bin += rb_size

    z1, z2, z3, z4 = ring_buffer[current_bin].key
    past_log = ring_buffer[current_bin].price

    log_diff = log_price-past_log
    ema = stats[z1, z2, z3, z4].ema[x_coord]
    stats[z1, z2, z3, z4].ema[x_coord] = ema + EMA_ALPHA * (log_diff - ema)

    stats[z1, z2, z3, z4].count[x_coord] += 1

@nb.njit(fastmath=True, cache=False, inline='always')
def write_key_to_buffer(
    z1: np.int32,
    z2: np.int32,
    z3: np.int32,
    z4: np.int32,
    log_price: np.float64,
    ring_buffer: np.ndarray,
    rb_cursor: np.int32,
) -> None:
    """Add Z-key and its met-price to the ring buffer for future price-delta update."""
    ring_buffer[rb_cursor].key[0] = z1
    ring_buffer[rb_cursor].key[1] = z2
    ring_buffer[rb_cursor].key[2] = z3
    ring_buffer[rb_cursor].key[3] = z4
    ring_buffer[rb_cursor].price = log_price

@nb.njit(fastmath=True, cache=False, inline='always')
def decay_weight_matrix(weight_matrix: np.ndarray, decay_array: np.ndarray) -> None:
    """Apply decay to each time-bin row of the frame matrix."""
    for i in range(decay_array.size):
        weight_matrix[i] *= decay_array[i]

@nb.njit(fastmath=True, cache=False, inline='always')
def calculate_y_coords(
    z1: np.int32, z2: np.int32, z3: np.int32, z4: np.int32, stats: np.ndarray
) -> np.ndarray:
    """Convert EMA values into percent bins on Y-axis."""
    ema_array = stats[z1, z2, z3, z4].ema

    percent = np.expm1(ema_array)
    scaled = (np.abs(percent) * PRICE_STEP).astype(np.int32)
    offset = (np.sign(percent) * np.minimum(CENTER_BIN, scaled)).astype(np.int32)
    y_coords = CENTER_BIN + offset

    return y_coords

@nb.njit(fastmath=True, cache=False, inline='always')
def add_weight_to_matrix(
    z_weight: np.int32,
    bin_counts: np.ndarray,
    y_coords: np.ndarray,
    x_coord: np.int32,
    weight_matrix: np.ndarray,
    avg_ema: np.float64,
) -> None:
    """Add signal weight into the frame matrix."""
    if (
        z_weight >= MIN_Z_WEIGHT
        and bin_counts[x_coord] >= MIN_COUNT
        and abs(avg_ema) > MIN_EMA
    ):
        weight_matrix[x_coord, y_coords[x_coord]] += z_weight**1

@nb.njit(fastmath=True, cache=False, inline='always')
def capture_frame(
    weight_matrix: np.ndarray, video_frames: np.ndarray, meta_number: np.int32
) -> None:
    """Copy the current weight matrix into the frame buffer."""
    for x in range(TIME_BINS.size):
        for y in range(PRICE_BINS):
            video_frames[meta_number, x, y] = weight_matrix[x, y]

@nb.njit(fastmath=True, cache=False, inline='always')
def capture_frame_meta(
    ring_buffer: np.ndarray,
    rb_cursor: np.int32,
    max_horizon: np.int32,
    rb_size: np.int32,
    trapped_meta: np.ndarray,
    meta_number: np.int32,
) -> None:
    """Calculate realized price movement for frame metadata."""
    start_idx = (rb_cursor - max_horizon + rb_size) % rb_size
    start_price = ring_buffer[start_idx].price
    for x_coord, time_bin in enumerate(TIME_BINS):
        after_buffer_idx = (start_idx + time_bin) % rb_size
        after_price = ring_buffer[after_buffer_idx].price

        price_diff = np.expm1(after_price - start_price)

        trapped_meta[meta_number].price_change[x_coord] = price_diff

"""Config."""
import pathlib

import numpy as np


class Config:
    """Config."""

    def __init__(self) -> None:
        """Config."""
        self.ROOT = pathlib.Path(__file__).parent.parent

        self.RAW_DIR = self.ROOT / "Binance-BTCUSDT-raw_dumps"
        self.SORTED_DIR = self.ROOT / "BTCUSDT-Sorted"
        self.FORMATTED_DIR = self.ROOT / "BTCUSDT"

        self.SORT_WORKERS = 1
        self.PACKER_WORKERS = 8
        self.BACKTEST_WORKERS = 1

        self.SIGNATURE = b"0P00"
        self.VERSION = 1
        self.HEADER_SIZE = 64
        self.HEADER_FORMAT = '< 4s I I I I I I I 12s 20x'
        self.TICK_BYTE_SIZE = 4
        self.GAP_RECORD_BYTE_SIZE = 8
        self.PRICE_SCALE = 100

        self.START_YEAR = 2020
        self.END_YEAR = 2027
        self.WARMUP = 86400
        self.GAP_THRESHOLD_SEC = 15

        self.Z_SPACE = 51
        self.Z_DUMMY = (self.Z_SPACE - 1)
        self.Z_HALF = (self.Z_SPACE - 1) // 2
        self.ZSCORE_STEP = 2
        self.MIN_Z_WEIGHT = 10

        self.PRICE_BINS = 201
        self.CENTER_BIN = (self.PRICE_BINS - 1) // 2
        self.PRICE_STEP = 10000  # 0.01%

        self.ALPHA_STEPS = 1800
        self.EMA_ALPHA = 1 - 0.5**(1/self.ALPHA_STEPS)
        self.CAPTURE_INTERVAL = 1800

        time_zero, time_max = 1800, 86400
        _time_bins = [int(time_zero)]
        while time_zero <= time_max:
            time_zero += 1800
            if time_zero <= time_max:
                _time_bins.append(int(time_zero))

        self.TIME_BINS = np.asarray(_time_bins, dtype=np.int32)

        self.RETENTION_TARGET = 0.9999
        self.HORIZON_PENALTY = 0.1
        _decays = []
        for time_bin in _time_bins:
            decay = self.RETENTION_TARGET**(1/(time_bin**self.HORIZON_PENALTY))
            _decays.append(decay)
        self.DECAYS = np.asarray(_decays, dtype=np.float64)

        self.STATS_DTYPE = np.dtype(
            [
                ("ema", np.float64, (self.TIME_BINS.size,)),
                ("count", np.int32, (self.TIME_BINS.size,)),
            ],
            align=True,
        )

        self.RING_BUFFER_DTYPE = np.dtype(
            [
                ("key", np.int32, (4,)),
                ("price", np.float64),
            ],
            align=True,
        )

        self.TRAPPED_META_DTYPE = np.dtype(
            [
                ("price_change", np.float64, (self.TIME_BINS.size,)),
                ("timestamp", np.int32),
            ],
            align=True,
        )

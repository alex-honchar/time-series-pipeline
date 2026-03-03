"""Config."""
import pathlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Config:
    """Config."""

    # --- PATHS ---
    ROOT: pathlib.Path = pathlib.Path("/home/alex")  # Base project directory
    RAW_DIR: pathlib.Path = ROOT / "Binance-BTCUSDT-raw_dumps"  # Source raw CSV dumps
    SORTED_DIR: pathlib.Path = ROOT / "BTCUSDT-Sorted"  # Chronologically sorted CSVs
    FORMATTED_DIR: pathlib.Path = ROOT / "BTCUSDT"  # Final optimized binary files

    # --- WORKERS ---
    SORT_WORKERS: int = 1    # RAM-safe limit for CSV sorting
    PACKER_WORKERS: int = 8    # High count for fast binary conversion
    BACKTEST_WORKERS: int = 1  # Optimized for CPU-bound Numba tasks

    # --- BINARY SPECS ---
    SIGNATURE: bytes = b"0P00"  # File format magic bytes
    VERSION: int = 1            # Binary format version
    HEADER_SIZE: int = 64       # Fixed header size in bytes
    HEADER_FORMAT: str = '< 4s I I I I I I I 12s 20x'  # Struct format for the header
    TICK_BYTE_SIZE: int = 4     # Size of a single int32 price
    GAP_RECORD_BYTE_SIZE: int = 8           # Record size: Start_TS + End_TS
    PRICE_SCALE: int = 100      # Multiplier for float -> int32 conversion

    # --- LOGIC ---
    WARMUP: int = 86400         # Stabilization period (24h in seconds)
    GAP_THRESHOLD_SEC: int = 15 # Minimum jump to register as a gap

    # --- PERIODS ---
    START_YEAR: int = 2022      # Baseline year for statistics
    WALK_FORWARD_YEAR: int = 2026 # Forward-test validation year

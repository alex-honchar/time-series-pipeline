"""Convert Binance trade CSV files into a custom per-second binary format."""

import concurrent.futures
import csv
import struct
from datetime import datetime, timezone
from pathlib import Path

from config import Config

cfg = Config()

PACKER = struct.Struct("<i")
MONTH_START_DAY = 1
TIMESTAMP_RULES = [
    (10**15, 1_000_000),
    (10**12, 1_000),
    (10**9, 1)
]

class Etl:
    """Process one monthly Binance CSV file into a binary output."""

    __slots__ = [
        'input_path',
        'buffer',
        'current_sec',
        'trade_price',
        'line_counter',
        'symbol',
        'data_type',
        'month',
        'year',
        'month_start_ts',
        'month_end_ts',
        'month_duration',
        'output_path',
        'gap_buffer',
        'gap_count',
    ]

    def __init__(self, input_path: Path) -> None:
        """Initialize ETL state and calculate time boundaries from the filename."""
        self.input_path = input_path
        self.buffer = bytearray()
        self.current_sec = 0
        self.trade_price = 0
        self.line_counter = 0
        parts = self.input_path.stem.split("-")
        self.symbol, self.data_type, self.year, self.month = parts
        self.output_path = (
            cfg.ROOT /
            self.symbol /
            f"{self.symbol}-{self.data_type}Formatted-{self.year}-{self.month}.bin")
        self.output_path.parent.mkdir(exist_ok=True)
        self._calculate_time_boundaries()
        self.gap_buffer = bytearray()
        self.gap_count = 0

    def _calculate_time_boundaries(self) -> None:
        """Calculate and set the start and end epoch timestamps of the month."""
        year_start, month_start = int(self.year), int(self.month)
        if month_start == 12:
            month_end = 1
            year_end = year_start + 1
        else:
            month_end = month_start + 1
            year_end = year_start

        start_dt = datetime(
            int(year_start), int(month_start), MONTH_START_DAY, tzinfo=timezone.utc
        )
        end_dt = datetime(
            int(year_end), int(month_end), MONTH_START_DAY, tzinfo=timezone.utc
        )

        self.month_start_ts = int(start_dt.timestamp())
        self.month_end_ts = int(end_dt.timestamp())
        self.month_duration = self.month_end_ts - self.month_start_ts

    def run(self) -> None:
        """Execute the full ETL pipeline: ingest, fill gaps, and save to binary."""
        with open(self.input_path, newline="") as file:
            reader = csv.reader(file)
            for row in reader:
                self._ingest_row(row)
            self._fill_end_gap()
            self._write_header_and_buffer()

    def _ingest_row(self, row: list[str]) -> None:
        """Extract trade data and update global timeline state."""
        trade_price       = int(float(row[1])*cfg.PRICE_SCALE+0.5)
        trade_ts            = int(row[5])

        missing_seconds = self._sync_timeline(trade_ts, trade_price)
        self._advance_timeline(trade_price, missing_seconds)

    def _sync_timeline(self, trade_ts: int, trade_price: int) -> int:
        """Calculate the gap between the last processed second and the current event."""
        trade_epoch_sec = self._normalize_ts(trade_ts)

        # Initialize start time on the first event
        if self.current_sec == 0:
            self.current_sec = self.month_start_ts
            self.trade_price = trade_price

        missing_seconds = (trade_epoch_sec - self.current_sec)
        return missing_seconds

    def _normalize_ts(self, trade_ts:int) -> int:
        """Normalize a trade timestamp to epoch seconds."""
        for threshold, divisor in TIMESTAMP_RULES:
            if trade_ts > threshold:
                return trade_ts // divisor

    def _advance_timeline(self, trade_price: int, missing_seconds: int) -> None:
        """Fill skipped seconds using last known trade price."""
        self._record_gap(missing_seconds)

        for _ in range(missing_seconds):
            self._append_tick()
            self.current_sec += 1

        self.trade_price = trade_price

    def _record_gap(self, gap_size: int) -> None:
        """Record large gap ranges in the gap buffer."""
        if gap_size >= cfg.GAP_THRESHOLD_SEC:
            gap_start = self.current_sec
            gap_end = self.current_sec + gap_size
            self.gap_buffer.extend(struct.pack("<II", gap_start, gap_end))
            self.gap_count += 1

    def _append_tick(self) -> None:
        """Append current tick to the output buffer."""
        self.buffer.extend(PACKER.pack(self.trade_price))
        self.line_counter += 1

    def _fill_end_gap(self) -> None:
        """Fill the remaining seconds of the month with the last known price."""
        end_gap = self.month_end_ts - self.current_sec
        self._record_gap(end_gap)

        for _ in range(end_gap):
            self._append_tick()

    def _write_header_and_buffer(self) -> None:
        """Write the header, gap metadata, and tick buffer to the output file."""
        header_format = '< 4sIIIIIII12s20x'
        header = struct.pack(
            header_format,
            cfg.SIGNATURE,
            cfg.VERSION,
            self.month_start_ts,
            self.month_end_ts,
            self.month_duration,
            int(self.year),
            int(self.month),
            self.gap_count,
            self.symbol.encode('ascii'),
        )
        with open(self.output_path, "wb") as writer:
            writer.write(header)
            writer.write(self.gap_buffer)
            writer.write(self.buffer)


def task(path: Path) -> None:
    """Convert one CSV file to binary format."""
    etl = Etl(path)
    etl.run()

if __name__ == "__main__":
    input_files = sorted(cfg.SORTED_DIR.glob("*.csv"))

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=cfg.PACKER_WORKERS
    ) as executor:

        futures = {
            executor.submit(task, path): path
            for path in input_files
        }

        for future in concurrent.futures.as_completed(futures):
            original_path = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f'Error in {original_path}: {exc!r}')

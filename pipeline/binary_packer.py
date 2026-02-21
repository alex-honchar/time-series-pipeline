import pathlib
import gzip
import concurrent.futures
import csv
import struct
from datetime import datetime, timezone
from dataclasses import dataclass, field
import pandas as pd

INPUT_DIR = pathlib.Path("/home/alex/BTCUSDT-Sorted")
OUTPUT_ROOT = pathlib.Path("/home/alex")
MAX_WORKERS = 8
PACKER = struct.Struct("<i")
EDGE_DAY = 1
TIMESTAMP_RULES = [
    (10**15, 1_000_000),
    (10**12, 1_000),
    (10**9, 1)
]
SIGNATURE = b"0P00"
VERSION = 1
GAP_THRESHOLD_SEC = 15

class Etl:
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
    
    def __init__(self, input_path):
        self.input_path = input_path
        self.buffer = bytearray()
        self.current_sec = 0
        self.trade_price = 0.0
        self.line_counter = 0
        self.symbol, self.data_type, self.year, self.month = self.input_path.stem.split("-")
        self.output_path = OUTPUT_ROOT / self.symbol / f"{self.symbol}-{self.data_type}Formatted-{self.year}-{self.month}.bin"
        self.output_path.parent.mkdir(exist_ok=True)
        self._set_time_boundires()
        self.gap_buffer = bytearray()
        self.gap_count = 0

    def _set_time_boundires(self):
        year_start, month_start = int(self.year), int(self.month)
        if month_start == 12:
            month_end = 1
            year_end = year_start + 1
        else:
            month_end = month_start + 1
            year_end = year_start
        
        start_dt =  datetime(int(year_start), int(month_start), EDGE_DAY, tzinfo=timezone.utc)
        end_dt = datetime(int(year_end), int(month_end), EDGE_DAY, tzinfo=timezone.utc)

        self.month_start_ts = int(start_dt.timestamp())
        self.month_end_ts = int(end_dt.timestamp())
        self.month_duration = self.month_end_ts - self.month_start_ts  

    def run(self):
        try:
            with open(self.input_path, newline="") as file:
                reader = csv.reader(file)
                for row in reader:
                    self._ingest_row(row)
                self._fill_end_gap()
                self._write_header_and_buffer()

        except Exception as e:
            print(f"Error in {self.input_path} : {type(e).__name__} {repr(e)}")

    def _ingest_row(self, row):
        #agg_trade_id      = int(row[0])
        trade_price       = int(float(row[1])*100+0.5)
        #trade_quantity    = float(row[2])
        #first_trade_id    = int(row[3])
        #last_trade_id     = int(row[4])
        trade_ts            = int(row[5])
        #is_buyer_maker    = row[6] == "true"
        
        missing_seconds = self._sync_timeline(trade_ts, trade_price)
        self._advance_timeline(trade_price, missing_seconds)

    def _sync_timeline(self, trade_ts, trade_price):
        trade_epoch_sec = self._normalize_ts(trade_ts)
        
        if self.current_sec == 0: # initiate the first row
            self.current_sec = self.month_start_ts
            self.trade_price = trade_price
            
        missing_seconds = (trade_epoch_sec - self.current_sec)
        return missing_seconds

    def _normalize_ts(self, trade_ts):
        for threshold, divisor in TIMESTAMP_RULES:
            if trade_ts > threshold:
                return trade_ts // divisor

    def _advance_timeline(self, trade_price, missing_seconds):
        self._check_gap(missing_seconds)

        for _ in range(missing_seconds):
            self._commit_tick()
            self.current_sec += 1   
            #state["buy_volume"] = 0.0
            #state["sell_volume"] = 0.0
            #state["trade_count"] = 0
        self.trade_price = trade_price

        #state["trade_count"] += ((last_trade_id - first_trade_id)+1)
        #if is_buyer_maker is False:
            #state["buy_volume"] += trade_quantity
        #elif is_buyer_maker is True:
            #state["sell_volume"] += trade_quantity

    def _check_gap(self, gap_size):
        if gap_size >= GAP_THRESHOLD_SEC: 
            gap_start = self.current_sec
            gap_end = self.current_sec + gap_size 
            self.gap_buffer.extend(struct.pack("<II", gap_start, gap_end))
            self.gap_count += 1

    def _commit_tick(self):
        self.buffer.extend(PACKER.pack(self.trade_price))
        self.line_counter += 1

    def _fill_end_gap(self):
        
        end_gap = self.month_end_ts - self.current_sec
        
        self._check_gap(end_gap)
        
        for missed_ticks in range(end_gap):
            self._commit_tick()                                                             # the iteration commits the last second (23:59:59) to the buffer.
        print(f"{self.symbol}-{self.year}-{self.month} / End_gap = {(end_gap-1)} / Gaps Counter = {self.gap_count}")

    def _write_header_and_buffer(self):
        header_format = '< 4s I I I I I I I 12s 20x'
        header = struct.pack(
            header_format,
            SIGNATURE,
            VERSION,
            self.month_start_ts,
            self.month_end_ts,
            self.month_duration,
            int(self.year),
            int(self.month),
            self.gap_count,
            self.symbol.encode('ascii'),
            #empty 20 bytes
        )
        with open(self.output_path, "wb") as writer:
            writer.write(header)
            writer.write(self.gap_buffer)
            writer.write(self.buffer)

def task(path):
    etl = Etl(path)
    etl.run()

if __name__ == "__main__":
    input_files = list(INPUT_DIR.glob("*.csv"))
    input_files.sort() # ensure deterministic chronological merge
    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(task, path) for path in input_files]
        for future in concurrent.futures.as_completed(futures):
            future.result()
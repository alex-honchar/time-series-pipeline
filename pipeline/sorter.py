import pathlib
import gzip
import concurrent.futures
import csv
import struct
from datetime import datetime, timezone
import pandas as pd
import time


INPUT_DIR = pathlib.Path("/home/alex/Binance-BTCUSDT-raw_dumps")
OUTPUT_ROOT = pathlib.Path("/home/alex")
MAX_WORKERS = 1



def sort_file(path):
    # BTCUSDT-aggTrades-2025-09.csv
    start_time = time.time()
    
    symbol, data_type, year, month  = path.stem.split("-")

    output_path = OUTPUT_ROOT / f"{symbol}-Sorted" / f"{symbol}-{data_type}Sorted-{year}-{month}.csv"
    output_path.parent.mkdir(exist_ok=True)
    try:
        
        with open(path, 'rt') as reader:
            row = reader.readline()
            is_not_header = row[0].isdigit()

        if is_not_header is True:
            df = pd.read_csv(path, dtype={5: "int64"}, header=None, usecols=[0, 1, 2, 3, 4, 5, 6], engine = 'c')
        
        if is_not_header is False:
            df = pd.read_csv(path, dtype={5: "int64"}, header=0, usecols=[0, 1, 2, 3, 4, 5, 6], engine = 'c')
            df.columns = [0, 1, 2, 3, 4, 5, 6]
        
        df.sort_values(by=5, ascending=True, inplace=True, ignore_index=True)

        df.to_csv(output_path, header=False, index=False)
        time_diff = time.time() - start_time

        print(f'{year}-{month} done in {time_diff} / no header {is_not_header}')


    except Exception as e:
        print(f"Error in {path} : {type(e).__name__} {repr(e)}")

if __name__ == "__main__":
    input_files = list(INPUT_DIR.glob("*.csv"))
    input_files.sort() # ensure deterministic chronological merge

    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(sort_file, path) for path in input_files]
        for future in concurrent.futures.as_completed(futures):
            future.result()
"""Sort raw trade data."""

import concurrent.futures
from pathlib import Path

import pandas as pd

from config import Config

cfg = Config()


def sort_file(path: Path) -> None:
    """Sort trade data files by timestamp."""
    symbol, data_type, year, month = path.stem.split("-")
    print(f"LETS START {path}")

    output_path = (
        cfg.ROOT / f"{symbol}-Sorted" / f"{symbol}-{data_type}Sorted-{year}-{month}.csv"
    )
    output_path.parent.mkdir(exist_ok=True)

    with open(path, "rt") as reader:
        row = reader.readline()
        is_not_header = row[0].isdigit()
        h_val = None if is_not_header else 0

    df = pd.read_csv(
        path, dtype={5: "int64"}, header=h_val, usecols=range(7), engine="c"
    )
    df.columns = range(7)
    df.sort_values(by=5, ascending=True, inplace=True, ignore_index=True)
    df.to_csv(output_path, header=False, index=False)


if __name__ == "__main__":
    input_files = sorted(cfg.RAW_DIR.glob("*.csv"))

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=cfg.SORT_WORKERS
    ) as executor:

        futures = {
            executor.submit(sort_file, path): path
            for path in input_files
        }

        for future in concurrent.futures.as_completed(futures):
            original_path = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f'Error in {original_path}: {exc!r}')


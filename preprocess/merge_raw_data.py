import pathlib
import gzip
import json

INPUT_DIR = pathlib.Path("/home/alex/dumps/BTCUSDT/trade/")
OUTPUT_DIR = pathlib.Path("/home/alex/merged/")
OUTPUT_FILENAME = OUTPUT_DIR / "merged.jsonl.gz"

def transform_entry(raw_line): # Convert raw dump entries into a smaller format for faster streaming.
    new_line = {
        "true_ts": int(raw_line["timestamp"]*1000), 
        "is_connected": bool(raw_line["connected"]), 
        "data": [],
    }
    
    for raw_trade in raw_line["data"]:  # parse strings into floats/ints here once
        new_data = {
            "trade_ts": int(raw_trade["T"]),
            "price": float(raw_trade["p"]), 
            "volume": float(raw_trade["q"]), 
            "is_buyer_maker": bool(raw_trade["m"])
        }
        
        new_line["data"].append(new_data)

    return new_line

def main():                      
    input_files = list(INPUT_DIR.glob("*.jsonl.gz"))
    input_files.sort() # ensure deterministic chronological merge
    total_files = len(input_files)
    
    OUTPUT_DIR.mkdir(exist_ok = True)

    try:
        with gzip.open(OUTPUT_FILENAME, "wt") as writer:
        
            for i, input_file in enumerate(input_files, 1):
                with gzip.open(input_file, "rt") as reader:
                    for line in reader: 
                        raw_line = json.loads(line)
                        new_line = transform_entry(raw_line)
                        writer.write(json.dumps(new_line, separators=(',', ':'))+ "\n")
                print(f"File {i} out of {total_files} : {input_file}")
        
        print("Done")
    
    except Exception as e:
        print(f"Error in {input_file} : {e}")

if __name__ == "__main__":
     main()
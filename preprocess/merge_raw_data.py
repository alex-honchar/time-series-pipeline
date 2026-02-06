import pathlib
import gzip
import orjson

INPUT_DIR = pathlib.Path("/home/alex/dumps/BTCUSDT/trade/")
OUTPUT_DIR = pathlib.Path("/home/alex/merged/")
OUTPUT_FILENAME = OUTPUT_DIR / "merged.jsonl.gz"

def transform_entry(raw_line, state): # Convert raw dump entries into a smaller format for faster streaming.
    true_ts = int(raw_line["timestamp"]*1000)
    #state["last_price"] - State persists the last price to prevent gaps and keep data continuity
    buy_volume = 0.0
    sell_volume =  0.0
    trade_count = 0
    is_connected = bool(raw_line["connected"])

    if raw_line["data"]:
        state["last_price"] = float(raw_line["data"][-1]["p"])
    
        for raw_trade in raw_line["data"]:
            trade_count += 1

            if raw_trade["m"] is False:
                buy_volume += float(raw_trade["q"])
            elif raw_trade["m"] is True:
                sell_volume += float(raw_trade["q"])
                
    new_line = [
        true_ts,             #0
        state["last_price"], #1
        buy_volume,          #2
        sell_volume,         #3
        trade_count,         #4
        is_connected         #5
    ]

    return new_line

def main():                      
    input_files = list(INPUT_DIR.glob("*.jsonl.gz"))
    input_files.sort() # ensure deterministic chronological merge
    total_files = len(input_files)

    state = {"last_price": 0.0}
    
    OUTPUT_DIR.mkdir(exist_ok = True)

    try:
        with gzip.open(OUTPUT_FILENAME, "wb") as writer:
        
            for i, input_file in enumerate(input_files, 1):
                with gzip.open(input_file, "rb") as reader:
                    for line in reader: 
                        raw_line = orjson.loads(line)
                        new_line = transform_entry(raw_line, state)
                        writer.write(orjson.dumps(new_line) + b"\n")
                print(f"File {i} out of {total_files} : {input_file}")
        
        print("Done")
    
    except Exception as e:
        print(f"Error in {input_file} : {e}")

if __name__ == "__main__":
     main()
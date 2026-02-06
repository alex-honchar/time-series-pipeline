import gzip
import orjson 
import time
import subprocess

from constants import TS, PRICE, BUY_VOL, SELL_VOL, COUNT, CONNECTED

def init_reader(state):
    if state["system"]["start_time"] is None:
        state["system"]["start_time"] = time.time() # used for simple throughput logging
    if state["system"]["reader"] is None and state["system"]["active"] is False:
        try:    
            process = subprocess.Popen(["pigz", "-dc","/home/alex/merged/merged.jsonl.gz"], stdout=subprocess.PIPE) # prefer pigz for faster gzip decompression (fallback to Python gzip)
            state["system"]["reader"] = process.stdout
            print("PIGZ MODE")
                    
        except FileNotFoundError:
            state["system"]["reader"] = gzip.open("/home/alex/merged/merged.jsonl.gz", "rb")
            print("GZIP MODE")

        state["system"]["active"] = True

def read_tick(state):
    raw_bytes = state["system"]["reader"].readline()
    
    if not raw_bytes:
        state["system"]["active"] = False
        state["system"]["tick_connected"] = False
        print(f'Done. Disconnected = {state["metrics"]["disconnected_ticks"]} / Broken = {state["metrics"]["broken_ticks"]}')
        return None

    try:
        line = orjson.loads(raw_bytes)
        return line
    except: # broken JSON tick: count and skip (do not crash the pipeline)
        state["system"]["tick_connected"] = False
        state["metrics"]["broken_ticks"] += 1
        return None

def check_tick(state, line): 
    state["system"]["tick"] += 1
    if state["system"]["tick"] % 86400 == 0:
        real_time = time.time()
        time_diff = real_time - state["system"]["start_time"]
        print(f'lps = {state["system"]["tick"] / time_diff}     /       total time = {time_diff}')

    if line[CONNECTED] is True:
        state["system"]["tick_connected"] = True # tick_connected is a run-validity flag: only clean continuous segments are allowed to update stats
    else:
        state["system"]["tick_connected"] = False
        state["metrics"]["disconnected_ticks"] += 1


def push_tick(state, line): 
    state["market"]["trades"].append(line[:5])

def ingest_tick(state):
    line = read_tick(state)
    if line is not None:
        check_tick(state, line)
        if state["system"]["tick_connected"] is True:
            push_tick(state, line)
# QUICK_TOUR

This is a short guide to the current codebase (what runs today, and where to look).

## Project at a glance

Right now the project is a minimal **streaming pipeline**:

- read a prepared `merged.jsonl.gz` stream **tick-by-tick**
- **1 line = 1 second tick**
- parse JSON
- if the tick is marked as connected → push its trades into a rolling `deque`

---

## Repo layout

- `run.py`  
  Entry point. Starts the loop and calls `ingest_tick()` until the stream ends.

- `state.py`  
  Shared runtime state (system flags, counters, rolling trade buffer).

- `ingest/stream_reader.py`  
  Streaming reader: decompression, JSON parsing, basic validation, buffering trades.

- `preprocess/merge_raw_data.py`  
  One-time utility that merges raw dump files into the optimized `merged.jsonl.gz` format.

---

## 1) One-time data preparation

### `preprocess/merge_raw_data.py`

This script is **not part of the runtime pipeline**.  
It is a one-time tool to convert raw dump files into a single normalized stream.

- input: many raw `*.jsonl.gz` files from `INPUT_DIR`
- output: one file `merged.jsonl.gz` in `OUTPUT_DIR`

Normalized output format (one line / one tick):

```json
{
  "true_ts": 1767916543589,
  "is_connected": true,
  "data": [
    {
      "trade_ts": 1767916542795,
      "price": 91106.09,
      "volume": 0.00054,
      "is_buyer_maker": true
    }
  ]
}
```


## 2) Shared runtime state

### `state.py`

`state` is a shared dictionary used by the runner and the ingestion module.

- `system`
  - `reader`: stream handle
  - `active`: whether the main loop continues
  - `tick_connected`: whether the current tick is valid
  - `tick`: processed tick counter (1 tick = 1 line = 1 second)
  - `start_time`: used for basic performance logging

- `metrics`
  - `broken_ticks`: JSON parse failures
  - `disconnected_ticks`: ticks where `is_connected = false`

- `market`
  - `trades`: rolling buffer of recent trades (`deque(maxlen=10000)`)
  - `last_price`: placeholder for later logic


## 3) Ingestion (stream reader)

### `ingest/stream_reader.py`

This module streams `merged.jsonl.gz` sequentially and updates the rolling trade buffer in
`state["market"]["trades"]` (connected ticks only).

Main functions:

- `init_reader(state)`
  - opens the `merged.jsonl.gz` stream and starts the timer
  - uses `pigz` if available, otherwise falls back to Python `gzip`
  - enables the main loop (`system["active"] = True`)

- `read_tick(state) -> dict | None`
  - reads the next JSON line (one tick = one second)
  - returns the parsed tick dict, or `None` on EOF / parse failure
  - increments `metrics["broken_ticks"]` on parse errors

- `check_tick(state, tick)`
  - increments `system["tick"]`
  - sets `system["tick_connected"]` from `tick["is_connected"]`
  - increments `metrics["disconnected_ticks"]` when the tick is not connected
  - prints a simple throughput report every 86400 ticks

- `push_tick(state, tick)`
  - appends `tick["data"]` to the rolling trade buffer (`market["trades"]`)

- `ingest_tick(state)`
  - single-step ingestion: `read_tick → check_tick → push_tick` (connected ticks only)




## 4) Runner loop

### `run.py`

`run.py` is intentionally small and just drives the ingestion loop:

- `init_reader(state)`
- `while state["system"]["active"]:`
  - `ingest_tick(state)`

Later pipeline steps (snapshots, statistics, inference, visualization) will be added after ingestion in the same loop.


## 5) Current behavior

What you can run and observe right now:

- sequential reading of a compressed tick stream (`jsonl.gz`)
- 1 line = 1 second tick
- rolling buffering of recent trades in `market.trades`
- basic counters for broken JSON ticks and disconnected ticks
- simple performance logging (lines per second)
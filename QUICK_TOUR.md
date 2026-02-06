# QUICK_TOUR

This guide explains the codebase structure and the data flow mechanics.

## System Overview

The project is a low-latency **streaming pipeline** designed for sequential trade processing:

- **Input:** A pre-aggregated `merged.jsonl.gz` stream.
- **Resolution:** 1 line = 1 second (tick).
- **Process:** sequential read → parse → validate → push to memory.
- **Storage:** Valid ticks are stored in a rolling `deque` for immediate statistical analysis.

---

## File Structure

- `ingest/preprocess/merge_raw_data.py`
  Normalization utility. Converts raw dumps into the optimized compact list format.

- `constants.py`
  Index mapping. Defines integer constants (`TS=0`, `PRICE=1`, etc.) for accessing elements in the raw list format.

- `state.py`
  Shared runtime context. Stores system flags, performance metrics, and the rolling trade buffer.

- `ingest/stream_reader.py`
  Core ingestion logic. Reads the compressed stream, validates ticks, and updates the market buffer.

- `run.py`
  Entry point. Initializes the environment and drives the main ingestion loop.
---

## 1) Data Preparation

### `ingest/preprocess/merge_raw_data.py`

This is a **one-time utility** to normalize raw exchange dumps into a fast-loading stream format.

- **Input:** Multiple raw `*.jsonl.gz` files from `INPUT_DIR`.
- **Output:** A single chronologically sorted `merged.jsonl.gz`.

**Transformation Logic (per second):**
1.  **Aggregation:** Sums `buy_volume` and `sell_volume` separately.
2.  **Forward Fill:** Carries over the last known price to empty ticks to avoid gaps.
3.  **Serialization:** Converts dicts to a compact list format.

**Output Format:**
`[ts, price, buy_vol, sell_vol, count, is_connected]`

```json
[1767916543589, 91106.09, 0.54, 0.12, 15, true]
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
  - `trades`: rolling buffer of recent trades (`deque`, stores compact lists `[ts, price, vol...]`)
  - `last_price`: placeholder for later logic (current market price)

## 3) Ingestion (stream reader)

### `ingest/stream_reader.py`

This module streams `merged.jsonl.gz` sequentially and updates the rolling trade buffer in `state["market"]["trades"]`.

Main functions:

- `init_reader(state)`
  - opens the stream using `pigz` (subprocess) or standard `gzip`
  - sets `system["start_time"]` and enables the main loop

- `read_tick(state) -> list | None`
  - reads raw bytes and parses JSON via `orjson`
  - returns the raw list `[ts, price, b_vol, s_vol, count, connected]`
  - increments `metrics["broken_ticks"]` on parse errors

- `check_tick(state, tick)`
  - updates global counters and prints throughput (LPS) every 86,400 ticks
  - updates `system["tick_connected"]` based on index `[5]` (`CONNECTED`)

- `push_tick(state, tick)`
  - slices the input list `tick[:5]` to isolate `[TS, PRICE, BUY_VOL, SELL_VOL, COUNT]`
  - appends the compact list to `state["market"]["trades"]`

- `ingest_tick(state)`
  - calls `read_tick` → `check_tick` → `push_tick` (only if connected)


## 4) Runner loop

### `run.py`

Entry point script. It initializes the reader and executes the main event loop.

**Execution flow:**
- `init_reader(state)`: Sets up the subprocess pipe and timers.
- `while state["system"]["active"]`:
  - `ingest_tick(state)`: Processes one tick (read → check → push).

*The loop runs until EOF or a fatal stream error.*

## 5) Current Status

The pipeline currently functions as a high-speed ingestion engine.

**Operational details:**
- **Input:** Streams compressed `jsonl.gz` via `pigz` pipe.
- **Performance:** High-speed sequential processing.
- **State:** Maintains a rolling buffer of compact trade lists (`[ts, price, b_vol, s_vol, count]`).
- **Logging:** Prints throughput metrics every 86,400 ticks; prints validation counters on completion.
# State-Based Market Analysis (WIP)

## Why this project exists

Portfolio-style engineering project focused on a **deterministic streaming data pipeline**
with modular architecture and statistical aggregation on real-world trade data.

Research tool — **not** a trading system: no order execution, no exchange interaction,
no “strategy / alpha / edge” goals.

Focus: real trade data, no look-ahead, correctness guarantees for statistical updates, and a modular pipeline.

---

## Data (current setup)

- Source dataset: BTCUSDT trades (price / volume / side) from Binance trade stream dumps.
- ~31 days of data.
- Preprocessed into one compressed `jsonl.gz` stream.
- Format: **1 line = 1 second** (all trades within that second).
- This 1-second stream is used as the processing **tick**.

The merge script is a one-time data preparation utility used to transform raw dumps into the optimized format.

Runtime data is expected locally (not tracked by git).  
A prepared compressed dataset (~200MB, full 31 days) may be included in some repository versions
to allow direct execution without additional preprocessing.

---

## Pipeline (current direction)

1. **Ingest:** Stream ticks from `jsonl.gz`.
2. **Snapshot:** Build features from a rolling window.
3. **Discretize:** Convert snapshots into discrete state keys.
4. **Statistics (Accumulation):** Update per-key forward statistics as horizons are reached.
5. **Expectation (Inference):** Query accumulated statistics for recent keys and build a forward probability distribution.
6. **Visualize:** Human-facing analysis (overlays + heatmaps).

---

## Core Concepts

### Snapshot → Key

- **Snapshot:** feature vector computed over a rolling window (e.g. last 600 ticks).
- Features are normalized using **z-scores** relative to recent history.
- Values are discretized into integer bins (−4…+4, step = 1 → 9 states per feature).
- A state key is a tuple of discretized feature values:  
  `key = (bin_f1, bin_f2, bin_f3, ...)`

This produces a compact discrete representation of the current market state.

### Accumulation / Evaluation Split (66/34)

The run is divided into two phases for validation purposes.

- **Phase 1 — Initial accumulation (~66%)**  
  The pipeline processes the stream and builds the statistical map of observed keys  
  and their forward outcomes. Statistics are continuously collected.

- **Phase 2 — Evaluation (~34%)**  
  Processing continues with the same logic.  
  The system now also queries the accumulated statistics for newly observed keys  
  and builds probabilistic expectations of short-horizon behavior.

Statistics continue to accumulate during this phase as well.

### No look-ahead

Processing is strictly sequential.  
Future data becomes available only when the timeline reaches it —  
no look-ahead or future leakage is possible.

### Context reset on invalid ticks

Snapshots use a rolling context built from previous ticks.  
If a disconnected or malformed tick appears, the rolling context is **reset** and the pipeline does **not**
update statistics or run downstream logic until the entire context window is 100% valid again.


---

## Usage

`python run.py`

---

## Tech (current)

Python 3.x, `orjson`, optional `pigz` (fallback to `gzip`).

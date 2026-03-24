# Deterministic Time-Series Backtesting Engine

A Python backtesting engine for deterministic simulation of time-series data.

The system converts raw CSV dumps into a custom binary format, builds an execution plan over contiguous valid data segments, and runs sequential simulation. The final stage renders captured 2D state matrices as dynamic MP4 heatmaps.

Detailed module breakdown and data flow: see `ARCHITECTURE.md`.

---

## Pipeline Structure

Data preparation and planning modules reside in `pipeline/`, simulation logic in `simulation/`, and rendering logic in `visualization/`.

### 1) Preprocessing (`pipeline/sorter.py`)
Sorts raw source CSVs by timestamp.

This step exists because exchange dumps (e.g. Binance monthly CSVs) may contain rows that are out of chronological order.

### 2) Binary Packer (`pipeline/binary_packer.py`)
Converts raw time-series rows into a custom monthly binary format.

The packer:
- normalizes input into a strict 1-second timeline
- expands each month to its full second range
- stores missing ranges explicitly in metadata

### 3) Execution Planner (`pipeline/execution_planner.py`)
Builds a contiguous tick buffer and an execution plan over valid data segments.

It uses missing ranges to split the timeline into valid segments, resets warmup before each new segment, and emits execution entries in the form:

`[cursor, timestamp, warmup_ticks, active_ticks]`

### 4) Backtest Runner (`simulation/backtest_runner.py`)
Executes the generated plan over the assembled tick buffer.

- restores warmup state for each segment
- updates `stats` across the execution plan
- routes the final segment through capture and rendering
- uses `multiprocessing.shared_memory` for the assembled tick buffer

### 5) Segment Processing (`simulation/passive.py`, `simulation/capture.py`)
Runs the core per-segment math.

- **Passive mode:** updates the 4D `stats` matrix without rendering overhead
- **Capture mode:** reuses the same sequential processing flow, adds weight-matrix updates, and records frame data for rendering
- **Math:** uses Numba-compiled functions for warmup, EMA / variance updates, Z-score discretization, and ring-buffer-based delayed price tracking

### 6) Visualization (`visualization/visualize.py`)
Renders captured 2D matrices into MP4 heatmaps.

- normalizes captured 2D matrices
- resizes them into a fixed video canvas
- applies OpenCV color mapping
- draws axes, timestamps, and realized price paths
- writes the result as an MP4 file

---

## Data (Current Setup)

- Binance BTCUSDT trade dumps
- Internal resolution: 1 second
- Dataset stored locally and not included in the repository

---

## Status

**Implemented:**
- CSV sorting for chronological preprocessing
- Binary packing into a custom monthly format
- Explicit missing-range metadata
- Execution planning over valid segments with warmup resets
- Global volume validation
- Shared-memory tick buffer assembly
- Passive segment processing with 4D `stats` updates
- Capture mode with frame recording
- MP4 heatmap rendering via OpenCV

**Planned:**
- Core math optimization

---

## Tech Stack

Python 3.x, `numpy`, `numba`, `multiprocessing.shared_memory`, `struct`, `concurrent.futures`, `pandas` (preprocessing only), `opencv-python`

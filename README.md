# Time-Series Simulation Pipeline

Portfolio engineering project for deterministic preprocessing, simulation, and visualization of time-based data in Python.

The pipeline converts raw event rows (CSV dumps) into a compact binary format, assembles a contiguous valid tick buffer, and builds a gap-aware execution plan for sequential simulation.

Detailed module breakdown and data flow: see `ARCHITECTURE.md`.

---

## Pipeline Structure

Data preparation and planning modules reside in `pipeline/`, simulation logic in `simulation/`, and rendering logic in `visualization/`.

### 1) Preprocessing (`pipeline/sorter.py`)
Raw source CSVs are sorted by timestamp.

This step exists because exchange dumps (e.g. Binance monthly CSVs) may contain rows out of chronological order.

### 2) Binary Packer (`pipeline/binary_packer.py`)
Converts raw time-based rows into a custom binary format.

The packer:
- normalizes input into a strict 1-second timeline
- expands each month to its full second range
- stores missing ranges explicitly as gap metadata

### 3) Execution Planner (`pipeline/execution_planner.py`)
Builds a contiguous tick buffer and a gap-aware execution plan from binary metadata.

It skips missing data gaps, uses them to trigger warmup resets for the next valid segment, and emits execution entries in the form:

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
- **Capture mode:** reuses the same sequential processing flow, adds weight-matrix updates, and traps frame data for rendering
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
- 1-second internal resolution
- Local dataset (not tracked in git)

---

## Status

**Implemented:**
- Strict CSV sorting
- Gap-aware binary packer
- Execution planner with gap skipping and warmup resets
- Global volume validation
- Shared-memory execution scaffolding
- Passive segment processing with 4D `stats` updates
- Capture mode with frame trapping
- MP4 heatmap rendering via OpenCV

**Planned:**
- Core math optimization

---

## Tech Stack

Python 3.x, `numpy`, `numba`, `multiprocessing.shared_memory`, `struct`, `concurrent.futures`, `pandas` (preprocessing only), `opencv-python`

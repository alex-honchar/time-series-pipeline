# Time-Series Simulation Pipeline (WIP)

Portfolio engineering project for deterministic preprocessing and execution of time-based data in Python.

The pipeline converts raw event rows (CSV dumps) into a compact binary format, assembles a contiguous tick buffer, and builds a gap-aware execution plan for sequential simulation and worker-based execution.

Detailed module breakdown and data flow: see `ARCHITECTURE.md`.

---

## Pipeline Structure

Data preparation and planning modules reside in the `pipeline/` directory, while the execution runner and core math logic sit at the root level.

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

It skips missing data gaps, using them to force a state reset and a new warmup phase for the next valid segment. It emits execution entries in the form:

`[cursor, timestamp, warmup_ticks, active_ticks]`

### 4) Backtest Execution (`backtest_runner.py` & `segment_math.py`)
Runs the generated execution plan over the assembled tick buffer.

- **Memory:** Uses `multiprocessing.shared_memory` so the assembled tick buffer is not copied into each worker process.
- **Math:** Uses Numba-compiled functions for warmup and active segment calculations, including rolling EMA / variance updates and z-score discretization.

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
- Shared-memory worker execution
- Numba-compiled segment math (`do_warmup`, `do_active`)

**Planned:**
- Writing results to the shared `stats` array
- Core math optimization

---

## Tech Stack

Python 3.x, `numpy`, `numba`, `multiprocessing.shared_memory`, `struct`, `concurrent.futures`, `pandas` (preprocessing only).
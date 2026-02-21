# Time-Series Simulation Pipeline (WIP)

Portfolio engineering project for deterministic preprocessing and orchestration of time-based data in Python.

The pipeline converts raw event rows (CSV dumps) into a compact binary format and prepares gap-aware worker jobs for fast sequential simulation and parallel evaluation.

Detailed module breakdown and data flow:
- see `ARCHITECTURE.md`

---

## Pipeline Structure
The core engine is located in the `pipeline/` directory.

### 1) Preprocessing (`sorter.py`)
Raw source CSVs are sorted by timestamp.

This step exists because Binance monthly dumps may contain rows out of chronological order.

### 2) Binary Packer (`binary_packer.py`)
Converts raw time-based rows into a custom binary format.

The packer:
- normalizes input into a strict 1-second timeline
- expands each month to its full second range
- stores missing ranges as explicit gap metadata

### 3) Orchestrator (`orchestrator.py`)
Builds gap-aware worker jobs from binary metadata.

It rebuilds `VALID` / `INVALID` segments and generates per-worker boundaries:
- `skip`
- `warmup`
- `do`

`warmup` exists so rolling-window logic starts only after enough valid contiguous history is available.

This ensures correct worker boundaries for rolling logic and sequential time simulation.

---

## Data (current setup)

- Binance BTCUSDT trade dumps
- 1-second internal resolution
- local dataset (not tracked in git)

---

## Status

Implemented:
- strict CSV sorting
- custom binary packer
- gap-aware orchestrator
- global mathematical validation (sanity checks)

Planned:
- per-worker invariant validation
- worker execution engine

---

Tech: Python 3.x, `struct`, `concurrent.futures`, `pandas` (preprocessing only).
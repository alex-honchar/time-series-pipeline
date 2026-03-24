# Pipeline Architecture

This document describes the internal mechanics of the preprocessing, planning, and simulation pipeline.

The system transforms raw, unordered CSV dumps into a compact binary format and executes deterministic simulations over valid data segments, with missing ranges handled explicitly. Data preparation and planning modules reside in the `pipeline/` directory, simulation logic in `simulation/`, and rendering logic in `visualization/`.

## 1. Sorter (`pipeline/sorter.py`)

**Goal:** Guarantee a strictly chronological timeline before binary packing.

Exchange dumps (including Binance monthly CSVs) may contain out-of-order rows.  
That breaks sequential processing and rolling logic.

**Mechanics:**
- Reads raw CSVs with `pandas`
- Sorts rows by timestamp column
- Writes clean sorted CSVs (headerless) for the packer

---

## 2. Binary Packer (`pipeline/binary_packer.py`)

**Goal:** Convert sorted rows into a compact, sequential binary stream with explicit missing-range metadata.

**Mechanics:**
- **Normalization:** Converts source timestamps to a strict 1-second timeline
- **Month Expansion:** Expands each month to its full second range
- **Binary Packing:** Packs per-second values into bytes via `struct` (e.g. `<i>`)
- **Missing-Range Detection:** Missing ranges exceeding a threshold (e.g. `GAP_THRESHOLD_SEC = 15`) are stored as metadata (`[gap_start, gap_end]`) in the file
- **Header Write:** Prepends a fixed-size binary header with file metadata

**Important:** The packer keeps a full per-second timeline. Micro-gaps (under 15s) are forward-filled with the last known price, while significant dropouts are explicitly recorded as metadata so downstream logic can distinguish `VALID` vs `INVALID` ranges.

### Binary layout (current)
1. **Header** (64 bytes)
2. **Gap metadata** (`gap_count × <II>`)
3. **Packed per-second values**

### Header metadata (current)
Current header fields include:
- signature
- version
- start timestamp
- end timestamp
- duration
- year
- month
- gap count
- symbol

---

## 3. Execution Planner (`pipeline/execution_planner.py`)

**Goal:** Assemble a contiguous buffer of valid tick data and an execution plan from fragmented binary files.

### The Core Problem: Files vs. Timeline

Data is stored in separate `.bin` files, but rolling logic needs a continuous timeline.

The execution planner reconstructs the global `VALID` / `INVALID` timeline from file metadata and maps it back to physical file offsets while preserving warmup boundaries.

It skips `INVALID` ranges, uses them to trigger warmup resets for the next `VALID` segment, and emits execution entries in the form:

`[cursor, timestamp, warmup_ticks, active_ticks]`

### Input

A collection of `.bin` files. For each file, the planner consumes:

* **Header metadata:** file-level metadata such as time bounds, version, symbol, etc.
* **Gap metadata:** explicit `[start, end]` pairs marking `INVALID` ranges
* **Tick data:** the packed per-second binary payload

### Output

The execution planner returns two values:

* **`assembled_ticks`**: a contiguous `int32` NumPy array containing the valid tick data required for execution
* **`execution_plan`**: a list of entries in this format:  
  `[cursor, timestamp, warmup_ticks, active_ticks]`

Each execution-plan entry refers to a slice of the assembled tick buffer.

### Execution Flow

1. **File Scan:** Read binary headers and gap metadata from eligible `.bin` files.
2. **Timeline Fragmentation:** Convert file-local missing ranges into `VALID` / `INVALID` timeline segments.
3. **Segment Coalescing:** Merge adjacent segments of the same type.
4. **File Alignment:** Convert file spans into relative tick intervals within the global timeline.
5. **Segment Mapping:** Resolve warmup and active coverage against physical file boundaries.
6. **Validation:** Check that mapped volume matches expected valid coverage.
7. **Payload Assembly:** Read the required tick ranges into one contiguous array and build the execution plan.

### Validation

A global volume check confirms that:

* all valid ticks are either assigned to execution or excluded due to missing warmup coverage
* the assembled payload volume matches the mapped timeline

### Guarantees

* No active segment is emitted without contiguous warmup history
* Warmup resets after invalid timeline gaps
* Output is deterministic for the same binary input set

---

## 4. Backtest Runner (`simulation/backtest_runner.py`)

**Goal:** Execute the assembled tick buffer over the execution plan.

The runner takes `assembled_ticks` and `execution_plan` from the `ExecutionPlanner`, restores warmup state for each segment, updates the stats across the plan, and runs capture/rendering on the final segment.

### Mechanics

* **Initialization:** Calls `ExecutionPlanner` to get `assembled_ticks` and `execution_plan`.
* **Shared Buffer:** Places `assembled_ticks` into `multiprocessing.shared_memory` and exposes it as NumPy views inside workers.
* **Execution Loop:** Iterates through the plan chronologically:
  1. Split the current entry into `warmup_part` and `active_part`.
  2. Run `run_warmup()` to initialize EMA/variance state.
  3. Run `run_passive_segment()` on regular segments to update `stats`.
  4. Run `run_capture_segment()` on the final segment and pass the result to `visualize()`.

### Current State

* Execution is currently single-threaded (`run_ids = range(1)`, `BACKTEST_WORKERS = 1`).
* Shared memory is already integrated, but current runs do not yet benefit from real parallel execution.
* The `stats` matrix is worker-local.

---

## 5. Segment Processing (`simulation/passive.py`, `simulation/capture.py`)

**Goal:** Run per-segment math in two modes: statistics accumulation and capture for rendering.

Both modules follow the same sequential tick-processing model and are compiled with Numba (`@njit(fastmath=True)`).

### Core Logic

* tick-by-tick processing in chronological order
* warmup-based initialization of EMA and variance state
* Z-score calculation and discretization
* ring-buffer state for delayed price references across configured time horizons

### Passive Mode (`passive.py`)

* `run_warmup()` initializes EMA and variance state from the warmup segment.
* `run_passive_segment()` processes the active segment tick by tick.
* Updates the 4D `stats` matrix (`stats[z1, z2, z3, z4]`) with EMA-based deltas and counts across configured time bins.
* Produces no frame data and performs no rendering-related work.

### Capture Mode (`capture.py`)

* Reuses the same warmup and sequential update flow as the passive path.
* Maintains a decaying 2D weight matrix during active processing.
* Maps signal state into Y-axis coordinates derived from EMA-based movement.
* Captures `video_frames` and `frame_meta` at fixed intervals for later rendering.

### Notes

* `capture.py` is the heavier rendering-oriented path.
* `passive.py` is the reduced non-rendering path used to build statistics before capture.

---

## 6. Visualization (`visualization/visualize.py`)

**Goal:** Render captured matrices into MP4 heatmaps.

### Mechanics

* Normalizes each frame by the column-wise sum of weights.
* Applies a power transform (`** 0.2`) to the normalized frame.
* Resizes the result and maps it with OpenCV `COLORMAP_TURBO`.
* Draws axes, timestamp, legend, reference lines, and realized price path.
* Exports the rendered frames as an MP4 video.

---

## Planned

- Core math optimization
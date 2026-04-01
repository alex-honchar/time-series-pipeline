# Pipeline Architecture

This file explains how the project works internally.

The pipeline starts from raw CSV trade dumps, sorts them, packs them into a custom binary format, reconstructs valid and invalid ranges from metadata, and runs simulation on the valid parts.

The code is split into three main areas:

- `pipeline/` for preprocessing, binary packing, and execution planning
- `simulation/` for warmup, replay, statistics, and capture
- `visualization/` for rendering captured output

## 1. Sorter (`pipeline/sorter.py`)

The sorter exists because raw exchange dumps are not always strictly chronological.

It reads raw CSV files with `pandas`, sorts rows by timestamp, and writes clean headerless CSVs for the binary packer.

## 2. Binary Packer (`pipeline/binary_packer.py`)

The binary packer converts sorted rows into a compact monthly binary format with explicit missing-range metadata.

It normalizes source timestamps to a strict 1-second timeline, expands each month to its full second range, packs per-second values with `struct`, and stores larger missing ranges as metadata inside the file.

Small gaps (under 15 seconds) are forward-filled with the last known price. Larger gaps are kept explicit so later stages can distinguish `VALID` and `INVALID` ranges.

### Binary layout (current)

1. Header (64 bytes)
2. Gap metadata (`gap_count × <II>`)
3. Packed per-second values

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

The execution planner builds a contiguous buffer of valid tick data and an execution plan from fragmented binary files.

The main issue here is that data is stored in separate `.bin` files, while the replay logic needs a continuous timeline. The planner reconstructs valid and invalid ranges from file metadata, maps them back to physical file offsets, applies warmup boundaries, and emits entries in the form:

`[cursor, timestamp, warmup_ticks, active_ticks]`

### Input

A collection of `.bin` files. For each file, the planner uses:

* **Header metadata:** file-level metadata such as time bounds, version, and symbol
* **Gap metadata:** explicit `[start, end]` pairs marking `INVALID` ranges
* **Tick data:** the packed per-second binary payload

### Output

The execution planner returns two values:

* **`assembled_ticks`**: a contiguous `int32` NumPy array containing the valid tick data required for execution
* **`execution_plan`**: a list of entries in this format:  
  `[cursor, timestamp, warmup_ticks, active_ticks]`

Each execution-plan entry refers to a slice of the assembled tick buffer.

### Execution flow

1. **File scan:** read binary headers and gap metadata from eligible `.bin` files
2. **Timeline fragmentation:** convert file-local missing ranges into `VALID` / `INVALID` timeline segments
3. **Segment coalescing:** merge adjacent segments of the same type
4. **File alignment:** convert file spans into relative tick intervals within the global timeline
5. **Segment mapping:** resolve warmup and active coverage against physical file boundaries
6. **Validation:** check that mapped volume matches expected valid coverage
7. **Payload assembly:** read the required tick ranges into one contiguous array and build the execution plan

### Validation

A global volume check confirms that:

* all valid ticks are either assigned to execution or excluded due to missing warmup coverage
* the assembled payload volume matches the mapped timeline

### Guarantees

* no active segment is emitted without contiguous warmup history
* warmup resets after invalid timeline gaps
* output is deterministic for the same binary input set

---

## 4. Backtest Runner (`simulation/backtest_runner.py`)

The backtest runner takes `assembled_ticks` and `execution_plan` from the `ExecutionPlanner`, restores warmup state for each segment, updates the main `stats` structure, and runs capture/rendering on the final segment.

### Notes

* execution is currently single-threaded (`run_ids = range(1)`, `BACKTEST_WORKERS = 1`)
* shared memory is already integrated, but current runs do not yet benefit from real parallel execution
* the `stats` matrix is worker-local

---

## 5. Segment Processing (`simulation/passive.py`, `simulation/capture.py`)

The segment-processing layer runs in two modes: statistics accumulation and capture for rendering.

### Core logic

* tick-by-tick processing in chronological order
* warmup-based initialization of EMA and variance state
* Z-score calculation and discretization
* ring-buffer state for delayed price references across configured time horizons

### Passive mode (`passive.py`)

* `run_warmup()` initializes EMA and variance state from the warmup segment
* `run_passive_segment()` processes the active segment tick by tick
* updates the 4D `stats` matrix (`stats[z1, z2, z3, z4]`) with EMA-based deltas and counts across configured time bins
* produces no frame data and performs no rendering-related work

### Capture mode (`capture.py`)

* reuses the same warmup and sequential update flow as the passive path
* maintains a decaying 2D weight matrix during active processing
* maps signal state into Y-axis coordinates derived from EMA-based movement
* captures `video_frames` and `frame_meta` at fixed intervals for later rendering

### Notes

* `capture.py` is the heavier rendering-oriented path
* `passive.py` is the reduced non-rendering path used to build statistics before capture

---

## 6. Visualization (`visualization/visualize.py`)

The visualization layer renders captured matrices as MP4 heatmaps.

For each frame it normalizes the matrix by column-wise weight, applies a power transform, resizes the result, maps it with OpenCV `COLORMAP_TURBO`, and overlays axes, timestamps, reference lines, and the realized price path.

# Pipeline Architecture

This document describes the internal mechanics of the data preparation and execution pipeline.

The system transforms raw, unordered CSV dumps into a compact binary format and supports shared-memory worker execution with deterministic boundaries. Data preparation and planning modules reside in the `pipeline/` directory, while the execution runner and core math logic sit at the root level.

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

**Goal:** Convert sorted rows into a compact, sequential binary stream with explicit gap metadata.

**Mechanics:**
- **Normalization:** Converts source timestamps to a strict 1-second timeline
- **Month Expansion:** Expands each month to its full second range
- **Binary Packing:** Packs per-second values into raw bytes via `struct` (e.g. `<i>`)
- **Gap Detection:** Missing ranges exceeding a threshold (e.g., `GAP_THRESHOLD_SEC = 15`) are stored as gap metadata (`[gap_start, gap_end]`) in the file
- **Header Write:** Prepends a fixed-size binary header with file metadata

**Important:** The packer keeps a full per-second timeline. Micro-gaps (under 15s) are forward-filled with the last known price, while significant dropouts are explicitly recorded as metadata so downstream logic can accurately distinguish `VALID` vs `INVALID` ranges.

### Binary layout (current)
1. **Header** (64 bytes)
2. **Gap metadata** (`gap_count × <II>`)
3. **Packed per-second values**

### Header metadata (current)
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
The execution planner reconstructs the global `VALID` / `INVALID` timeline from file metadata and maps it back to file offsets with warmup-aware boundaries. 

It skips `INVALID` gaps, using them to trigger warmup resets for the next `VALID` segment, and emits execution entries in the form:

`[cursor, timestamp, warmup_ticks, active_ticks]`

### Input

From each `.bin` file:

* Time bounds from the binary header
* Gap metadata describing `INVALID` ranges

### Output

The execution planner returns two values:

* **`assembled_ticks`**: a contiguous `int32` NumPy array with the valid tick data required for execution
* **`execution_plan`**: a list of entries in this format:
  `[cursor, timestamp, warmup_ticks, active_ticks]`

Each execution-plan entry refers to a slice of the assembled tick buffer.

### Execution Flow

1. **File Scan:** Read binary headers and gap metadata from eligible `.bin` files.
2. **Timeline Fragmentation:** Convert file-local gaps into `VALID` / `INVALID` timeline segments.
3. **Segment Coalescing:** Merge adjacent segments of the same type.
4. **File Alignment:** Convert file spans into relative tick intervals within the global timeline.
5. **Segment Mapping:** Resolve warmup and active coverage against physical file boundaries.
6. **Validation:** Check that mapped volume matches expected valid coverage.
7. **Payload Assembly:** Read the required tick ranges into one contiguous array and build the execution plan.

### Validation (Current)

A global volume check confirms that:

* all valid ticks are either assigned to execution or counted as lost warmup coverage,
* the assembled payload volume matches the mapped timeline.

### Guarantees

* No active segment is emitted without contiguous warmup history
* Warmup resets after invalid timeline gaps
* Output is deterministic for the same binary input set

---

## 4. Backtest Runner (`backtest_runner.py`)

**Goal:** Run backtest segments over a shared tick buffer.

### The Core Problem: Shared Data vs. Segment Execution

The execution planner produces a contiguous tick buffer and an execution plan, but the simulation still has to process each segment with warmup and active logic. The runner sets up shared memory for the assembled tick buffer and executes the plan through worker processes.

### Mechanics
* **Planning:** Calls the `ExecutionPlanner` to get `assembled_ticks` and `execution_plan`.
* **Shared Memory:** Creates a shared-memory block for `assembled_ticks` and exposes it to workers through NumPy views.
* **Worker Initialization:** Each worker attaches to the shared-memory block by name and stores the shared execution plan.
* **Execution Loop:**
    1. Slice `ticks_view` into `warmup_part` and `active_part` using offsets from the plan.
    2. Run `do_warmup` to initialize EMA and variance state.
    3. Run `do_active` to process the active segment and return the final tick's z-score bins.

### Current State
* The multiprocessing structure is in place, but current runs are still minimal (`range(1)`).
* Every worker currently iterates over the full `execution_plan`.
* Shared memory is used so the assembled tick buffer is not copied into each worker process.

### Guarantees
* All workers read from the same assembled tick buffer.
* Warmup and active processing follow the execution plan emitted by the execution planner.
* Shared memory is explicitly closed and unlinked during cleanup.

---

## 5. Segment Math (`segment_math.py`)

**Goal:** Run warmup and active calculations for each execution segment.

### Logic
* **`do_warmup`**: Initialize EMA and variance state from the warmup segment.
* **`do_active`**: Process the active segment tick-by-tick, update rolling state, and return discretized z-score bins for the final tick only.

### Implementation
* Core math is compiled with Numba (`njit`).
* EMA and variance are updated tick-by-tick.
* Z-scores are scaled and shifted into a fixed integer range (`0-60`).

### Rules
* Ticks must be processed in chronological order.
* Warmup must run before active evaluation.

---

## Planned
- Writing results to the shared `stats` array
- Core math optimization
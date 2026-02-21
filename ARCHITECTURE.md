# Pipeline Architecture

This document describes the internal mechanics of the data preparation and orchestration pipeline.

The system transforms raw, unordered CSV dumps into a compact binary format and distributes work across parallel workers with deterministic boundaries. All core modules reside in the `pipeline/` directory.

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

**Important:** The packer keeps a full per-second timeline. Micro-gaps (under 15s) are smoothly forward-filled, while significant dropouts are explicitly recorded as metadata so downstream logic can accurately distinguish `VALID` vs `INVALID` ranges.

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

## 3. Orchestrator (`pipeline/orchestrator.py`)

**Goal:** Build deterministic worker jobs for parallel time simulation using only binary metadata (headers + gaps), without reading the payload.

### The Core Problem: Files vs. Timeline
Data is stored as physical files, but rolling logic requires a continuous logical timeline.  
The orchestrator must split a global timeline into worker chunks, then convert them back into physical file offsets.

Every worker needs:
- **`skip`**: advance the file cursor
- **`warmup`**: prime the internal state (no evaluation)
- **`do`**: actual evaluation range

To achieve this, the orchestrator must:
- Map a global timeline of `VALID`/`INVALID` segments back to specific `.bin` files.
- Guarantee every `do` segment has a full `warmup` history.
- Stitch boundaries when a worker's `warmup` requirement spans across multiple files.
- Reset `warmup` expectations whenever an `INVALID` gap breaks the timeline.

### Input
From each `.bin` file:
- Time bounds (from the 64-byte header)
- Gap metadata (`INVALID` ranges)

### Output
Job lists for `MAX_WORKERS` in this format:  
`[file_name, skip, warmup, do]`

### Execution Flow
1. **Timeline Reconstruction:** Builds a global `VALID` / `INVALID` timeline from file metadata (headers + gaps).
2. **Chunk Allocation:** Divides the global timeline into roughly equal worker chunks (`base_chunk`, in ticks).
3. **Job Resolution:** Converts abstract chunks into specific `skip / warmup / do` file boundaries, including warmup stitching across worker boundaries.

### Validation (Current)
A global mathematical check at the end of execution:
- Verifies `SUM(warmup + do) == TOTAL_VALID + (WARMUP * (MAX_WORKERS - 1))`
- Confirms global processed volume is consistent (including duplicated warmup across worker boundaries)

### Guarantees
- Deterministic worker boundaries across runs
- No `do` execution without contiguous `warmup` history
- `warmup` resets after invalid segments

---

## 4. Planned
- **Per-worker validation:** Independent checks for worker-level coverage (expected `VALID` ticks vs. assigned `warmup/do`)
- **Worker execution:** Implement the engine that consumes `[skip, warmup, do]` jobs
# Time-Series Data Pipeline and Simulation Project

This is a Python project that takes raw aggTrades data, packs it into a custom binary format, and runs simulation on top of that data.

I started this project as a practical way to learn programming more seriously. I chose Binance market data mainly because it was freely available, while the real goal was to build something larger than small exercises or toy scripts.

At the beginning, I barely knew Python. I used the project as a way to learn by doing: working through raw data, project structure, simulation logic, and performance questions in one codebase.

The repository is split into three parts:

- `pipeline/` — preprocessing, binary packing, execution planning
- `simulation/` — warmup, replay, statistics, capture
- `visualization/` — rendering simulation output as MP4 heatmaps

## What it does

The current pipeline:

- sorts raw CSV data by timestamp
- packs the data into a custom monthly binary format
- keeps missing ranges explicit in metadata
- assembles valid data into replayable segments
- runs simulation over those segments
- renders one part of the captured output as MP4 heatmaps

## Performance

**Test machine:** `Ryzen 7 5800X` (single-threaded), `DDR4-3400`

| Configuration | Throughput | Ticks / s |
| :--- | :--- | :--- |
| **Engine** | **236 years/s** | **~7.5B** |
| **Engine + Simulation** | **1.2 years/s** | **~39M** |

The **Engine** result reflects the engine by itself, with minimal per-tick math.

### Why simulation is slower

The simulation I've built on top is still heavy. The main bottleneck is memory access: every tick updates a large 4D array, while EMA, variance state, and Z-score updates add extra work on top.

## Data

Current setup:

- Binance BTCUSDT aggTrades
- internal resolution: 1 second
- dataset is stored locally and not included in the repository

## Tech stack

Python 3.x, NumPy, Numba, pandas, OpenCV, `multiprocessing.shared_memory`, `struct`, `concurrent.futures`

## More detail

For the internal mechanics and module-level breakdown, see [`ARCHITECTURE.md`](ARCHITECTURE.md). 
"""Launch backtest workers."""

import concurrent.futures
import time
from multiprocessing import shared_memory

import numpy as np

from config import Config
from pipeline.execution_planner import ExecutionPlanner
from simulation.capture import run_capture_segment
from simulation.passive import run_passive_segment
from simulation.warmup import run_warmup
from visualization.visualize import visualize

cfg = Config()

ticks_view = None
worker_plan = None
existing_shm = None

def init_worker(
    shm_name: str,
    shm_shape: tuple[int, ...],
    shm_dtype: np.dtype,
    execution_plan: list[tuple[int, int, int, int]],
) -> None:
    """Attach the worker to shared memory and store execution instructions."""
    global ticks_view, existing_shm, worker_plan
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    ticks_view = np.ndarray(shape=shm_shape, dtype=shm_dtype, buffer=existing_shm.buf)
    worker_plan = execution_plan


def process_segments(_run_id: int) -> None:
    """Process warmup and active history segments defined by worker instructions."""
    global ticks_view, worker_plan

    windows = np.array([30.0, 125.0, 625.0, 14400.0], dtype=np.float64)

    stats = np.zeros(
        shape=(cfg.Z_SPACE, cfg.Z_SPACE, cfg.Z_SPACE, cfg.Z_SPACE),
        dtype=cfg.STATS_DTYPE
    )

    whole_start = time.perf_counter_ns()
    total_plans = len(worker_plan)
    capture_offset = 4
    to_capture = total_plans - capture_offset

    print(f"segments: {total_plans}, capture segment: {to_capture}")

    for i, (cursor, timestamp, warmup_ticks, active_ticks) in enumerate(worker_plan):
        warmup_part = ticks_view[cursor : cursor + warmup_ticks]
        active_part = ticks_view[
            cursor + warmup_ticks : cursor + warmup_ticks + active_ticks
        ]

        if i+1 < (total_plans-capture_offset):
            emas, variances = run_warmup(warmup_part, windows)
            stats = run_passive_segment(
                active_part, windows, emas, variances, stats
            )
            if (i+1) % 10 == 0:
                print(f"Passive: {i+1}")

        elif i+1 == (to_capture):
            emas, variances = run_warmup(warmup_part, windows)
            print(f"Capture: {i+1}")
            trapped_matrix, trapped_meta = run_capture_segment(
                active_part, windows, emas, variances, stats, timestamp
            )
            print("Rendering video")
            visualize(trapped_matrix, trapped_meta)

    whole_end = time.perf_counter_ns()
    whole_time = (whole_end-whole_start)/1e9
    print(f"Time: {whole_time} sec")


def print_engine_specs(assembled_ticks: np.ndarray, execution_plan: list) -> None:
    """Print run specs."""
    print(f"ticks loaded: {len(assembled_ticks):,}")
    print(f"segments: {len(execution_plan)}")
    print(f"workers: {cfg.BACKTEST_WORKERS}")
    print(f"matrix: {cfg.TIME_BINS.size} x {cfg.PRICE_BINS}")
    print(f"z-space: {cfg.Z_SPACE}^4")

def run() -> None:
    """Run the backtest pipeline."""
    shared_mem = None
    try:
        execution_planner = ExecutionPlanner(cfg.FORMATTED_DIR)
        assembled_ticks, execution_plan = execution_planner.build()

        print_engine_specs(assembled_ticks, execution_plan)

        shared_mem = shared_memory.SharedMemory(
            create=True, size=assembled_ticks.nbytes
        )
        shared_tick_buffer = np.ndarray(
            shape=assembled_ticks.shape,
            dtype=assembled_ticks.dtype,
            buffer=shared_mem.buf,
        )
        shared_tick_buffer[:] = assembled_ticks[:]

        shm_name = shared_mem.name
        shm_shape = shared_tick_buffer.shape
        shm_dtype = shared_tick_buffer.dtype

        run_ids = range(1)

        with concurrent.futures.ProcessPoolExecutor(
            max_workers=cfg.BACKTEST_WORKERS,
            initializer=init_worker,
            initargs=(shm_name, shm_shape, shm_dtype, execution_plan),
        ) as executor:
            futures = [executor.submit(process_segments, run_id) for run_id in run_ids]
            for future in concurrent.futures.as_completed(futures):
                future.result()

    except (Exception, KeyboardInterrupt) as e:
        print(f"Error type: {type(e).__name__}")
        print(f"Error details: {repr(e)}")

    finally:
        if shared_mem is not None:
            print("Cleaning shm")
            shared_mem.close()
            shared_mem.unlink()
            print("Cleaned")


if __name__ == "__main__":
    run()

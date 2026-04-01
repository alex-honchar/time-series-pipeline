"""Test speed."""

import concurrent.futures
import time
from multiprocessing import shared_memory

import numpy as np

from benchmark.benchmark_sum import test_engine_speed
from config import Config
from pipeline.execution_planner import ExecutionPlanner

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
    """Run numba warmup and test speed."""
    global ticks_view, worker_plan

    repeats = 100

    #warmup numba
    for cursor, _, warmup_ticks, active_ticks in worker_plan:
        active_part = ticks_view[
            cursor + warmup_ticks : cursor + warmup_ticks + active_ticks
        ]

        test_engine_speed(active_part)

    ticks_done = repeats * sum(active_ticks for _, _, _, active_ticks in worker_plan)

    whole_start = time.perf_counter_ns()
    prices_sum = 0

    for _ in range(repeats):
        for cursor, _, warmup_ticks, active_ticks in worker_plan:
            active_part = ticks_view[
                cursor + warmup_ticks : cursor + warmup_ticks + active_ticks
            ]
            prices_sum += test_engine_speed(active_part)

    whole_end = time.perf_counter_ns()
    whole_time = (whole_end - whole_start) / 1e9
    print(f"Speed: {ticks_done / whole_time} ticks per sec")
    print(f"Prices sum: {prices_sum}")

def run() -> None:
    """Run the backtest pipeline."""
    shared_mem = None
    try:
        execution_planner = ExecutionPlanner(cfg.FORMATTED_DIR)
        assembled_ticks, execution_plan = execution_planner.build()

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
            futures = [
                executor.submit(process_segments, run_id)
                for run_id in run_ids
            ]
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

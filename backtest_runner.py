"""Launch backtest workers.""" # WIP

import concurrent.futures
from multiprocessing import shared_memory

import numpy as np

from config import Config
from pipeline.execution_planner import ExecutionPlanner
from segment_math import do_active, do_warmup

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
    for cursor, _, warmup_ticks, active_ticks in worker_plan:
        warmup_part = ticks_view[cursor : cursor + warmup_ticks]
        active_part = ticks_view[
            cursor + warmup_ticks : cursor + warmup_ticks + active_ticks
        ]

        emas, variances = do_warmup(warmup_part, windows)
        zscores = do_active(active_part, windows, emas, variances)

    print(zscores)


def run() -> None:
    """Run the backtest pipeline."""
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
            futures = [executor.submit(process_segments, run_id) for run_id in run_ids]
            for future in concurrent.futures.as_completed(futures):
                future.result()

    except (Exception, KeyboardInterrupt) as e:
        print(f"Error type: {type(e).__name__}")
        print(f"Error details: {repr(e)}")

    finally:
        print("Cleaning shm")
        shared_mem.close()
        shared_mem.unlink()
        print("Cleaned")


if __name__ == "__main__":
    run()

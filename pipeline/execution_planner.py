"""Assemble a contiguous valid tick buffer and execution plan."""
import struct
from pathlib import Path

import numpy as np

from config import Config

cfg = Config()

class ExecutionPlanner:
    """Stateful coordinator for binary timeline mapping and instruction generation."""

    __slots__ = [
        "input_path",
        "file_spans",
        "aligned_files",
        "fragmented_segments",
        "coalesced_segments",
        "mapped_file_chunks",
        "total_valid_ticks",
        "lost_valid_ticks",
        "gap_bytes_map",
    ]

    input_path: Path
    file_spans: list[tuple[Path, int, int, int]]
    aligned_files: list[tuple[Path, int]]
    fragmented_segments: list[tuple[str, int]]
    coalesced_segments: list[tuple[str,int]]
    mapped_file_chunks: list[tuple[Path, int, int, int]]
    total_valid_ticks: int
    slost_valid: int
    gap_bytes_map: dict[Path, int]

    def __init__(self, input_path: Path) -> None:
        """Initialize orchestator state."""
        self.input_path = input_path
        self.file_spans = []
        self.aligned_files = []
        self.fragmented_segments = []
        self.coalesced_segments = []
        self.mapped_file_chunks = []
        self.total_valid_ticks = 0
        self.lost_valid_ticks = 0
        self.gap_bytes_map = {}

    def build(self) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
        """Execute the full orchestrator pipeline."""
        self._unpack_input_files()
        self._align_file_intervals()
        self._coalesce_segments()
        self._map_segments_to_files()
        self._validate_job_volume()
        main, main_instructions = self._assemble_payload()

        return main, main_instructions

    def _unpack_input_files(self) -> None:
        """Filter input files, create timeline fragmented segment map."""
        input_files = sorted(self.input_path.glob("*.bin"))
        for file in input_files:
            with open(file, "rb") as reader:
                unpacked = struct.unpack(
                    cfg.HEADER_FORMAT, reader.read(cfg.HEADER_SIZE)
                )

                signature = unpacked[0]  # 0P00
                version = unpacked[1]
                start_ts = unpacked[2]
                end_ts = unpacked[3]
                duration = unpacked[4]
                year = unpacked[5]
                _ = unpacked[6]
                gap_count = unpacked[7]
                _ = unpacked[8].decode('ascii').strip('\x00')

                if (
                    signature == b'0P00'
                    and version == 1
                    and (cfg.START_YEAR <= year < cfg.WALK_FORWARD_YEAR)
                ):
                    self.file_spans.append((file, duration, start_ts, end_ts))
                    self.gap_bytes_map[file] = (gap_count*cfg.GAP_RECORD_BYTE_SIZE)
                    gaps = []

                    if gap_count > 0:
                        gap_bytes = gap_count*cfg.GAP_RECORD_BYTE_SIZE
                        gap_raw_bytes = reader.read(gap_bytes)

                        for gap_start, gap_end in struct.iter_unpack(
                            "<II", gap_raw_bytes
                        ):
                            gaps.append((gap_start, gap_end))

                    self._fragment_file_timeline(start_ts, end_ts, gaps)

    def _fragment_file_timeline(
        self, start_ts: int, end_ts: int, gaps: list[tuple[int, int]]
    ) -> None:
        """Partition the file timeline on valid and invalid segments."""
        cursor = start_ts
        for gap_start, gap_end in gaps:
            if cursor < gap_start:
                duration = gap_start - cursor
                self.fragmented_segments.append(("VALID", duration))

            gap_duration = gap_end - gap_start
            self.fragmented_segments.append(("INVALID", gap_duration))
            cursor = gap_end

        if cursor < end_ts:
            duration = end_ts - cursor
            self.fragmented_segments.append(("VALID", duration))

    def _coalesce_segments(self,) -> None:
        """Coalesce fragmented segments into solid ones."""
        status = self.fragmented_segments[0][0]
        segment_duration = 0

        for raw_status, count in self.fragmented_segments:

            if raw_status == "VALID":
                self.total_valid_ticks += count

            if status == raw_status:
                segment_duration += count

            elif status != raw_status:
                self.coalesced_segments.append((status, segment_duration))
                segment_duration = count
                status = raw_status

        self.coalesced_segments.append((status, segment_duration))

    def _align_file_intervals(self) -> None:
        """Resolve file boundaries into relative tick counts."""
        main_start_ts = self.file_spans[0][2]
        ticks_done = 0

        for file_name, _, _, end_ts in self.file_spans:
            ticks_in_file = (end_ts - main_start_ts) - ticks_done

            self.aligned_files.append((file_name, ticks_in_file))
            ticks_done += ticks_in_file

    def _map_segments_to_files(self) -> None:
        """Map logical segments onto physical file boundaries."""
        warmup_need = cfg.WARMUP
        seg_idx = 0
        seg_length = self.coalesced_segments[seg_idx][1]

        for path, file_duration in self.aligned_files:
            to_skip_ticks = 0
            to_warmup_ticks = 0
            to_do_ticks = 0

            while file_duration > 0:

                seg_idx, seg_length = self._ensure_active_segment(seg_idx, seg_length)
                if self.coalesced_segments[seg_idx][0] == "INVALID":
                    warmup_need = cfg.WARMUP
                    take = min(file_duration, seg_length)
                    to_skip_ticks += take
                    file_duration -= take
                    seg_length -= take

                seg_idx, seg_length = self._ensure_active_segment(seg_idx, seg_length)
                if warmup_need > 0 and self.coalesced_segments[seg_idx][0] == "VALID":
                    if seg_length > warmup_need:
                        take = min(file_duration, seg_length, warmup_need)
                        to_warmup_ticks += take
                        warmup_need -= take
                        file_duration -= take
                        seg_length -= take

                    else:
                        take = min(file_duration, seg_length)
                        self.lost_valid_ticks += take
                        to_skip_ticks += take
                        file_duration -= take
                        seg_length -= take

                seg_idx, seg_length = self._ensure_active_segment(seg_idx, seg_length)
                if warmup_need == 0 and self.coalesced_segments[seg_idx][0] == "VALID":
                    take = min(file_duration, seg_length)
                    to_do_ticks += take
                    file_duration -= take
                    seg_length -= take

                if to_warmup_ticks > 0 or to_do_ticks > 0:
                    job = (path, to_skip_ticks, to_warmup_ticks, to_do_ticks)
                    self.mapped_file_chunks.append(job)
                    to_skip_ticks = to_skip_ticks + to_warmup_ticks + to_do_ticks
                    to_warmup_ticks = 0
                    to_do_ticks = 0

    def _ensure_active_segment(self, seg_idx: int, seg_length: int) -> tuple[int, int]:
        """Advance to the next segment if the current one has ended."""
        if seg_length == 0:
            seg_idx += 1
            seg_length = self.coalesced_segments[seg_idx][1]

        return seg_idx, seg_length

    def _validate_job_volume(self) -> None:
        """Compare expected ticks to have to actual ticks in job."""
        expected_ticks = self.total_valid_ticks
        actual_ticks = 0

        for _, _, to_warmup_ticks, to_do_ticks in self.mapped_file_chunks:
            actual_ticks += to_warmup_ticks + to_do_ticks

        tick_diff = expected_ticks - (actual_ticks + self.lost_valid_ticks)
        print(f"diff = {tick_diff} / actual = {actual_ticks}")
        if tick_diff != 0:
            raise RuntimeError(f"Job volume mismatch: diff={tick_diff}")

    def _assemble_payload(self) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
        """Construct a single continuous data array with offset instructions."""
        assembled_ticks = np.empty(
            dtype='<i4', shape=self.total_valid_ticks-self.lost_valid_ticks
        )
        execution_plan = []
        cursor = 0
        start_ts_by_file = {item[0]: item[2] for item in self.file_spans}

        for path, to_skip, warmup_ticks, active_ticks in self.mapped_file_chunks:
            chunk_length = warmup_ticks + active_ticks

            byte_offset = (
                to_skip * cfg.TICK_BYTE_SIZE
                + cfg.HEADER_SIZE
                + self.gap_bytes_map[path]
            )

            chunk_data = np.memmap(
                filename=path,
                dtype='<i4',
                offset=byte_offset,
                mode='r',
                shape=(warmup_ticks + active_ticks,),
            )

            assembled_ticks[cursor : cursor + chunk_length] = chunk_data
            cursor += chunk_length

            start_ts = start_ts_by_file[path]

            if warmup_ticks == 0:
                execution_plan[-1][-1] = execution_plan[-1][-1] + active_ticks
            else:
                timestamp = start_ts + to_skip
                instruction_cursor = cursor - chunk_length
                execution_plan.append(
                    [instruction_cursor, timestamp, warmup_ticks, active_ticks]
                )
        execution_plan = [tuple(inst) for inst in execution_plan]
        return assembled_ticks, execution_plan


if __name__ == "__main__":
    test = ExecutionPlanner(cfg.FORMATTED_DIR)
    test.build()

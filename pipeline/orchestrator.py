import struct
import concurrent.futures
import pathlib
import numpy as np
from numba import njit
import time
from dataclasses import dataclass, field
import json

MAX_WORKERS = 2
HEADER_SIZE = 64
INPUT_DIR = pathlib.Path("/home/alex/BTCUSDT/")
START_YEAR = 2025
WALK_FORWARD_YEAR = 2026
HEADER_FORMAT = '< 4s I I I I I I I 12s 20x'
WARMUP = 86400
GAP_SIZE = 8

class Orchestrator:
    __slots__ = [
            'input_path',
            'file_spans',
            'raw_segments',
            'merged_segments',
            'raw_worker_jobs',
            'resolved_worker_jobs',

            'total_valid_ticks',
        ]

    def __init__(self, input_path):
        self.input_path = input_path
        self.file_spans = []
        self.raw_segments = []
        self.merged_segments = []
        self.raw_worker_jobs = []
        self.resolved_worker_jobs = []
        
        self.total_valid_ticks = 0
        
    def orchestrate(self):
        input_files = list(INPUT_DIR.glob("*.bin"))
        input_files.sort()

        for file in input_files:

            with open(file, "rb") as reader:
                unpacked = struct.unpack(HEADER_FORMAT, reader.read(HEADER_SIZE))

                signature = unpacked[0] # 0P00
                version =   unpacked[1]
                start_ts =  unpacked[2]
                end_ts =    unpacked[3]
                duration =  unpacked[4]
                year =      unpacked[5]
                month =     unpacked[6]
                gap_count = unpacked[7]
                symbol =    unpacked[8].decode('ascii').strip('\x00')

                if signature == b'0P00' and version == 1 and (START_YEAR <= year < WALK_FORWARD_YEAR):
                    self.file_spans.append((file, duration, start_ts, end_ts))
                    gaps = []

                    if gap_count > 0:
                        bytes_to_read = gap_count*GAP_SIZE
                        gap_raw_bytes = reader.read(bytes_to_read)
                        
                        for gap_start, gap_end in struct.iter_unpack("<II", gap_raw_bytes):
                            gaps.append((gap_start, gap_end))
                        
                    self._extract_segments(start_ts, end_ts, gaps)

        self._merge_segments()
        self._map_worker_boundaries()
        self._calculate_warmups_and_skips()
        self._fill_warmup_gaps()
        self._validate_job_volume()

    def _extract_segments(self, start_ts, end_ts, gaps):
        cursor = start_ts

        for gap_start, gap_end in gaps:
            if cursor < gap_start:
                self._process_chunk(cursor, gap_start)
                
            gap_duration = gap_end - gap_start
            self.raw_segments.append(("INVALID", gap_duration))
            cursor = gap_end

        if cursor < end_ts:
            self._process_chunk(cursor, end_ts)

    def _process_chunk(self, start_ts, end_ts):
        duration = end_ts - start_ts
        self.raw_segments.append(("VALID", duration))

    def _merge_segments(self):
        status = self.raw_segments[0][0]
        segment_duration = 0
        
        for raw_status, count in self.raw_segments:
            
            if raw_status == "VALID":
                self.total_valid_ticks += count
                print(self.total_valid_ticks)

            if status == raw_status:
                segment_duration += count
            
            elif status != raw_status:
                self.merged_segments.append([status, segment_duration])
                segment_duration = count
                status = raw_status
                
        self.merged_segments.append([status, segment_duration])
        
    def _map_worker_boundaries(self):
        total = sum(item[1] for item in self.merged_segments)
        base_chunk = (total-WARMUP) // MAX_WORKERS #last worker does as much ticks as every worker
        main_start_ts = self.file_spans[0][2]
        ticks_done_glob = 0

        for _ in range(MAX_WORKERS):
            ticks_done_worker = 0
            worker_job_list = []

            for file_name, _, start_ts, end_ts in self.file_spans:
                file_low_border = (start_ts - main_start_ts)
                file_high_border = (end_ts  - main_start_ts)

                if (file_low_border <= ticks_done_glob < file_high_border) and (ticks_done_worker < base_chunk):
                   
                    we_need_to_write_more = base_chunk - ticks_done_worker
                    allowed_ticks_in_file = file_high_border - ticks_done_glob

                    if we_need_to_write_more >= allowed_ticks_in_file:
                        we_write = allowed_ticks_in_file

                    elif we_need_to_write_more < allowed_ticks_in_file:
                        we_write = we_need_to_write_more

                    start_tick_in_file = ticks_done_glob - file_low_border
                    worker_job_list.append([file_name, start_tick_in_file, we_write])
                    ticks_done_glob += we_write
                    ticks_done_worker += we_write

            self.raw_worker_jobs.append(worker_job_list)
        
    def _calculate_warmups_and_skips(self):
        for big_job in self.raw_worker_jobs:
            cursor_warmup = 86400
            worker_job_list = []

            for path, start, length_left_in_file in big_job:
                to_skip_ticks = start
                to_warmup_ticks = 0
                to_do_ticks = 0

                while length_left_in_file > 0:
                    current_seg = self.merged_segments[0]

                    if current_seg[1] == 0:
                        self.merged_segments.pop(0)
                        current_seg = self.merged_segments[0]

                    if current_seg[0] == "INVALID":
                        cursor_warmup = 86400

                        if length_left_in_file >= current_seg[1]:
                            to_skip_ticks += current_seg[1]
                            length_left_in_file -= current_seg[1]
                            current_seg[1] = 0
                        
                        else:
                            current_seg[1] -= length_left_in_file
                            to_skip_ticks += length_left_in_file
                            length_left_in_file = 0
                            
                    if current_seg[1] == 0:
                        self.merged_segments.pop(0)
                        current_seg = self.merged_segments[0]

                    if cursor_warmup > 0 and current_seg[0] == "VALID":
                        
                        if current_seg[1] > cursor_warmup:

                            if length_left_in_file >= cursor_warmup:
                                to_warmup_ticks += cursor_warmup
                                length_left_in_file -= cursor_warmup
                                current_seg[1] -= cursor_warmup
                                cursor_warmup = 0
                            
                            else:
                                if length_left_in_file > current_seg[1]:
                                    to_warmup_ticks += current_seg[1]
                                    length_left_in_file -= current_seg[1]
                                    cursor_warmup -= current_seg[1]
                                    current_seg[1] = 0
                                else:
                                    current_seg[1] -= length_left_in_file
                                    to_warmup_ticks += length_left_in_file
                                    cursor_warmup -= length_left_in_file
                                    length_left_in_file = 0
                        
                        else:
                            cursor_warmup = 86400
                            if length_left_in_file >= current_seg[1]:
                                to_skip_ticks += current_seg[1]
                                length_left_in_file -= current_seg[1]
                                current_seg[1] = 0
                            
                            else:
                                current_seg[1] -= length_left_in_file
                                to_skip_ticks += length_left_in_file
                                length_left_in_file = 0
                                
                    if current_seg[1] == 0:
                        self.merged_segments.pop(0)
                        current_seg = self.merged_segments[0]

                    if cursor_warmup == 0 and current_seg[0] == "VALID":
                        if length_left_in_file >= current_seg[1]:
                            to_do_ticks += current_seg[1]
                            length_left_in_file -= current_seg[1]
                            current_seg[1] = 0
                        else:
                            current_seg[1] -= length_left_in_file
                            to_do_ticks += length_left_in_file
                            length_left_in_file = 0
                            
                    if current_seg[1] == 0:
                        self.merged_segments.pop(0)
                        current_seg = self.merged_segments[0]
                    
                    if to_warmup_ticks > 0 or to_do_ticks > 0:
                        job = [path, to_skip_ticks, to_warmup_ticks, to_do_ticks]
                        worker_job_list.append(job)
                        to_skip_ticks = to_skip_ticks + to_warmup_ticks + to_do_ticks
                        to_warmup_ticks = 0
                        to_do_ticks = 0

            self.resolved_worker_jobs.append(worker_job_list)
            
    def _fill_warmup_gaps(self):
        for i in range(len(self.resolved_worker_jobs)-1):
            this_file_name, this_to_skip_ticks, this_to_warmup_ticks, this_to_do_ticks = self.resolved_worker_jobs[i][-1] 

            to_do_more = WARMUP
            we_need_more_warmup = 0
            if 0 < this_to_warmup_ticks < 86400:
                we_need_more_warmup = WARMUP - this_to_warmup_ticks

            skip_to_write = 0
            warmup_to_write = 0
            todo_to_write = 0
            
            for next_file_name, next_to_skip_ticks, next_to_warmup_ticks, next_to_do_ticks in self.resolved_worker_jobs[i+1]:

                if to_do_more > 0:
                    available_ticks_to_write = next_to_warmup_ticks
                   
                    if we_need_more_warmup > 0:

                        if available_ticks_to_write > we_need_more_warmup:
                            skip_to_write = next_to_skip_ticks
                            warmup_to_write += we_need_more_warmup
                            to_do_more -= we_need_more_warmup
                            available_ticks_to_write -= we_need_more_warmup
                            we_need_more_warmup -= we_need_more_warmup
                        
                        else:
                            skip_to_write = next_to_skip_ticks
                            warmup_to_write += available_ticks_to_write
                            to_do_more -= available_ticks_to_write
                            we_need_more_warmup -= available_ticks_to_write
                            available_ticks_to_write -= available_ticks_to_write
                    
                    if available_ticks_to_write >= to_do_more:
                        skip_to_write = next_to_skip_ticks
                        todo_to_write += to_do_more
                        available_ticks_to_write -= to_do_more
                        to_do_more -= to_do_more

                        job = [next_file_name, skip_to_write, warmup_to_write, todo_to_write]
                        self.resolved_worker_jobs[i].append(job)
                        skip_to_write = 0
                        warmup_to_write = 0
                        todo_to_write = 0
                    
                    if available_ticks_to_write < to_do_more:
                        skip_to_write = next_to_skip_ticks
                        todo_to_write += available_ticks_to_write
                        to_do_more -= available_ticks_to_write
                        available_ticks_to_write -= available_ticks_to_write

                        job = [next_file_name, skip_to_write, warmup_to_write, todo_to_write]
                        self.resolved_worker_jobs[i].append(job)
                        skip_to_write = 0
                        warmup_to_write = 0
                        todo_to_write = 0

        last_job_file_name, last_job_to_skip_ticks, last_job_to_warmup_ticks, last_job_to_do_ticks = self.resolved_worker_jobs[-1][-1]

        if self.merged_segments[0][0] == "VALID" and self.merged_segments[0][1] == WARMUP:
            if last_job_to_do_ticks > 0:
                job_for_the_last = [last_job_file_name, last_job_to_skip_ticks+last_job_to_warmup_ticks+last_job_to_do_ticks, 0, WARMUP]
                self.resolved_worker_jobs[-1].append(job_for_the_last)
                print("last correct")
            else:
                more_warmup = WARMUP - last_job_to_warmup_ticks
                job_for_the_last = [last_job_file_name, last_job_to_skip_ticks+last_job_to_warmup_ticks+last_job_to_do_ticks, more_warmup, WARMUP-more_warmup]
                self.resolved_worker_jobs[-1].append(job_for_the_last)
                print("last weird")
        else:
            raise RuntimeError("Unexpected end of segments")
        
        print(self.resolved_worker_jobs)

    def _validate_job_volume(self):
        expected_ticks = self.total_valid_ticks + (WARMUP*(MAX_WORKERS-1))
        actual_ticks = 0
        for worker_job in self.resolved_worker_jobs:
            for _, _, to_warmup_ticks, to_do_ticks in worker_job:
                actual_ticks += (to_warmup_ticks+to_do_ticks)

        print(f"expected {expected_ticks} / actual {actual_ticks}")
        tick_diff = expected_ticks - actual_ticks
        if tick_diff != 0:
            raise RuntimeError(f"Job volume mismatch: diff={tick_diff}")
        
if __name__ == "__main__":
    orchestrator = Orchestrator(INPUT_DIR)
    orchestrator.orchestrate()

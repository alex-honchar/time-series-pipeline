"""Render captured frames into mp4 video."""

import time
from datetime import datetime, timezone

import cv2
import numpy as np

from config import Config

cfg = Config()

FULL_X = 1920
FULL_Y = 1080

GRAPH_X = 1875
GRAPH_Y = 1060

OFFSET_X = FULL_X - GRAPH_X
OFFSET_Y = FULL_Y - GRAPH_Y

TIME_BIN_STEP = 1
PRICE_BIN_STEP = 1

CANVAS_BACKGROUND = 0
TEXT_COLOR = 255


def visualize(trapped_matrix: np.ndarray, trapped_meta: np.ndarray) -> None:
    """Draw heatmaps, time and price bins, realized movements, and timestamps."""
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    start_time = int(time.time())
    video_path = cfg.ROOT / "videos" / f"{start_time}.mp4"
    out = cv2.VideoWriter(str(video_path), fourcc, 60.0, (FULL_X, FULL_Y))

    for frame in range(trapped_matrix.shape[0]):

        canvas = draw_heatmap(trapped_matrix, frame)
        draw_time_bins(canvas)
        draw_price_bins(canvas)
        draw_line(canvas)
        draw_price_meta(trapped_meta, frame, canvas)
        draw_text(canvas)
        draw_time_meta(trapped_meta, frame, canvas)

        out.write(canvas)

    out.release()
    print("MP4 Done.")



def draw_heatmap(trapped_matrix: np.ndarray, frame: int) -> np.ndarray:
    """Draw heatmap."""
    frame2d = trapped_matrix[frame].astype(np.float32)
    axis_weight = np.sum(frame2d, axis=1, keepdims=True)

    weight_frame = np.zeros_like(frame2d)
    weight_frame = np.divide(
        frame2d, axis_weight, out=weight_frame, where=(axis_weight != 0)
    )

    weight_frame = weight_frame ** 0.18

    brightness_frame  = (weight_frame*255).astype(np.uint8)
    rotated_frame = np.ascontiguousarray(np.flipud(brightness_frame.T))

    resized_frame = cv2.resize(
        rotated_frame, (GRAPH_X, GRAPH_Y), interpolation=cv2.INTER_LANCZOS4
    )

    rgb_frame = cv2.applyColorMap(resized_frame, cv2.COLORMAP_TURBO)

    canvas = np.full((FULL_Y, FULL_X, 3,), CANVAS_BACKGROUND, dtype=np.uint8)
    canvas[0:GRAPH_Y, OFFSET_X:1920] = rgb_frame

    return canvas



def draw_time_bins(canvas:  np.ndarray) -> None:
    """Draw time bins."""
    total_bins = cfg.TIME_BINS.size
    time_bin_step = int(GRAPH_X/total_bins)
    for i, time_bin in enumerate(cfg.TIME_BINS):
        if i % TIME_BIN_STEP == 0:
            cv2.putText(
                canvas,
                str(time_bin/3600)+"h",
                (4+OFFSET_X+(i*time_bin_step),
                FULL_Y-5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (TEXT_COLOR, TEXT_COLOR, TEXT_COLOR),
                1,
                cv2.LINE_AA
            )

def draw_price_bins(canvas: np.ndarray) -> None:
    """Draw price bins."""
    price_step = (1/cfg.PRICE_STEP)*100
    start = cfg.CENTER_BIN * (price_step)

    price_bins = []
    for i in range(cfg.PRICE_BINS):
        price_bins.append(2 + (GRAPH_Y/cfg.PRICE_BINS)*i)

    for i in range(cfg.PRICE_BINS):
        if i % PRICE_BIN_STEP == 0 or i == cfg.CENTER_BIN:
            value = start - (price_step*i)
            text = str(f"{value:.2f}%")
            y_offset = int(price_bins[i])
            x_offset = 10
            if value < 0:
                x_offset = 0
            cv2.putText(
                canvas,
                text,
                (x_offset, 5 + y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.3,
                (TEXT_COLOR, TEXT_COLOR, TEXT_COLOR),
                1,
                cv2.LINE_AA
            )

def draw_time_meta(
        trapped_meta: np.ndarray, frame: int, canvas:  np.ndarray
    ) -> None:
    """Draw time meta."""
    timestamp = trapped_meta[frame]["timestamp"]
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    text = dt.strftime("%Y-%m-%d %H:00")

    x, y = OFFSET_X+30, 30

    cv2.putText(
        canvas,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (TEXT_COLOR, TEXT_COLOR, TEXT_COLOR),
        1,
        cv2.LINE_AA
    )


def draw_price_meta(
        trapped_meta: np.ndarray, frame: int, canvas:  np.ndarray
    ) -> None:
    """Draw price meta."""
    vectored_price = trapped_meta[frame]["price_change"]

    points = []
    for i, price in enumerate(vectored_price):
        y_center = GRAPH_Y//2
        step_for_price_bin = GRAPH_Y // cfg.PRICE_BINS

        if cfg.TIME_BINS.size > 1:
            step_for_x = GRAPH_X // (cfg.TIME_BINS.size - 1)
        else:
            step_for_x = GRAPH_X

        x_offset = OFFSET_X + (step_for_x*i)
        scaled = price*cfg.PRICE_STEP
        y_offset = np.int32(min(GRAPH_Y, (y_center - scaled * step_for_price_bin)))
        points.append((x_offset, y_offset))

    if len(points) == 1:
        cv2.line(
            canvas,
            (points[0][0], points[0][1]),
            (points[0][0]+step_for_x, points[0][1]),
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
        cv2.line(
            canvas,
            (points[0][0], points[0][1]),
            (points[0][0]+step_for_x, points[0][1]),
            (255, 0, 255),
            2,
            cv2.LINE_AA,
        )
        return

    for i in range(len(points)):
        if i == 0:
            continue
        cv2.line(
            canvas,
            points[i-1],
            points[i],
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
        cv2.line(
            canvas,
            points[i-1],
            points[i],
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

def draw_line(canvas: np.ndarray) -> None:
    """Draw middle line."""
    point_one = (OFFSET_X, GRAPH_Y//2)
    point_two = (FULL_X, GRAPH_Y//2)
    cv2.line(
            canvas,
            point_one,
            point_two,
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
    cv2.line(
        canvas,
        point_one,
        point_two,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.line(
            canvas,
            (OFFSET_X, 0),
            (OFFSET_X, GRAPH_Y),
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
    cv2.line(
        canvas,
        (OFFSET_X, 0),
        (OFFSET_X, GRAPH_Y),
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.line(
        canvas,
        (OFFSET_X, GRAPH_Y),
        (FULL_X, GRAPH_Y),
        (0, 0, 0),
        3,
        cv2.LINE_AA,
    )
    cv2.line(
        canvas,
        (OFFSET_X, GRAPH_Y),
        (FULL_X, GRAPH_Y),
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

def draw_text(canvas: np.ndarray) -> None:
    """Draw text."""
    cv2.rectangle(
        canvas,
        (OFFSET_X + 22, 10),
        (OFFSET_X + 475, 130),
        (35, 15, 30),
        -1
    )

    cv2.putText(
        canvas,
        "White line = realized price path",
        (OFFSET_X + 30, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (TEXT_COLOR, TEXT_COLOR, TEXT_COLOR),
        1,
        cv2.LINE_AA
    )

    cv2.putText(
        canvas,
        "Heatmap = model-weighted forward path distribution",
        (OFFSET_X + 30, 90),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (TEXT_COLOR, TEXT_COLOR, TEXT_COLOR),
        1,
        cv2.LINE_AA
    )

    cv2.putText(
        canvas,
        "Brighter regions = higher relative weight concentration",
        (OFFSET_X + 30, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (TEXT_COLOR, TEXT_COLOR, TEXT_COLOR),
        1,
        cv2.LINE_AA
    )

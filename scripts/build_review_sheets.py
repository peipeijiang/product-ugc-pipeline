#!/usr/bin/env python3
"""Build human-reviewable contact sheets for keyframe and sampled-video QC.

QC stages require a real visual check, but the vision-model path writes only
JSON verdicts. When review is done by a human, or by an agent whose transport
cannot inline large images, that check needs durable artifacts on disk:

  - one contact sheet per video, evenly sampled and labelled with timestamps
  - one contact sheet per generated storyboard or keyframe
  - an index.html that shows every sheet full width for scrolling review

This script only samples and lays out existing files. It never calls a paid
provider and never writes a QC verdict; qc/<stage>.json stays the sole record
of pass/fail and must still be filled in from an actual review.
"""
from __future__ import annotations

import argparse
import html
import shutil
import subprocess
from pathlib import Path

from common import selected_product_dirs


def which(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise SystemExit(f"{tool} is required for review sheets; install ffmpeg")
    return path


def duration_seconds(video: Path) -> float:
    out = subprocess.run(
        [which("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0

def sample_timestamps(total: float, count: int) -> list[float]:
    """Evenly spaced interior samples; skips the first/last frame fades."""
    if total <= 0:
        return []
    start = total * 0.03
    span = total * 0.94
    if count <= 1:
        return [round(total / 2, 2)]
    step = span / (count - 1)
    return [round(start + step * index, 2) for index in range(count)]


def extract_frames(video: Path, stamps: list[float], work: Path, width: int) -> list[Path]:
    frames: list[Path] = []
    for index, stamp in enumerate(stamps):
        frame = work / f"{video.stem}-{index:02d}.jpg"
        subprocess.run(
            [which("ffmpeg"), "-nostdin", "-v", "error", "-ss", str(stamp),
             "-i", str(video), "-frames:v", "1", "-vf", f"scale={width}:-1",
             "-q:v", "4", str(frame), "-y"],
            check=False,
        )
        if frame.is_file():
            frames.append(frame)
    return frames


def stack_frames(frames: list[Path], destination: Path, columns: int) -> bool:
    """Lay frames out in a grid. ffmpeg xstack needs an explicit layout."""
    if not frames:
        return False
    if len(frames) == 1:
        subprocess.run(
            [which("ffmpeg"), "-nostdin", "-v", "error", "-i", str(frames[0]),
             "-q:v", "4", str(destination), "-y"],
            check=False,
        )
        return destination.is_file()
    layout: list[str] = []
    for index in range(len(frames)):
        column = index % columns
        row = index // columns
        x = "0" if column == 0 else "+".join(f"w{item}" for item in range(column))
        y = "0" if row == 0 else "+".join(f"h{item * columns}" for item in range(row))
        layout.append(f"{x}_{y}")
    inputs: list[str] = []
    for frame in frames:
        inputs.extend(["-i", str(frame)])
    streams = "".join(f"[{index}]" for index in range(len(frames)))
    subprocess.run(
        [which("ffmpeg"), "-nostdin", "-v", "error", *inputs, "-filter_complex",
         f"{streams}xstack=inputs={len(frames)}:layout={'|'.join(layout)}:fill=black",
         "-q:v", "4", str(destination), "-y"],
        check=False,
    )
    return destination.is_file()

def label_text(stamps: list[float]) -> str:
    return "  ".join(f"{index + 1}:{stamp}s" for index, stamp in enumerate(stamps))


def build_video_sheets(folder: Path, sheet_dir: Path, work: Path,
                       samples: int, width: int, columns: int) -> list[dict]:
    entries: list[dict] = []
    for video in sorted((folder / "videos").glob("variant-*.mp4")):
        total = duration_seconds(video)
        stamps = sample_timestamps(total, samples)
        frames = extract_frames(video, stamps, work, width)
        sheet = sheet_dir / f"{video.stem}-sheet.jpg"
        if stack_frames(frames, sheet, columns):
            entries.append({
                "label": f"{video.stem}  ({total:.2f}s)",
                "sheet": sheet.name,
                "samples": label_text(stamps),
            })
            print(f"[sheet] {sheet.relative_to(folder)}", flush=True)
    return entries


def build_image_sheets(folder: Path, sheet_dir: Path, patterns: list[str], width: int) -> list[dict]:
    """Downscale existing generated stills so they are cheap to review."""
    entries: list[dict] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for source in sorted(folder.glob(pattern)):
            if source in seen:
                continue
            seen.add(source)
            sheet = sheet_dir / f"{source.stem}-review.jpg"
            subprocess.run(
                [which("ffmpeg"), "-nostdin", "-v", "error", "-i", str(source),
                 "-vf", f"scale={width}:-1", "-q:v", "4", str(sheet), "-y"],
                check=False,
            )
            if sheet.is_file():
                entries.append({
                    "label": str(source.relative_to(folder)),
                    "sheet": sheet.name,
                    "samples": "single generated image",
                })
                print(f"[sheet] {sheet.relative_to(folder)}", flush=True)
    return entries

def write_index(sheet_dir: Path, entries: list[dict], stage: str, product: str) -> Path:
    index = sheet_dir / "index.html"
    blocks = []
    for entry in entries:
        caption = html.escape(entry["label"])
        samples = html.escape(entry.get("samples", ""))
        name = html.escape(entry["sheet"])
        blocks.append(
            f'<section><h2>{caption}</h2><p class="s">{samples}</p>'
            f'<img src="{name}" alt="{caption}"></section>'
        )
    index.write_text(
        "<!doctype html><meta charset=utf-8>"
        f"<title>{html.escape(product)} {html.escape(stage)} review</title>"
        "<style>body{background:#111;color:#eee;font:14px system-ui;margin:0;padding:24px}"
        "h1{font-size:18px}h2{font-size:15px;margin:28px 0 4px}.s{color:#8a8;margin:0 0 8px}"
        "img{width:100%;height:auto;display:block;border:1px solid #333}</style>"
        f"<h1>{html.escape(product)} · {html.escape(stage)} sampled review</h1>"
        "<p class=s>Check every panel against the real source photos. This page is "
        "review input only; record the verdict in qc/&lt;stage&gt;.json.</p>"
        + "".join(blocks),
        encoding="utf-8",
    )
    return index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--products", default="")
    parser.add_argument("--stage", choices=["keyframes", "videos"], default="videos")
    parser.add_argument("--samples", type=int, default=6, help="Frames sampled per video")
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--frame-width", type=int, default=360)
    parser.add_argument(
        "--image-glob", action="append", default=[],
        help="Extra globs for keyframe stage, relative to the product folder",
    )
    args = parser.parse_args()
    for folder in selected_product_dirs(args.output_dir, args.products):
        sheet_dir = folder / "qc" / f"{args.stage}_review"
        sheet_dir.mkdir(parents=True, exist_ok=True)
        work = sheet_dir / "frames"
        work.mkdir(exist_ok=True)
        if args.stage == "videos":
            entries = build_video_sheets(folder, sheet_dir, work, args.samples,
                                        args.frame_width, args.columns)
        else:
            patterns = args.image_glob or [
                "generated_images/variant-*.png",
                "runs/*/storyboards/variant-*-storyboard.png",
            ]
            entries = build_image_sheets(folder, sheet_dir, patterns, args.frame_width * args.columns)
        if not entries:
            print(f"[skip] {folder.name}: nothing to review for stage {args.stage}", flush=True)
            continue
        index = write_index(sheet_dir, entries, args.stage, folder.name)
        print(f"[index] {index}", flush=True)


if __name__ == "__main__":
    main()


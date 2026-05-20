#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Sequence

from common import slugify


def script_path(name: str) -> Path:
    return Path(__file__).with_name(name)


def run_command(command: Sequence[str]) -> None:
    print("[run]", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def default_prompt_file(label: str) -> str:
    return f"ugc_prompts_{slugify(label, fallback='fresh-batch')}.json"


def default_video_subdir(label: str) -> str:
    return f"videos_{slugify(label, fallback='fresh-batch')}"


def ensure_new_targets(output_dir: Path, products: str, prompt_file: str, video_subdir: str, force: bool) -> None:
    if force:
        return
    selectors = [item.strip() for item in products.split(",") if item.strip()]
    candidates = []
    for folder in sorted(output_dir.iterdir()):
        if not folder.is_dir() or not folder.name[:2].isdigit():
            continue
        if selectors:
            folder_index = folder.name.split("-", 1)[0]
            folder_name = folder.name.lower()
            if not any(folder_name.startswith(sel.lower()) or folder_index == sel.zfill(2) for sel in selectors):
                continue
        candidates.append(folder)
    collisions: list[str] = []
    for folder in candidates:
        if (folder / prompt_file).exists():
            collisions.append(str(folder / prompt_file))
        if (folder / video_subdir).exists():
            collisions.append(str(folder / video_subdir))
    if collisions:
        joined = "\n".join(collisions[:20])
        raise SystemExit(
            "Fresh-batch target already exists. Choose a new --batch-label or rerun with --force.\n"
            f"{joined}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a fresh history-aware prompt batch, keyframes, and videos.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--products", default="", help="Comma-separated product selectors, e.g. 01,02 or 01-flower")
    parser.add_argument("--count", type=int, default=2, help="New variants to generate per product.")
    parser.add_argument("--batch-label", default=f"fresh-{datetime.now().strftime('%Y%m%d-%H%M')}")
    parser.add_argument("--history-glob", default="ugc_prompts*.json")
    parser.add_argument("--prompt-output-file", default="")
    parser.add_argument("--prompt-model", default="gpt-5.2")
    parser.add_argument("--prompt-base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument("--image-model", default="gpt-image-2-vip")
    parser.add_argument("--image-size", default="1024x1536")
    parser.add_argument("--image-base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument("--video-provider", choices=["lk888", "laozhang"], default="lk888")
    parser.add_argument("--video-model", default="")
    parser.add_argument("--video-base-url", default="")
    parser.add_argument("--video-output-subdir", default="")
    parser.add_argument("--audio-style", choices=["none", "safe", "mid", "legacy", "asmr"], default="safe")
    parser.add_argument("--light-overlay", action="store_true")
    parser.add_argument("--single-reference", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    prompt_output_file = args.prompt_output_file or default_prompt_file(args.batch_label)
    video_output_subdir = args.video_output_subdir or default_video_subdir(args.batch_label)
    ensure_new_targets(args.output_dir, args.products, prompt_output_file, video_output_subdir, args.force)

    run_command(
        [
            "python3",
            str(script_path("generate_ugc_prompts.py")),
            str(args.output_dir),
            "--count",
            str(args.count),
            "--output-file",
            prompt_output_file,
            "--batch-label",
            args.batch_label,
            "--history-glob",
            args.history_glob,
            "--model",
            args.prompt_model,
            "--base-url",
            args.prompt_base_url,
            "--products",
            args.products,
        ]
    )

    run_command(
        [
            "python3",
            str(script_path("generate_images.py")),
            str(args.output_dir),
            "--variants",
            f"1-{args.count}",
            "--prompts-file",
            prompt_output_file,
            "--model",
            args.image_model,
            "--size",
            args.image_size,
            "--base-url",
            args.image_base_url,
            "--products",
            args.products,
            "--keyframes",
        ]
        + (["--force"] if args.force else [])
    )

    if args.video_provider == "laozhang":
        video_model = args.video_model or "veo-3.1-fast-fl"
        video_base_url = args.video_base_url or "https://api.laozhang.ai/v1"
        run_command(
            [
                "python3",
                str(script_path("generate_videos.py")),
                str(args.output_dir),
                "--variants",
                f"1-{args.count}",
                "--model",
                video_model,
                "--base-url",
                video_base_url,
                "--products",
                args.products,
            ]
            + (["--force"] if args.force else [])
        )
        return

    video_model = args.video_model or "veo3.1"
    video_base_url = args.video_base_url or "https://api.lk888.ai/api"
    command = [
        "python3",
        str(script_path("generate_videos_lk888.py")),
        str(args.output_dir),
        "--variants",
        f"1-{args.count}",
        "--prompts-file",
        prompt_output_file,
        "--model",
        video_model,
        "--base-url",
        video_base_url,
        "--products",
        args.products,
        "--output-subdir",
        video_output_subdir,
        "--audio-style",
        args.audio_style,
    ]
    if args.light_overlay:
        command.append("--light-overlay")
    if args.single_reference:
        command.append("--single-reference")
    if args.continue_on_error:
        command.append("--continue-on-error")
    if args.force:
        command.append("--force")
    run_command(command)


if __name__ == "__main__":
    main()

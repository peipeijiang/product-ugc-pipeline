#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Sequence

from common import load_json, selected_product_dirs, slugify, write_json


def script_path(name: str) -> Path:
    return Path(__file__).with_name(name)


def run_command(command: Sequence[str]) -> None:
    print("[run]", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def product_batch_dir(product_dir: Path, label: str) -> Path:
    return product_dir / "runs" / slugify(label, fallback="fresh-batch")


def copy_if_exists(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_tree_if_exists(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def write_run_manifests(output_dir: Path, products: str, label: str, count: int, provider: str, model: str) -> None:
    for product_dir in selected_product_dirs(output_dir, products):
        run_dir = product_batch_dir(product_dir, label)
        run_dir.mkdir(parents=True, exist_ok=True)
        copy_if_exists(product_dir / "ugc_prompts.json", run_dir / "prompt_batch.json")
        copy_if_exists(product_dir / "generated_images" / "image_generation_results.json", run_dir / "image_generation_results.json")
        copy_if_exists(product_dir / "videos" / "video_generation_results.json", run_dir / "video_generation_results.json")
        copy_tree_if_exists(product_dir / "generated_images", run_dir / "keyframes")
        copy_tree_if_exists(product_dir / "videos", run_dir / "videos")
        write_json(
            run_dir / "run_manifest.json",
            {
                "batch_label": label,
                "product_folder": product_dir.name,
                "requested_new_variants": count,
                "video_provider": provider,
                "video_model": model,
                "canonical_prompt_file": "ugc_prompts.json",
                "canonical_generated_images_dir": "generated_images",
                "canonical_videos_dir": "videos",
                "note": "This run folder is a snapshot for review/history. Canonical outputs remain at product root.",
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a fresh history-aware prompt batch, keyframes, and videos.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--products", default="", help="Comma-separated product selectors, e.g. 01,02 or 01-flower")
    parser.add_argument("--count", type=int, default=2, help="New variants to generate per product.")
    parser.add_argument("--batch-label", default=f"fresh-{datetime.now().strftime('%Y%m%d-%H%M')}")
    parser.add_argument("--history-glob", default="ugc_prompts*.json")
    parser.add_argument("--prompt-model", default="gpt-5.2")
    parser.add_argument("--prompt-base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument("--image-model", default="gpt-image-2-vip")
    parser.add_argument("--image-size", default="1024x1536")
    parser.add_argument("--image-base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument("--video-provider", choices=["lk888", "laozhang"], default="lk888")
    parser.add_argument("--video-model", default="")
    parser.add_argument("--video-base-url", default="")
    parser.add_argument("--audio-style", choices=["none", "safe", "mid", "legacy", "asmr"], default="safe")
    parser.add_argument("--light-overlay", action="store_true")
    parser.add_argument("--single-reference", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    run_command(
        [
            "python3",
            str(script_path("generate_ugc_prompts.py")),
            str(args.output_dir),
            "--count",
            str(args.count),
            "--output-file",
            "ugc_prompts.json",
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

    prompts_snapshot_variants: dict[str, list[int]] = {}
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        prompts = load_json(product_dir / "ugc_prompts.json", {})
        variants = [int(variant.get("variant_id", 0)) for variant in prompts.get("variants", []) if isinstance(variant, dict)]
        prompts_snapshot_variants[product_dir.name] = variants[-args.count :] if args.count > 0 else variants

    for product_dir in selected_product_dirs(args.output_dir, args.products):
        variants = prompts_snapshot_variants.get(product_dir.name, [])
        if not variants:
            continue
        selector = ",".join(str(item) for item in variants)
        run_command(
            [
                "python3",
                str(script_path("generate_images.py")),
                str(args.output_dir),
                "--variants",
                selector,
                "--prompts-file",
                "ugc_prompts.json",
                "--model",
                args.image_model,
                "--size",
                args.image_size,
                "--base-url",
                args.image_base_url,
                "--products",
                product_dir.name.split("-", 1)[0],
                "--keyframes",
            ]
            + (["--force"] if args.force else [])
        )

    if args.video_provider == "laozhang":
        video_model = args.video_model or "veo-3.1-fast-fl"
        video_base_url = args.video_base_url or "https://api.laozhang.ai/v1"
        for product_dir in selected_product_dirs(args.output_dir, args.products):
            variants = prompts_snapshot_variants.get(product_dir.name, [])
            if not variants:
                continue
            run_command(
                [
                    "python3",
                    str(script_path("generate_videos.py")),
                    str(args.output_dir),
                    "--variants",
                    ",".join(str(item) for item in variants),
                    "--model",
                    video_model,
                    "--base-url",
                    video_base_url,
                    "--products",
                    product_dir.name.split("-", 1)[0],
                ]
                + (["--force"] if args.force else [])
            )
        write_run_manifests(args.output_dir, args.products, args.batch_label, args.count, args.video_provider, video_model)
        return

    video_model = args.video_model or "veo3.1"
    video_base_url = args.video_base_url or "https://api.lk888.ai/api"
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        variants = prompts_snapshot_variants.get(product_dir.name, [])
        if not variants:
            continue
        command = [
            "python3",
            str(script_path("generate_videos_lk888.py")),
            str(args.output_dir),
            "--variants",
            ",".join(str(item) for item in variants),
            "--prompts-file",
            "ugc_prompts.json",
            "--model",
            video_model,
            "--base-url",
            video_base_url,
            "--products",
            product_dir.name.split("-", 1)[0],
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
    write_run_manifests(args.output_dir, args.products, args.batch_label, args.count, args.video_provider, video_model)


if __name__ == "__main__":
    main()

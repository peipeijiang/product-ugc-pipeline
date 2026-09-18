#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
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


def write_run_manifests(
    output_dir: Path,
    products: str,
    label: str,
    count: int,
    model: str,
    voice_locale: str = "",
    market: str = "",
) -> None:
    for product_dir in selected_product_dirs(output_dir, products):
        run_dir = product_batch_dir(product_dir, label)
        run_dir.mkdir(parents=True, exist_ok=True)
        copy_if_exists(product_dir / "ugc_prompts.json", run_dir / "prompt_batch.json")
        copy_if_exists(product_dir / "generated_images" / "image_generation_results.json", run_dir / "image_generation_results.json")
        copy_if_exists(product_dir / "videos" / "video_generation_results.json", run_dir / "video_generation_results.json")
        copy_tree_if_exists(product_dir / "generated_images", run_dir / "storyboards")
        copy_tree_if_exists(product_dir / "videos", run_dir / "videos")
        write_json(
            run_dir / "run_manifest.json",
            {
                "batch_label": label,
                "product_folder": product_dir.name,
                "requested_new_variants": count,
                "video_provider": "lk888",
                "reference_mode": "omni-reference",
                "video_model": model,
                "voice_locale": voice_locale,
                "market": market,
                "canonical_prompt_file": "ugc_prompts.json",
                "canonical_generated_images_dir": "generated_images",
                "canonical_videos_dir": "videos",
                "note": "This run folder is a snapshot for review/history. Canonical outputs remain at product root.",
            },
        )


def assert_ready_for_fresh_batch(output_dir: Path, products: str) -> None:
    for product_dir in selected_product_dirs(output_dir, products):
        missing = [
            filename
            for filename in ("product_manifest.json", "image_analysis.json", "product_brief.json")
            if not (product_dir / filename).exists()
        ]
        if missing:
            raise RuntimeError(
                f"{product_dir.name}: missing {missing}. Refusing to run fresh batch before scrape, vision analysis, and product brief are complete."
            )
        image_analysis = load_json(product_dir / "image_analysis.json", {})
        failed = [
            item.get("local_path", "unknown")
            for item in image_analysis.get("images", [])
            if (item.get("analysis") or {}).get("error")
        ]
        if failed:
            raise RuntimeError(
                f"{product_dir.name}: image_analysis.json contains failed visual model outputs for {failed}. "
                "Rerun analyze_materials with a working vision model before generating prompts/images/videos."
            )
        product_brief = load_json(product_dir / "product_brief.json", {})
        required = ["confirmed_identity", "confirmed_use_cases", "step_by_step_usage", "misuse_risks_to_avoid"]
        missing_brief = [key for key in required if not product_brief.get(key)]
        if missing_brief:
            raise RuntimeError(
                f"{product_dir.name}: product_brief.json missing required cognition fields {missing_brief}. "
                "Refusing to generate videos until product use is understood."
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a fresh history-aware prompt batch, Omni reference storyboards, and videos.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--products", default="", help="Comma-separated product selectors, e.g. 01,02 or 01-flower")
    parser.add_argument("--count", type=int, default=2, help="New variants to generate per product.")
    parser.add_argument("--batch-label", default=f"fresh-{datetime.now().strftime('%Y%m%d-%H%M')}")
    parser.add_argument("--history-glob", default="ugc_prompts*.json")
    parser.add_argument("--prompt-model", default=os.getenv("PRODUCT_UGC_PROMPT_MODEL", "gpt-5.2"))
    parser.add_argument("--prompt-base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument("--image-model", default="gpt-image-2-vip")
    parser.add_argument("--image-size", default="1080x1920", help="Omni storyboard canvas passed to generate_images.py. Defaults to 1080x1920 (9:16).")
    parser.add_argument("--image-base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument("--video-model", default="omni-flash", choices=["omni-flash", "omni_flash-10s"])
    parser.add_argument("--video-base-url", default="https://api.lk888.ai")
    parser.add_argument("--audio-style", choices=["none", "safe", "mid", "legacy", "asmr"], default="safe")
    parser.add_argument("--light-overlay", action="store_true")
    parser.add_argument(
        "--market",
        default="",
        help="Target market for the spoken language and local creative framing, e.g. Japan. Resolved from the product brief when omitted.",
    )
    parser.add_argument(
        "--voice-locale",
        default=os.getenv("PRODUCT_UGC_VOICE_LOCALE", ""),
        help="Explicit spoken locale, e.g. ja-JP. Never silently defaults to English; an unresolved locale fails before any paid step.",
    )
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    assert_ready_for_fresh_batch(args.output_dir, args.products)
    target_video_model = args.video_model

    # Resolve the batch language up front so an undeclared market fails before
    # prompt generation, image generation or any paid video submission.
    market_flags: list[str] = []
    if args.voice_locale:
        market_flags += ["--voice-locale", args.voice_locale]
    if args.market:
        market_flags += ["--market", args.market]
    from voice_locale import VoiceLocaleError, resolve_voice_locale

    resolved_locales: dict[str, str] = {}
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        prompt_file = product_dir / "ugc_prompts.json"
        try:
            resolution = resolve_voice_locale(
                prompts=load_json(prompt_file, {}) if prompt_file.exists() else {},
                brief=load_json(product_dir / "product_brief.json", {}),
                manifest=load_json(product_dir / "product_manifest.json", {}),
                explicit=args.voice_locale or args.market,
                product_dir=product_dir,
            )
        except VoiceLocaleError as error:
            raise RuntimeError(f"{product_dir.name}: {error}") from error
        resolved_locales[product_dir.name] = resolution.locale
        print(f"[market] {product_dir.name} locale={resolution.locale} source={resolution.source}", flush=True)

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
            "--target-video-model",
            target_video_model,
            "--base-url",
            args.prompt_base_url,
            "--products",
            args.products,
        ]
        + market_flags
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
                "--storyboards",
            ]
            + (["--force"] if args.force else [])
        )

        run_command(
            [
                "python3",
                str(script_path("qc_dual_consistency.py")),
                str(args.output_dir),
                "--stage",
                "storyboards",
                "--variants",
                selector,
                "--prompts-file",
                "ugc_prompts.json",
                "--products",
                product_dir.name.split("-", 1)[0],
            ]
        )

    video_model = args.video_model
    video_base_url = args.video_base_url
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
            "--duration",
            "10",
            "--status-endpoint",
            "/v1/media/status",
            "--reference-mode",
            "omni-reference",
        ]
        # Pin the resolved locale so the adapter cannot re-derive a different
        # language than the prompt batch was written in.
        resolved_locale = resolved_locales.get(product_dir.name)
        if resolved_locale:
            command.extend(["--voice-locale", resolved_locale])
        if args.light_overlay:
            command.append("--light-overlay")
        if args.continue_on_error:
            command.append("--continue-on-error")
        if args.force:
            command.append("--force")
        run_command(command)
    write_run_manifests(
        args.output_dir,
        args.products,
        args.batch_label,
        args.count,
        video_model,
        voice_locale=",".join(sorted(set(resolved_locales.values()))),
        market=args.market,
    )


if __name__ == "__main__":
    main()

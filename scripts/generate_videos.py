#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

from common import (
    DEFAULT_BASE_URL,
    download_binary,
    http_request,
    load_json,
    multipart_request,
    request_json,
    require_api_key,
    selected_product_dirs,
    write_json,
)
from generate_images import parse_variants


CONTINUE_STATUSES = {"queued", "processing", "in_progress", "submitted", "running"}
COMPLETE_STATUSES = {"completed", "succeeded", "success"}
FAIL_STATUSES = {"failed", "cancelled", "canceled", "expired", "error"}
TRANSIENT_ERROR_MARKERS = (
    "UNEXPECTED_EOF",
    "urlopen error",
    "timed out",
    "Connection reset",
    "IncompleteRead",
    "Max retries exceeded",
    "NameResolutionError",
    "Failed to resolve",
    "nodename nor servname",
)


def generated_image_path(product_dir: Path, variant_id: int) -> Path | None:
    candidate = product_dir / "generated_images" / f"variant-{variant_id:02d}.png"
    if candidate.exists():
        return candidate
    return None


def generated_keyframe_paths(product_dir: Path, variant_id: int) -> list[Path]:
    start = product_dir / "generated_images" / f"variant-{variant_id:02d}-start.png"
    end = product_dir / "generated_images" / f"variant-{variant_id:02d}-end.png"
    if start.exists() and end.exists():
        return [start, end]
    return []


def existing_video_dir(product_dir: Path) -> Path:
    candidates = [product_dir / "videos"]
    for path in sorted(product_dir.glob("videos*")):
        if path.is_dir() and path.name.startswith("videos"):
            candidates.append(path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return product_dir / "videos"


def existing_variant_max(video_dir: Path) -> int:
    max_variant = 0
    for path in video_dir.glob("variant-*.mp4"):
        stem = path.stem
        try:
            variant_id = int(stem.split("-", 1)[1])
        except Exception:
            continue
        max_variant = max(max_variant, variant_id)
    return max_variant


def fallback_reference_path(product_dir: Path, variant: dict[str, Any]) -> Path | None:
    for local_path in variant.get("selected_reference_images") or []:
        candidate = product_dir / local_path
        if candidate.exists():
            return candidate
    return None


def create_video_task(
    api_key: str,
    prompt: str,
    model: str,
    reference_images: list[Path],
    base_url: str,
) -> dict[str, Any]:
    if reference_images:
        return multipart_request(
            "/videos",
            api_key,
            fields={"model": model, "prompt": prompt},
            files=[("input_reference", reference_image) for reference_image in reference_images[:2]],
            base_url=base_url,
            timeout=180,
        )
    return request_json("/videos", api_key, {"model": model, "prompt": prompt}, base_url=base_url, timeout=180)


def create_video_task_with_retry(
    api_key: str,
    prompt: str,
    model: str,
    reference_images: list[Path],
    base_url: str,
    attempts: int,
    delay_seconds: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return create_video_task(api_key, prompt, model, reference_images, base_url)
        except RuntimeError as error:
            last_error = error
            transient = any(marker in str(error) for marker in TRANSIENT_ERROR_MARKERS)
            if not transient or attempt == attempts:
                raise
            print(f"[create] transient error attempt {attempt}/{attempts}: {error}", flush=True)
            time.sleep(delay_seconds)
    raise last_error or RuntimeError("video task creation failed")


def poll_video(api_key: str, video_id: str, base_url: str, poll_seconds: int, timeout_seconds: int) -> dict[str, Any]:
    started_at = time.time()
    latest: dict[str, Any] = {}
    transient_errors = 0
    while time.time() - started_at < timeout_seconds:
        try:
            latest = request_json(f"/videos/{video_id}", api_key, payload=None, method="GET", base_url=base_url, timeout=60)
            transient_errors = 0
        except RuntimeError as error:
            transient_errors += 1
            if transient_errors > 6:
                raise
            print(f"[poll] {video_id} transient error {transient_errors}/6: {error}", flush=True)
            time.sleep(poll_seconds)
            continue
        status = str(latest.get("status", "")).lower()
        print(f"[poll] {video_id} status={status} progress={latest.get('progress', 'n/a')}", flush=True)
        if status in COMPLETE_STATUSES:
            return latest
        if status in FAIL_STATUSES:
            raise RuntimeError(f"Video task failed: {json.dumps(latest, ensure_ascii=False)}")
        if status not in CONTINUE_STATUSES:
            print(f"[warn] unknown status, continuing: {status}")
        time.sleep(poll_seconds)
    raise TimeoutError(f"Timed out waiting for {video_id}: {json.dumps(latest, ensure_ascii=False)}")


def download_video_content(api_key: str, video_id: str, destination: Path, base_url: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/videos/{video_id}/content"
    status_code, headers, body = http_request(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=180)
    content_type = headers.get("Content-Type", "")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if "application/json" not in content_type:
        destination.write_bytes(body)
        return {"status_code": status_code, "content_type": content_type, "output_path": str(destination)}
    payload = json.loads(body.decode("utf-8"))
    video_url = payload.get("url")
    if video_url:
        absolute_url = urllib.parse.urljoin(DEFAULT_BASE_URL, video_url)
        if video_url.startswith("http"):
            absolute_url = video_url
        downloaded = download_binary(absolute_url, destination, timeout=240)
        payload["downloaded"] = downloaded
        payload["output_path"] = str(destination) if downloaded else None
    return payload


def download_video_content_with_retry(
    api_key: str,
    video_id: str,
    destination: Path,
    base_url: str,
    poll_seconds: int,
    attempts: int = 12,
) -> dict[str, Any]:
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            return download_video_content(api_key, video_id, destination, base_url)
        except RuntimeError as error:
            last_error = str(error)
            transient = any(marker in last_error for marker in TRANSIENT_ERROR_MARKERS)
            if "not completed" not in last_error and "IN_PROGRESS" not in last_error and not transient:
                raise
            print(f"[content] {video_id} not ready yet, retry {attempt}/{attempts}: {last_error}", flush=True)
            time.sleep(poll_seconds)
    raise RuntimeError(last_error or f"video content not ready after {attempts} attempts")


def process_variant(
    product_dir: Path,
    variant: dict[str, Any],
    api_key: str,
    args: argparse.Namespace,
    video_dir: Path,
) -> dict[str, Any]:
    variant_id = int(variant.get("variant_id", 0))
    reference_images = generated_keyframe_paths(product_dir, variant_id)
    if not reference_images:
        reference_image = generated_image_path(product_dir, variant_id) or fallback_reference_path(product_dir, variant)
        reference_images = [reference_image] if reference_image else []
    prompt = variant.get("video_prompt") or variant.get("image_prompt") or f"Create a UGC product video for {product_dir.name}."
    output_path = video_dir / f"variant-{variant_id:02d}.mp4"
    if output_path.exists() and not args.force:
        return {
            "variant_id": variant_id,
            "status": "skipped_existing",
            "model": args.model,
            "reference_images": [str(reference_image.relative_to(product_dir)) for reference_image in reference_images],
            "output_path": str(output_path.relative_to(product_dir)),
            "prompt": prompt,
        }
    print(f"[video] {product_dir.name} variant {variant_id:02d}", flush=True)
    create_response = create_video_task_with_retry(
        api_key,
        prompt,
        args.model,
        reference_images,
        args.base_url,
        args.create_retries,
        args.poll_seconds,
    )
    video_id = create_response.get("id")
    if not video_id:
        raise RuntimeError(f"Video create response missing id: {json.dumps(create_response, ensure_ascii=False)}")
    try:
        status_response = poll_video(api_key, video_id, args.base_url, args.poll_seconds, args.timeout_seconds)
    except RuntimeError as error:
        if args.safe_no_audio_retry and "PUBLIC_ERROR_" in str(error):
            safe_prompt = (
                "Use the provided first frame as the complete visual source of truth. "
                "Keep every visible object's shape, color, proportions, texture, position, and silhouette unchanged for the entire video. "
                "Animate only a slow camera push-in, tiny handheld parallax, and subtle natural light shift. "
                "Do not introduce new hands, props, labels, text, tools, liquids, mechanisms, packaging, or product parts. "
                "Do not perform scrubbing, washing, squeezing, pressing, cutting, opening, twisting, pouring, bending, morphing, or any use action. "
                "No faces, no children, no spoken dialogue, no voiceover, no captions, no subtitles, no music lyrics, no on-screen text."
            )
            print(f"[video] {product_dir.name} variant {variant_id:02d} retrying silent visual-only prompt", flush=True)
            create_response = create_video_task_with_retry(
                api_key,
                safe_prompt,
                args.model,
                reference_images,
                args.base_url,
                args.create_retries,
                args.poll_seconds,
            )
            video_id = create_response.get("id")
            prompt = safe_prompt
            if not video_id:
                raise RuntimeError(f"Video retry response missing id: {json.dumps(create_response, ensure_ascii=False)}")
            status_response = poll_video(api_key, video_id, args.base_url, args.poll_seconds, args.timeout_seconds)
        else:
            raise
    if status_response.get("video_url"):
        downloaded = False
        for attempt in range(1, args.download_retries + 1):
            downloaded = download_binary(status_response["video_url"], output_path, timeout=240)
            if downloaded:
                break
            print(f"[download] retry {attempt}/{args.download_retries}: {status_response['video_url']}", flush=True)
            time.sleep(args.poll_seconds)
        content_response = {
            "downloaded_from_status_video_url": downloaded,
            "url": status_response["video_url"],
            "output_path": str(output_path) if downloaded else None,
        }
    else:
        content_response = download_video_content_with_retry(
            api_key,
            video_id,
            output_path,
            args.base_url,
            args.poll_seconds,
        )
    return {
        "variant_id": variant_id,
        "video_id": video_id,
        "model": args.model,
        "reference_images": [str(reference_image.relative_to(product_dir)) for reference_image in reference_images],
        "prompt": prompt,
        "create_response": create_response,
        "status_response": status_response,
        "content_response": content_response,
    }


def process_product(product_dir: Path, api_key: str, selected_variants: set[int], args: argparse.Namespace) -> None:
    prompts = load_json(product_dir / "ugc_prompts.json")
    if not prompts:
        print(f"[skip] missing ugc_prompts.json: {product_dir}")
        return
    video_dir = existing_video_dir(product_dir)
    video_dir.mkdir(parents=True, exist_ok=True)
    results_path = video_dir / "video_generation_results.json"
    existing_results = load_json(results_path, {"results": []})
    results: list[dict[str, Any]] = list(existing_results.get("results", []))
    result_keys = {(int(item.get("variant_id", 0)), item.get("status", "")) for item in results if isinstance(item, dict)}
    start_variant_id = existing_variant_max(video_dir) + 1
    for variant in prompts.get("variants", []):
        variant_id = int(variant.get("variant_id", 0))
        if variant_id not in selected_variants:
            continue
        current_variant = dict(variant)
        current_variant["variant_id"] = start_variant_id + (variant_id - 1)
        result = process_variant(product_dir, current_variant, api_key, args, video_dir)
        if args.force:
            results = [item for item in results if int(item.get("variant_id", 0)) != current_variant["variant_id"]]
            results.append(result)
            result_keys = {(int(item.get("variant_id", 0)), item.get("status", "")) for item in results if isinstance(item, dict)}
        elif (current_variant["variant_id"], result.get("status", "")) not in result_keys:
            results = [item for item in results if int(item.get("variant_id", 0)) != current_variant["variant_id"]]
            results.append(result)
            result_keys.add((current_variant["variant_id"], result.get("status", "")))
        write_json(results_path, {"results": results})


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate VEO 3.1 async product videos from UGC prompt variants.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--variants", default="1-10")
    parser.add_argument("--model", default="veo-3.1-fast-fl")
    parser.add_argument("--base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument("--products", default="", help="Comma-separated product selectors, e.g. 01 or 01-flower")
    parser.add_argument("--poll-seconds", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--create-retries", type=int, default=4)
    parser.add_argument("--download-retries", type=int, default=6)
    parser.add_argument("--safe-no-audio-retry", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    selected_variants = parse_variants(args.variants)
    api_key = require_api_key()
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        process_product(product_dir, api_key, selected_variants, args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from common import download_binary, load_json, selected_product_dirs, write_json
from generate_images import parse_variants


BASE_URL = "https://api.lk888.ai/api"
CONTINUE_STATES = {"pending", "running", "queued", "processing", "submitted"}
SUCCESS_STATES = {"success", "completed", "succeeded"}
FAILED_STATES = {"failed", "error", "cancelled", "canceled", "expired"}


def require_lk888_api_key() -> str:
    api_key = os.environ.get("LK888_API_KEY", "").strip() or os.environ.get("API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Missing LK888_API_KEY. Export it before running this script.")
    return api_key


def generated_keyframe_paths(product_dir: Path, variant_id: int) -> list[Path]:
    start = product_dir / "generated_images" / f"variant-{variant_id:02d}-start.png"
    end = product_dir / "generated_images" / f"variant-{variant_id:02d}-end.png"
    if start.exists() and end.exists():
        return [start, end]
    single = product_dir / "generated_images" / f"variant-{variant_id:02d}.png"
    if single.exists():
        return [single]
    return []


def upload_litterbox(path: Path, lifetime: str = "1h") -> str:
    command = [
        "curl",
        "--http1.1",
        "-fsS",
        "-F",
        "reqtype=fileupload",
        "-F",
        f"time={lifetime}",
        "-F",
        f"fileToUpload=@{path}",
        "https://litterbox.catbox.moe/resources/internals/api.php",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
    url = result.stdout.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"Unexpected upload response for {path}: {url[:300]}")
    return url


def upload_references(product_dir: Path, reference_images: list[Path], lifetime: str) -> list[dict[str, str]]:
    cache_path = product_dir / "videos_lk888" / "uploaded_reference_urls.json"
    cache = load_json(cache_path, {"uploads": {}})
    uploads: dict[str, Any] = dict(cache.get("uploads", {}))
    changed = False
    results: list[dict[str, str]] = []
    now = int(time.time())
    for image_path in reference_images:
        relative = str(image_path.relative_to(product_dir))
        cached = uploads.get(relative) or {}
        url = cached.get("url")
        expires_at = int(cached.get("expires_at", 0) or 0)
        if not url or expires_at - now < 900:
            print(f"[upload] {relative}", flush=True)
            url = upload_litterbox(image_path, lifetime=lifetime)
            expires_at = now + 50 * 60 if lifetime == "1h" else now + 10 * 60
            uploads[relative] = {"url": url, "uploaded_at": now, "expires_at": expires_at, "host": "litterbox.catbox.moe"}
            changed = True
        results.append({"path": relative, "url": url})
    if changed:
        write_json(cache_path, {"uploads": uploads})
    return results


def append_native_audio_instruction(prompt: str, voice_lines: Any) -> str:
    line = ""
    if isinstance(voice_lines, list) and voice_lines:
        first = voice_lines[0]
        if isinstance(first, dict):
            line = str(first.get("line") or first.get("text") or "").strip()
        else:
            line = str(first).strip()
    elif isinstance(voice_lines, str):
        line = voice_lines.strip()
    audio_block = (
        "\n\nNATIVE AUDIO: Generate natural native audio inside the video: a bright, young American female ecommerce creator voice, energetic but not robotic, with subtle upbeat social-ad background music. "
        "No subtitles, no captions, no readable on-screen text, no labels. "
    )
    if line:
        audio_block += f"Spoken voiceover, complete within 8 seconds: \"{line}\""
    else:
        audio_block += "Use a short natural product-demo voiceover that finishes within 8 seconds."
    return prompt + audio_block


def lk888_post(api_key: str, endpoint: str, payload: dict[str, Any], base_url: str) -> dict[str, Any]:
    response = requests.post(
        f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1000]}")
    data = response.json()
    if data.get("code") not in (None, 200):
        raise RuntimeError(f"API error: {json.dumps(data, ensure_ascii=False)}")
    return data


def lk888_get(api_key: str, endpoint: str, base_url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.get(
        f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}",
        headers={"Authorization": f"Bearer {api_key}"},
        params=params,
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1000]}")
    data = response.json()
    if data.get("code") not in (None, 200):
        raise RuntimeError(f"API error: {json.dumps(data, ensure_ascii=False)}")
    return data


def build_model_params(args: argparse.Namespace, image_urls: list[str]) -> dict[str, Any]:
    if args.model == "veo3.1-lite":
        return {
            "quality": args.quality,
            "aspect_ratio": args.aspect_ratio,
            "images": image_urls,
            "enhance_prompt": args.enhance_prompt,
        }
    params: dict[str, Any] = {
        "generation_mode": args.generation_mode,
        "aspect_ratio": args.aspect_ratio,
        "images": image_urls,
        "enhance_prompt": args.enhance_prompt,
    }
    if args.enable_upsample is not None:
        params["enable_upsample"] = args.enable_upsample
    return params


def extract_task_ids(create_response: dict[str, Any]) -> list[str]:
    data = create_response.get("data") if isinstance(create_response.get("data"), dict) else create_response
    raw_ids: list[Any] = []
    for key in ["task_id", "任务id", "任务ID"]:
        if data.get(key):
            raw_ids.append(data[key])
    for key in ["任务ids", "task_ids", "ids"]:
        value = data.get(key)
        if isinstance(value, list):
            raw_ids.extend(value)
    ids = [str(item) for item in raw_ids if item]
    return list(dict.fromkeys(ids))


def normalize_status(status_response: dict[str, Any]) -> dict[str, Any]:
    data = status_response.get("data") if isinstance(status_response.get("data"), dict) else status_response
    return data if isinstance(data, dict) else status_response


def poll_task(api_key: str, task_id: str, base_url: str, poll_seconds: int) -> dict[str, Any]:
    transient_errors = 0
    while True:
        try:
            raw = lk888_get(api_key, "/v1/skills/task-status", base_url, params={"task_id": task_id})
            transient_errors = 0
        except requests.RequestException as error:
            transient_errors += 1
            if transient_errors > 12:
                raise
            print(f"[poll] task={task_id} transient network error {transient_errors}/12: {error}", flush=True)
            time.sleep(poll_seconds)
            continue
        status = normalize_status(raw)
        state = str(status.get("state") or status.get("status_group") or status.get("status") or "").lower()
        is_final = bool(status.get("is_final"))
        print(f"[poll] task={task_id} state={state} final={is_final} progress={status.get('progress', '')}", flush=True)
        if is_final:
            if state in FAILED_STATES or status.get("error"):
                raise RuntimeError(f"Task failed: {json.dumps(status, ensure_ascii=False)}")
            return status
        if state in FAILED_STATES:
            raise RuntimeError(f"Task failed: {json.dumps(status, ensure_ascii=False)}")
        time.sleep(poll_seconds)


def process_variant(product_dir: Path, variant: dict[str, Any], api_key: str, args: argparse.Namespace) -> dict[str, Any]:
    variant_id = int(variant.get("variant_id", 0))
    output_dir = product_dir / "videos_lk888"
    output_path = output_dir / f"variant-{variant_id:02d}.mp4"
    if output_path.exists() and not args.force:
        return {"variant_id": variant_id, "status": "skipped_existing", "output_path": str(output_path.relative_to(product_dir))}
    reference_images = generated_keyframe_paths(product_dir, variant_id)
    if not reference_images:
        raise RuntimeError(f"Missing generated reference image(s) for variant {variant_id}")
    uploads = upload_references(product_dir, reference_images[:2], args.upload_lifetime)
    prompt = append_native_audio_instruction(variant.get("video_prompt") or "Create a product UGC video.", variant.get("voiceover_script_8s"))
    params = build_model_params(args, [item["url"] for item in uploads])
    payload = {"model": args.model, "prompt": prompt, "params": params, "count": 1}
    if args.dry_run:
        return {
            "variant_id": variant_id,
            "status": "dry_run",
            "model": args.model,
            "reference_images": uploads,
            "payload": payload,
            "output_path": str(output_path.relative_to(product_dir)),
        }
    print(f"[create] {product_dir.name} variant {variant_id:02d} model={args.model}", flush=True)
    create_response = lk888_post(api_key, "/v1/media/generate", payload, args.base_url)
    task_ids = extract_task_ids(create_response)
    if not task_ids:
        raise RuntimeError(f"Missing task_id: {json.dumps(create_response, ensure_ascii=False)}")
    task_id = task_ids[0]
    status_response = poll_task(api_key, task_id, args.base_url, args.poll_seconds)
    result_url = status_response.get("result_url") or status_response.get("url")
    if not result_url:
        raise RuntimeError(f"Task completed without result_url: {json.dumps(status_response, ensure_ascii=False)}")
    downloaded = download_binary(result_url, output_path, timeout=300)
    if not downloaded:
        raise RuntimeError(f"Download failed: {result_url}")
    return {
        "variant_id": variant_id,
        "task_id": task_id,
        "model": args.model,
        "reference_images": uploads,
        "prompt": prompt,
        "params": params,
        "create_response": create_response,
        "status_response": status_response,
        "content_response": {"url": result_url, "output_path": str(output_path.relative_to(product_dir))},
    }


def process_product(product_dir: Path, api_key: str, selected_variants: set[int], args: argparse.Namespace) -> None:
    prompts = load_json(product_dir / "ugc_prompts.json")
    results_path = product_dir / "videos_lk888" / "video_generation_results.json"
    existing = load_json(results_path, {"results": []})
    results = list(existing.get("results", []))
    for variant in prompts.get("variants", []):
        variant_id = int(variant.get("variant_id", 0))
        if variant_id not in selected_variants:
            continue
        result = process_variant(product_dir, variant, api_key, args)
        results = [item for item in results if int(item.get("variant_id", 0)) != variant_id]
        results.append(result)
        write_json(results_path, {"results": results})


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate product videos with LK888/updrama media API.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--products", default="")
    parser.add_argument("--variants", default="1-10")
    parser.add_argument("--model", default="veo3.1-lite")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--generation-mode", default="fast")
    parser.add_argument("--quality", default="sd")
    parser.add_argument("--aspect-ratio", default="9:16")
    parser.add_argument("--enhance-prompt", default="false")
    parser.add_argument("--enable-upsample", default=None)
    parser.add_argument("--upload-lifetime", default="1h", choices=["1h"])
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    api_key = "dry-run" if args.dry_run else require_lk888_api_key()
    selected_variants = parse_variants(args.variants)
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        process_product(product_dir, api_key, selected_variants, args)


if __name__ == "__main__":
    main()

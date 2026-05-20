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


def resolve_prompts_path(product_dir: Path, prompts_file: str) -> Path:
    candidate = Path(prompts_file)
    if candidate.is_absolute():
        return candidate
    return product_dir / prompts_file


def generated_keyframe_paths(product_dir: Path, variant_id: int) -> list[Path]:
    start = product_dir / "generated_images" / f"variant-{variant_id:02d}-start.png"
    end = product_dir / "generated_images" / f"variant-{variant_id:02d}-end.png"
    if start.exists() and end.exists():
        return [start, end]
    single = product_dir / "generated_images" / f"variant-{variant_id:02d}.png"
    if single.exists():
        return [single]
    return []


def existing_video_dir(product_dir: Path) -> Path:
    return product_dir / "videos"


def existing_variant_max(video_dir: Path) -> int:
    max_variant = 0
    for path in video_dir.glob("variant-*.mp4"):
        try:
            variant_id = int(path.stem.split("-", 1)[1])
        except Exception:
            continue
        max_variant = max(max_variant, variant_id)
    return max_variant


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


def upload_uguu(path: Path) -> str:
    with path.open("rb") as file_handle:
        response = requests.post(
            "https://uguu.se/upload.php",
            files={"files[]": (path.name, file_handle, "image/png")},
            timeout=120,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Uguu upload failed HTTP {response.status_code}: {response.text[:500]}")
    data = response.json()
    files = data.get("files") or []
    url = files[0].get("url") if files and isinstance(files[0], dict) else ""
    if not data.get("success") or not url:
        raise RuntimeError(f"Unexpected Uguu upload response for {path}: {response.text[:500]}")
    return url


def with_retries(label: str, attempts: int, backoff_seconds: float, operation: Any) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if attempt >= attempts:
                break
            wait_seconds = backoff_seconds * attempt
            print(f"[retry] {label} attempt {attempt}/{attempts} failed: {error}", flush=True)
            time.sleep(wait_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{label} failed without a captured error")


def upload_reference(
    path: Path,
    host: str,
    lifetime: str,
    upload_retries: int,
    retry_backoff_seconds: float,
) -> tuple[str, int, str]:
    now = int(time.time())
    if host == "uguu":
        url = with_retries(
            f"upload {path.name} to uguu",
            upload_retries,
            retry_backoff_seconds,
            lambda: upload_uguu(path),
        )
        return url, now + 23 * 60 * 60, "uguu.se"
    url = with_retries(
        f"upload {path.name} to litterbox",
        upload_retries,
        retry_backoff_seconds,
        lambda: upload_litterbox(path, lifetime=lifetime),
    )
    return url, now + 50 * 60 if lifetime == "1h" else now + 10 * 60, "litterbox.catbox.moe"


def upload_references(
    product_dir: Path,
    reference_images: list[Path],
    lifetime: str,
    host: str,
    upload_retries: int,
    retry_backoff_seconds: float,
) -> list[dict[str, str]]:
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
        cached_host = cached.get("host", "")
        if not url or cached_host != host or expires_at - now < 900:
            print(f"[upload] {relative}", flush=True)
            url, expires_at, stored_host = upload_reference(
                image_path,
                host,
                lifetime,
                upload_retries,
                retry_backoff_seconds,
            )
            uploads[relative] = {"url": url, "uploaded_at": now, "expires_at": expires_at, "host": stored_host}
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
        "No subtitles, no captions, no readable on-screen text, no labels, no Instagram or INS icons, no TikTok icons, no app UI, no watermarks. "
    )
    if line:
        audio_block += f"Spoken voiceover, complete within 8 seconds: \"{line}\""
    else:
        audio_block += "Use a short natural product-demo voiceover that finishes within 8 seconds."
    return prompt + audio_block


def prompt_has_native_audio(prompt: str) -> bool:
    upper_prompt = prompt.upper()
    return "NATIVE AUDIO" in upper_prompt or "VOICEOVER" in upper_prompt


def first_voice_line(voice_lines: Any, fallback: str = "") -> str:
    line = ""
    if isinstance(voice_lines, list) and voice_lines:
        first = voice_lines[0]
        if isinstance(first, dict):
            line = str(first.get("line") or first.get("text") or "").strip()
        else:
            line = str(first).strip()
    elif isinstance(voice_lines, str):
        line = voice_lines.strip()
    return (line or fallback).replace("—", ", ")


def overlay_callouts(variant: dict[str, Any], enabled: bool) -> list[str]:
    if not enabled:
        return []
    raw_callouts = variant.get("on_screen_callouts") or []
    cleaned: list[str] = []
    for item in raw_callouts:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("label") or "").strip()
        else:
            text = ""
        if not text:
            continue
        cleaned.append(text[:18])
        if len(cleaned) >= 2:
            break
    return cleaned


def append_safe_audio_test_instruction(prompt: str, voice_lines: Any) -> str:
    safe_line = first_voice_line(voice_lines, "Place the trap outside after adding bait.")
    audio_block = (
        "\n\nNATIVE AUDIO TEST: Include one short natural English sentence in a young adult female voice. "
        "No music, no singing, no hype, no slang, no labels, no subtitles, no captions, no readable on-screen text, no Instagram or INS icons, no TikTok icons, no app UI, no watermarks. "
        f"Speak exactly this one sentence and nothing else: \"{safe_line}\""
    )
    return prompt + audio_block


def append_safe_native_audio_instruction(prompt: str, voice_lines: Any) -> str:
    safe_line = first_voice_line(voice_lines, "Here is how the product works.")
    audio_block = (
        "\n\nNATIVE AUDIO: Include one short natural English voice line in a young adult female voice. "
        "No music, no singing, no hype words, no slang, no labels, no subtitles, no captions, no readable on-screen text, no Instagram or INS icons, no TikTok icons, no app UI, no watermarks. "
        f"Speak exactly this one sentence and nothing else: \"{safe_line}\""
    )
    return prompt + audio_block


def append_mid_native_audio_instruction(prompt: str, voice_lines: Any, callouts: list[str]) -> str:
    safe_line = first_voice_line(voice_lines, "Here is how the product works.")
    overlay_block = ""
    if callouts:
        joined = ", ".join(f"\"{item}\"" for item in callouts[:2])
        overlay_block = (
            f" Allow only {len(callouts[:2])} tiny tasteful social-style feature-tag overlays, optionally with one simple product-relevant emoji: {joined}. "
            "Keep them very small, decorative, and brief. Never render Instagram or INS icons, TikTok icons, app UI chrome, watermarks, full-sentence captions, subtitles, lower thirds, or transcripts."
        )
    audio_block = (
        "\n\nNATIVE AUDIO: Generate natural native audio inside the video: a bright, young American female ecommerce creator voice, friendly, clear, slightly energetic, not robotic, not corporate. "
        f"Spoken voiceover, complete within 8 seconds: \"{safe_line}\" "
        "Add subtle upbeat modern product-ad background music under the voice at low volume, no lyrics, plus light real handling sounds. "
        "No subtitles, no captions, no Instagram or INS icons, no TikTok icons, no app UI, no watermarks, and no readable on-screen text beyond any explicitly allowed tiny decorative feature-tag overlays."
    )
    return prompt + overlay_block + audio_block


def append_asmr_audio_instruction(prompt: str) -> str:
    audio_block = (
        "\n\nNATIVE AUDIO: Generate clean ASMR-style native audio only. No spoken voiceover, no dialogue, no narration, no music. "
        "Use crisp realistic kitchen sounds only: suction click, vegetable tapping on the counter, gentle pusher contact, smooth crank rotation, stainless drum rasp, crisp slicing or grating texture, and shreds or slices falling into a glass bowl. "
        "Keep the sound intimate, detailed, satisfying, and natural. No subtitles, no captions, no Instagram or INS icons, no TikTok icons, no app UI, no watermarks."
    )
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
    if args.model.startswith("doubao-seedance"):
        return {
            "images": image_urls,
            "audio_duration": args.audio_duration,
            "resolution": args.resolution,
            "ratio": args.aspect_ratio,
            "generate_audio": "true" if args.generate_audio else "false",
        }
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
    output_dir = existing_video_dir(product_dir)
    output_path = output_dir / f"variant-{variant_id:02d}.mp4"
    if output_path.exists() and not args.force:
        return {"variant_id": variant_id, "status": "skipped_existing", "output_path": str(output_path.relative_to(product_dir))}
    reference_images = generated_keyframe_paths(product_dir, variant_id)
    if not reference_images:
        raise RuntimeError(f"Missing generated reference image(s) for variant {variant_id}")
    if args.single_reference:
        reference_images = reference_images[:1]
    uploads = upload_references(
        product_dir,
        reference_images[:2],
        args.upload_lifetime,
        args.upload_host,
        args.upload_retries,
        args.retry_backoff_seconds,
    )
    base_prompt = variant.get("video_prompt") or "Create a product UGC video."
    callouts = overlay_callouts(variant, args.light_overlay)
    if args.audio_style == "none" or prompt_has_native_audio(base_prompt):
        prompt = base_prompt
    else:
        prompt = (
            append_safe_audio_test_instruction(base_prompt, variant.get("voiceover_script_8s")) if args.safe_audio_test else (
                append_asmr_audio_instruction(base_prompt)
                if args.audio_style == "asmr"
                else
                append_mid_native_audio_instruction(base_prompt, variant.get("voiceover_script_8s"), callouts)
                if args.audio_style == "mid"
                else append_native_audio_instruction(base_prompt, variant.get("voiceover_script_8s"))
                if args.audio_style == "legacy"
                else append_safe_native_audio_instruction(base_prompt, variant.get("voiceover_script_8s"))
            )
        )
    params = build_model_params(args, [item["url"] for item in uploads])
    payload = {"model": args.model, "prompt": prompt, "params": params, "count": 1}
    print(f"[create] {product_dir.name} variant {variant_id:02d} model={args.model}", flush=True)
    create_response = with_retries(
        f"create task for {product_dir.name} variant {variant_id:02d}",
        args.create_retries,
        args.retry_backoff_seconds,
        lambda: lk888_post(api_key, "/v1/media/generate", payload, args.base_url),
    )
    task_ids = extract_task_ids(create_response)
    if not task_ids:
        raise RuntimeError(f"Missing task_id: {json.dumps(create_response, ensure_ascii=False)}")
    task_id = task_ids[0]
    status_response = poll_task(api_key, task_id, args.base_url, args.poll_seconds)
    result_url = status_response.get("result_url") or status_response.get("url")
    if not result_url:
        raise RuntimeError(f"Task completed without result_url: {json.dumps(status_response, ensure_ascii=False)}")
    downloaded = with_retries(
        f"download result for {product_dir.name} variant {variant_id:02d}",
        args.download_retries,
        args.retry_backoff_seconds,
        lambda: download_binary(result_url, output_path, timeout=300),
    )
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
    prompts = load_json(resolve_prompts_path(product_dir, args.prompts_file))
    output_dir = existing_video_dir(product_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "video_generation_results.json"
    existing = load_json(results_path, {"results": []})
    results = list(existing.get("results", []))
    for variant in prompts.get("variants", []):
        variant_id = int(variant.get("variant_id", 0))
        if variant_id not in selected_variants:
            continue
        current_variant = dict(variant)
        try:
            result = process_variant(product_dir, current_variant, api_key, args)
        except Exception as error:
            if not args.continue_on_error:
                raise
            result = {
                "variant_id": current_variant["variant_id"],
                "status": "failed",
                "error": str(error),
                "output_path": str((output_dir / f"variant-{current_variant['variant_id']:02d}.mp4").relative_to(product_dir)),
            }
        results = [item for item in results if int(item.get("variant_id", 0)) != current_variant["variant_id"]]
        results.append(result)
        write_json(results_path, {"results": results})


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate product videos with LK888/updrama media API.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--products", default="")
    parser.add_argument("--variants", default="1-10")
    parser.add_argument("--prompts-file", default="ugc_prompts.json")
    parser.add_argument("--model", default="veo3.1-lite")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--generation-mode", default="fast")
    parser.add_argument("--quality", default="sd")
    parser.add_argument("--aspect-ratio", default="9:16")
    parser.add_argument("--audio-duration", default="8")
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--generate-audio", action="store_true")
    parser.add_argument("--output-subdir", default="")
    parser.add_argument("--enhance-prompt", default="false")
    parser.add_argument("--enable-upsample", default=None)
    parser.add_argument("--upload-host", default="litterbox", choices=["litterbox", "uguu"])
    parser.add_argument("--upload-lifetime", default="1h", choices=["1h"])
    parser.add_argument("--upload-retries", type=int, default=4)
    parser.add_argument("--create-retries", type=int, default=3)
    parser.add_argument("--download-retries", type=int, default=4)
    parser.add_argument("--retry-backoff-seconds", type=float, default=5.0)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--audio-style", default="safe", choices=["none", "safe", "mid", "legacy", "asmr"])
    parser.add_argument("--light-overlay", action="store_true")
    parser.add_argument("--safe-audio-test", action="store_true")
    parser.add_argument("--single-reference", action="store_true", help="Use only the first generated reference image instead of first/last keyframes.")
    parser.add_argument("--continue-on-error", action="store_true", help="Record failed variants and continue processing the batch.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    api_key = require_lk888_api_key()
    selected_variants = parse_variants(args.variants)
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        process_product(product_dir, api_key, selected_variants, args)


if __name__ == "__main__":
    main()

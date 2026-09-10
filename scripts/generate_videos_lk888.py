#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from common import download_binary, load_json, selected_product_dirs, write_json
from generate_images import parse_variants

# The desktop environment may inject a stale local SOCKS proxy.  LK888 and
# public reference hosts must be reached directly for production submissions.
for _proxy_key in list(os.environ):
    if "proxy" in _proxy_key.lower():
        os.environ.pop(_proxy_key, None)


BASE_URL = "https://api.lk888.ai/api"
CONTINUE_STATES = {"pending", "running", "queued", "processing", "submitted"}
SUCCESS_STATES = {"success", "completed", "succeeded"}
FAILED_STATES = {"failed", "error", "cancelled", "canceled", "expired"}
DEFAULT_ASPECT_RATIO = "9:16"


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


def variant_reference_paths(product_dir: Path, variant: dict[str, Any]) -> list[Path]:
    raw_paths = variant.get("reference_images") or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    if not isinstance(raw_paths, list):
        raise RuntimeError("reference_images must be a path string or a list of path strings")

    paths: list[Path] = []
    for raw_path in raw_paths:
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = product_dir / path
        if not path.exists():
            raise RuntimeError(f"Missing variant reference image: {path}")
        paths.append(path)
    return paths


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def omni_storyboard_identity_paths(product_dir: Path, variant: dict[str, Any]) -> list[Path]:
    """Return the fixed v2 Omni pair: chronological storyboard + identity grid."""
    from v2_contract import load_identity, local_file

    identity = load_identity(product_dir)
    identity_sheet = local_file(product_dir, identity["output_path"])
    explicit_references = unique_paths(variant_reference_paths(product_dir, variant))
    storyboard = next(
        (
            path
            for path in explicit_references
            if path.resolve() != identity_sheet.resolve()
            and (
                "storyboard" in path.name.lower()
                or "storyboard" in str(load_json(path.with_suffix(".provenance.json"), {}).get("type", "")).lower()
            )
        ),
        None,
    )
    if storyboard is None:
        raise RuntimeError(
            "Omni reference mode requires an Image2-generated chronological storyboard in variant reference_images"
        )
    if not storyboard.with_suffix(".provenance.json").is_file():
        raise RuntimeError(f"Storyboard is missing provenance: {storyboard}")
    return [storyboard, identity_sheet]


def generated_start_end_paths(product_dir: Path, variant_id: int) -> tuple[Path, Path]:
    return (
        product_dir / "generated_images" / f"variant-{variant_id:02d}-start.png",
        product_dir / "generated_images" / f"variant-{variant_id:02d}-end.png",
    )


def is_veo_model(model: str) -> bool:
    return model.lower().startswith("veo")


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
        "--noproxy", "*",
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
        session = requests.Session()
        session.trust_env = False
        response = session.post(
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


def append_native_audio_instruction(prompt: str, voice_lines: Any, locale: str = "en-US") -> str:
    voice, language = voice_profile(locale)
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
        f"\n\nNATIVE AUDIO: Generate natural native audio inside the video: a bright {voice} ecommerce creator voice, energetic but not robotic, with subtle upbeat social-ad background music. Every spoken word must be in {language}; never answer in English. "
        "No subtitles, no captions, no readable on-screen text, no labels, no social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, no watermarks. "
    )
    if line:
        audio_block += f"Spoken voiceover, complete within 8 seconds: \"{line}\""
    else:
        audio_block += "Use a short natural product-demo voiceover that finishes within 8 seconds."
    return prompt + audio_block


def prompt_has_native_audio(prompt: str) -> bool:
    upper_prompt = prompt.upper()
    return "NATIVE AUDIO" in upper_prompt or "VOICEOVER" in upper_prompt


def compact_voiceover_line(voice_lines: Any, fallback: str = "", max_words: int = 18) -> str:
    lines: list[str] = []
    if isinstance(voice_lines, list):
        for item in voice_lines:
            if isinstance(item, dict):
                text = str(item.get("line") or item.get("text") or "").strip()
            else:
                text = str(item).strip()
            if text:
                lines.append(text)
    elif isinstance(voice_lines, str):
        lines.append(voice_lines.strip())
    text = " ".join(lines) or fallback
    text = text.replace("—", ", ")
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(" ,.-")
    return text


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


VOICE_LOCALE_PROFILES: dict[str, tuple[str, str]] = {
    "en-US": ("young American woman", "English"),
    "es-MX": ("young Mexican woman speaking natural Mexican Spanish, with the clear open vowels and rhythm of Mexico rather than Spain",
              "Mexican Spanish as spoken in Mexico"),
    "es-ES": ("young Spanish woman speaking Castilian Spanish from Spain", "Castilian Spanish from Spain"),
    "es-419": ("young Latin American woman speaking neutral Latin American Spanish", "neutral Latin American Spanish"),
    "pt-BR": ("young Brazilian woman speaking Brazilian Portuguese", "Brazilian Portuguese"),
}


def voice_profile(locale: str | None) -> tuple[str, str]:
    return VOICE_LOCALE_PROFILES.get(str(locale or "en-US"), VOICE_LOCALE_PROFILES["en-US"])


def append_safe_audio_test_instruction(prompt: str, voice_lines: Any, locale: str = "en-US") -> str:
    voice, language = voice_profile(locale)
    safe_line = first_voice_line(voice_lines, "Place the trap outside after adding bait.")
    audio_block = (
        f"\n\nNATIVE AUDIO TEST: Include one short natural sentence in {language}. The speaker is a {voice}. "
        "No music, no singing, no hype, no slang, no labels, no subtitles, no captions, no readable on-screen text, no social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, no watermarks. "
        f"Speak exactly this one sentence and nothing else: \"{safe_line}\""
    )
    return prompt + audio_block


def append_safe_native_audio_instruction(prompt: str, voice_lines: Any, locale: str = "en-US") -> str:
    voice, language = voice_profile(locale)
    safe_line = first_voice_line(voice_lines, "Here is how the product works.")
    audio_block = (
        f"\n\nNATIVE AUDIO: Include one short natural voice line in {language}. The speaker is a {voice}. Every spoken word must be in {language}; never answer in English. "
        "No music, no singing, no hype words, no slang, no labels, no subtitles, no captions, no readable on-screen text, no social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, no watermarks. "
        f"Speak exactly this one sentence and nothing else: \"{safe_line}\""
    )
    return prompt + audio_block


def append_mid_native_audio_instruction(prompt: str, voice_lines: Any, callouts: list[str], locale: str = "en-US") -> str:
    voice, language = voice_profile(locale)
    safe_line = compact_voiceover_line(voice_lines, "Watch this tiny upgrade make the setup feel easier.", max_words=18)
    overlay_block = ""
    if callouts:
        safe_callouts = []
        for item in callouts[:2]:
            text = re.sub(r"[^\x00-\x7F]+", "", str(item))
            text = re.sub(r"[^A-Za-z0-9 %&+/-]", "", text)
            text = " ".join(text.split()[:3])[:18].strip()
            if text:
                safe_callouts.append(text)
        joined = ", ".join(f"\"{item}\"" for item in safe_callouts)
        overlay_block = (
            f" Allow only {len(safe_callouts)} stylish short-form creator typography feature-tag overlays: {joined}. "
            "Render them as stylish short-form creator typography: bold rounded pill labels, warm vibrant accent tints, compact pop-up badges, modern fashion-tag feel. Keep them brief and not synchronized with the spoken voiceover. Never render full-sentence captions, subtitles, transcripts, lower thirds, karaoke text, social media icons, platform logos, camera/reel icons, reaction icons, app UI chrome, watermarks, or emoji text."
            if safe_callouts
            else ""
        )
    audio_block = (
        f"\n\nNATIVE AUDIO: Generate natural native audio inside the video: a bright {voice} lifestyle-commerce creator voice, stylish, warm, emotionally engaged, friendly, clear, not robotic, not corporate. "
        f"Every spoken word must be in {language}; never answer in English. "
        f"Spoken voiceover, complete within 8 seconds: \"{safe_line}\" "
        "Add subtle upbeat modern lifestyle background music under the voice at low volume, no lyrics, plus light real handling sounds. "
        "No subtitles, no captions, no full-sentence labels, no emoji text, no social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, and no watermarks. The only allowed readable text is the explicitly allowed tiny feature-tag overlay words."
    )
    return prompt + overlay_block + audio_block


def append_asmr_audio_instruction(prompt: str) -> str:
    audio_block = (
        "\n\nNATIVE AUDIO: Generate clean ASMR-style native audio only. No spoken voiceover, no dialogue, no narration, no music. "
        "Use crisp realistic kitchen sounds only: suction click, vegetable tapping on the counter, gentle pusher contact, smooth crank rotation, stainless drum rasp, crisp slicing or grating texture, and shreds or slices falling into a glass bowl. "
        "Keep the sound intimate, detailed, satisfying, and natural. No subtitles, no captions, no social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, no watermarks."
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
    if args.model == "kwvideo-v2":
        return {
            "version": args.version,
            "duration": str(args.duration),
            "aspect_ratio": args.aspect_ratio,
            "resolution": args.resolution,
            "images": image_urls[:2],
        }
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
    if args.model in {"omni-flash", "omni_flash-10s"}:
        params = {
            "aspect_ratio": args.aspect_ratio,
            "images": image_urls[:7] if args.model == "omni_flash-10s" else image_urls[:3],
        }
        if args.model == "omni-flash":
            params["duration"] = str(args.duration)
            params["enhance_prompt"] = args.enhance_prompt
        if args.enable_upsample is not None:
            params["enable_upsample"] = args.enable_upsample
        return params
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
    for key in ["task_id", "id", "任务id", "任务ID"]:
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


def compact_omni_prompt(
    variant: dict[str, Any],
    duration: str,
    reference_mode: str,
    product_dir: Path | None = None,
) -> str:
    """Keep Omni prompts inside the provider's 4,000-character hard limit."""
    def clipped(value: Any, limit: int) -> str:
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value or "")
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit].rstrip()

    storyboard = variant.get("storyboard_10s") or variant.get("storyboard_8s") or variant.get("shot_plan") or []
    beats: list[str] = []
    if isinstance(storyboard, list):
        for item in storyboard:
            if isinstance(item, dict):
                visual = str(item.get("visual") or item.get("shot") or "").strip()
                spoken = str(item.get("spoken") or "").strip()
                timing = str(item.get("time") or item.get("timing") or "").strip()
                if visual:
                    beat = (f"{timing}: " if timing else "") + visual
                    beats.append(beat + (f"; spoken: {spoken}" if spoken else ""))
    mode_instruction = (
        "Image 1 is the opening frame and image 2 is the final frame; interpolate a continuous action between them."
        if reference_mode == "first-last"
        else "Use exactly two all-purpose references: image 1 is the chronological storyboard and image 2 is the product identity grid; they are not a forced first/final-frame pair."
    )
    voice_items = variant.get("voiceover_script_10s") or variant.get("voiceover_script_8s") or []
    if isinstance(voice_items, list):
        voice = " ".join(str(item.get("line", "")) if isinstance(item, dict) else str(item) for item in voice_items)
    else:
        voice = str(voice_items)
    brief = load_json(product_dir / "product_brief.json", {}) if product_dir else {}
    voice_desc, voice_language = voice_profile(variant.get("voice_locale"))
    identity = variant.get("product_fidelity_block") or brief.get("confirmed_identity") or []
    misuse = variant.get("negative_prompt") or brief.get("misuse_risks_to_avoid") or []
    return (
        f"Create exactly one {duration}-second vertical 9:16 realistic creator-style product video. {mode_instruction} "
        "Preserve the same adult creator, room, wardrobe, lighting, camera geometry, props, and the same single physical product throughout. "
        "Show exactly ONE product in the entire video; never duplicate it in hands, on furniture, in mirrors, reflections, or screens. "
        f"PRODUCT TRUTH AND IDENTITY LOCK: {clipped(identity, 700)}. Match image 2 for silhouette, parts, proportions and controls; when documented SKU colors differ, use the single colorway shown in image 1 consistently. "
        f"MANDATORY SKU FOR THIS VIDEO: {clipped(variant.get('sku_colourway'), 240)}. "
        f"FORBIDDEN DRIFT: {clipped(misuse, 600)}. Never morph, resize, recolor, add branding, invent controls or unsupported functions. "
        f"CONCEPT: {clipped(variant.get('title'), 180)}. HOOK: {clipped(variant.get('hook'), 320)}. "
        f"PRIMARY FUNCTION: {clipped(variant.get('primary_function_focus'), 320)}. "
        f"SCENE: {clipped(variant.get('scene_imagination'), 650)}. "
        f"SHOT PLAN: follow these chronological beats across all {duration} seconds: {clipped(beats or storyboard, 1250)}. "
        f"SUPPORTED ACTION: {clipped(variant.get('usage_logic'), 650)}. "
        f"PAYOFF: {clipped(variant.get('proof_moment'), 450)}. "
        f"NATIVE AUDIO: {voice_desc} creator voice, natural and warm. Speak exactly: {clipped(voice, 400)}. Every spoken word must be in {voice_language}; never answer in English. Do not add speech. Add subtle room/product sounds and low music without singing. "
        "No subtitles, captions, labels, overlays, logos, watermarks, app UI, touchscreen, wireless charging, projector, camera lens, extra accessories, extra products, or unsupported claims. Use natural handheld motion."
        + (" Finish exactly on image 2." if reference_mode == "first-last" else "")
    )


def poll_task(api_key: str, task_id: str, base_url: str, poll_seconds: int, status_endpoint: str) -> dict[str, Any]:
    transient_errors = 0
    while True:
        try:
            raw = lk888_get(api_key, status_endpoint, base_url, params={"task_id": task_id})
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
    from v2_contract import active, check_existing_video, record_video, require_qc, validate_scene_chain, video_contract
    variant_id = int(variant.get("variant_id", 0))
    output_dir = existing_video_dir(product_dir)
    output_path = output_dir / f"variant-{variant_id:02d}.mp4"
    v2_active = active(product_dir)
    if output_path.exists() and not args.force and not v2_active:
        return {"variant_id": variant_id, "status": "skipped_existing", "output_path": str(output_path.relative_to(product_dir))}
    if is_veo_model(args.model):
        if args.single_reference:
            raise RuntimeError(
                f"{product_dir.name} variant {variant_id:02d}: VEO must use both start and end keyframes. "
                "Remove --single-reference and generate the missing keyframe first."
            )
        start_frame, end_frame = generated_start_end_paths(product_dir, variant_id)
        missing = [path.name for path in (start_frame, end_frame) if not path.exists()]
        if missing:
            raise RuntimeError(
                f"{product_dir.name} variant {variant_id:02d}: VEO requires start+end keyframes; missing {', '.join(missing)}. "
                "Run generate_images.py with --keyframes for this variant before submitting VEO."
            )
        reference_images = [start_frame, end_frame]
    elif args.model in {"omni-flash", "omni_flash-10s"} and args.reference_mode == "first-last":
        start_frame, end_frame = generated_start_end_paths(product_dir, variant_id)
        missing = [path.name for path in (start_frame, end_frame) if not path.exists()]
        if missing:
            raise RuntimeError(
                f"{product_dir.name} variant {variant_id:02d}: Omni first-last mode requires both keyframes; "
                f"missing {', '.join(missing)}. Generate and QC the missing frame first."
            )
        reference_images = [start_frame, end_frame]
    elif args.model in {"omni-flash", "omni_flash-10s"} and args.reference_mode == "omni-reference":
        generated = generated_keyframe_paths(product_dir, variant_id)
        if v2_active:
            # V2 Omni uses one stable, explicit pair. The real product photo is
            # upstream evidence for creating/QC'ing the identity grid, not a
            # third video-model reference.
            reference_images = omni_storyboard_identity_paths(product_dir, variant)
        else:
            reference_images = unique_paths(generated[:1] + variant_reference_paths(product_dir, variant))[:3]
    else:
        reference_images = unique_paths(
            generated_keyframe_paths(product_dir, variant_id)
            + variant_reference_paths(product_dir, variant)
        )
    if not reference_images:
        raise RuntimeError(f"Missing generated reference image(s) for variant {variant_id}")
    if args.single_reference:
        reference_images = reference_images[:1]
    if v2_active:
        # A generated storyboard can live in an append-only run folder rather
        # than the canonical generated_images directory. Its provenance file is
        # the durable proof that it is an Image2-generated scene reference.
        scene_refs = [p for p in reference_images if p.with_suffix(".provenance.json").is_file()]
        if not scene_refs:
            raise RuntimeError("v2 video requires generated scene frames")
        validate_scene_chain(product_dir, scene_refs)
        require_qc(product_dir, scene_refs, "keyframes",
                   override=bool(getattr(args, "allow_unverified_references", False)))
    reference_limit = 7 if args.model == "omni_flash-10s" else 3 if args.model == "omni-flash" else 2
    base_prompt = variant.get("video_prompt") or compact_omni_prompt(
        variant, str(args.duration), args.reference_mode, product_dir
    )
    if args.model in {"omni-flash", "omni_flash-10s"} and len(base_prompt) > 4000:
        base_prompt = compact_omni_prompt(variant, str(args.duration), args.reference_mode, product_dir)
        print(f"[prompt] compacted Omni prompt to {len(base_prompt)} characters", flush=True)
    scale_lock = str(variant.get("_physical_scale_lock") or "").strip()
    if scale_lock:
        base_prompt += " STRICT PHYSICAL SCALE THROUGHOUT: " + scale_lock
    expected = video_contract(product_dir, reference_images[:reference_limit], args.model, base_prompt, {
        "aspect_ratio": args.aspect_ratio, "duration": str(args.duration),
        "audio_duration": str(args.audio_duration), "resolution": args.resolution,
        "generate_audio": bool(args.generate_audio), "generation_mode": args.generation_mode,
        "version": args.version, "quality": args.quality, "enhance_prompt": args.enhance_prompt,
        "audio_style": args.audio_style, "light_overlay": bool(args.light_overlay),
        "safe_audio_test": bool(args.safe_audio_test), "enable_upsample": args.enable_upsample,
        "reference_mode": args.reference_mode,
        "base_url": args.base_url, "status_endpoint": args.status_endpoint,
    }) if v2_active else {}
    if output_path.exists() and not args.force:
        check_existing_video(product_dir, output_path, expected)
        return {"variant_id": variant_id, "status": "skipped_existing_verified_v2",
                "output_path": str(output_path.relative_to(product_dir))}
    uploads = upload_references(
        product_dir,
        reference_images[:reference_limit],
        args.upload_lifetime,
        args.upload_host,
        args.upload_retries,
        args.retry_backoff_seconds,
    )
    callouts = overlay_callouts(variant, args.light_overlay)
    voiceover = variant.get("voiceover_script_10s") or variant.get("voiceover_script_8s")
    voice_locale = str(variant.get("voice_locale") or getattr(args, "voice_locale", "en-US"))
    if args.audio_style == "none" or prompt_has_native_audio(base_prompt):
        prompt = base_prompt
    else:
        prompt = (
            append_safe_audio_test_instruction(base_prompt, voiceover, voice_locale) if args.safe_audio_test else (
                append_asmr_audio_instruction(base_prompt)
                if args.audio_style == "asmr"
                else
                append_mid_native_audio_instruction(base_prompt, voiceover, callouts, voice_locale)
                if args.audio_style == "mid"
                else append_native_audio_instruction(base_prompt, voiceover, voice_locale)
                if args.audio_style == "legacy"
                else append_safe_native_audio_instruction(base_prompt, voiceover, voice_locale)
            )
        )
    params = build_model_params(args, [item["url"] for item in uploads])
    payload = {"model": args.model, "prompt": prompt, "params": params, "count": 1}
    print(
        f"[params] aspect_ratio={args.aspect_ratio} duration={args.duration} "
        f"reference_mode={args.reference_mode} images={len(params.get('images') or [])}",
        flush=True,
    )
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
    task_record_path = output_dir / f"variant-{variant_id:02d}.task.json"
    write_json(task_record_path, {
        "variant_id": variant_id,
        "task_id": task_id,
        "status": "submitted",
        "model": args.model,
        "created_at": int(time.time()),
        "reference_mode": args.reference_mode,
        "params": {key: value for key, value in params.items() if key != "images"},
    })
    print(f"[submitted] variant={variant_id:02d} task_id={task_id}", flush=True)
    status_response = poll_task(api_key, task_id, args.base_url, args.poll_seconds, args.status_endpoint)
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
    write_json(task_record_path, {
        "variant_id": variant_id,
        "task_id": task_id,
        "status": "success",
        "model": args.model,
        "completed_at": int(time.time()),
        "result_url": result_url,
        "output_path": str(output_path.relative_to(product_dir)),
    })
    if v2_active:
        recorded_params = {key: value for key, value in params.items() if key != "images"}
        record_video(product_dir, output_path, expected, prompt,
                     {"task_id": task_id, "base_url": args.base_url, "params": recorded_params,
                      "reference_qc_override": bool(getattr(args, "allow_unverified_references", False))})
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
    selected = []
    for variant in prompts.get("variants", []):
        variant_id = int(variant.get("variant_id", 0))
        if variant_id not in selected_variants:
            continue
        current_variant = dict(variant)
        current_variant["_physical_scale_lock"] = prompts.get("physical_scale_lock", "")
        selected.append(current_variant)

    def run_variant(current_variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return process_variant(product_dir, current_variant, api_key, args)
        except Exception as error:
            if not args.continue_on_error:
                raise
            return {
                "variant_id": current_variant["variant_id"],
                "status": "failed",
                "error": str(error),
                "output_path": str((output_dir / f"variant-{current_variant['variant_id']:02d}.mp4").relative_to(product_dir)),
            }

    workers = max(1, min(args.workers, len(selected) or 1))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(run_variant, variant): variant for variant in selected}
        for future in concurrent.futures.as_completed(future_map):
            current_variant = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                # One bad variant must not discard the whole batch
                result = {
                    "variant_id": current_variant["variant_id"],
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "output_path": str((output_dir / f"variant-{current_variant['variant_id']:02d}.mp4").relative_to(product_dir)),
                }
                print(f"[video] variant {current_variant['variant_id']:02d} failed: {exc}", flush=True)
            results = [item for item in results if int(item.get("variant_id", 0)) != current_variant["variant_id"]]
            results.append(result)
            results.sort(key=lambda item: int(item.get("variant_id", 0)))
            write_json(results_path, {"results": results})


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate product videos with LK888/updrama media API.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--products", default="")
    parser.add_argument("--variants", default="1-10")
    parser.add_argument("--prompts-file", default="ugc_prompts.json")
    parser.add_argument("--model", default="veo3.1")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--status-endpoint", default="/v1/skills/task-status")
    parser.add_argument("--generation-mode", default="fast")
    parser.add_argument("--version", default="快速")
    parser.add_argument("--quality", default="sd")
    parser.add_argument("--aspect-ratio", default=DEFAULT_ASPECT_RATIO)
    parser.add_argument(
        "--duration",
        default=None,
        help="Video duration. Defaults to 10 for omni-flash/omni_flash-10s and 8 for other models.",
    )
    parser.add_argument("--audio-duration", default=None)
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
    parser.add_argument(
        "--reference-mode",
        default="first-last",
        choices=["first-last", "omni-reference"],
        help="Omni image mode: an exact generated start/end pair, or the fixed v2 storyboard + identity-grid pair.",
    )
    parser.add_argument("--single-reference", action="store_true", help="Deprecated alias: use one generated scene image in omni-reference mode.")
    parser.add_argument("--allow-landscape", action="store_true", help="Allow non-9:16 aspect ratios for explicit landscape-only jobs.")
    parser.add_argument("--continue-on-error", action="store_true", help="Record failed variants and continue processing the batch.")
    parser.add_argument("--workers", type=int, default=1, help="Submit and poll independent variants concurrently.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-unverified-references", action="store_true",
                        help="Submit even when keyframe QC has not passed. Only with explicit user sign-off; the override is recorded in each video's provenance.")
    parser.add_argument("--voice-locale", default="en-US",
                        help="Spoken language and accent for the native audio, e.g. en-US, es-MX, es-ES, es-419, pt-BR. A per-variant 'voice_locale' field overrides this.")
    args = parser.parse_args()
    if args.duration is None:
        args.duration = "10" if args.model in {"omni-flash", "omni_flash-10s"} else "8"
    if args.audio_duration is None:
        args.audio_duration = str(args.duration)
    if args.model in {"omni-flash", "omni_flash-10s"} and str(args.duration) not in {"4", "6", "8", "10"}:
        raise SystemExit("Omni duration must be one of 4, 6, 8, or 10 seconds")
    if args.single_reference:
        args.reference_mode = "omni-reference"
    if args.aspect_ratio != DEFAULT_ASPECT_RATIO and not args.allow_landscape:
        raise SystemExit(
            f"Refusing aspect_ratio={args.aspect_ratio}. Product UGC videos default to vertical {DEFAULT_ASPECT_RATIO}; "
            "pass --allow-landscape only when the user explicitly requests landscape."
        )
    api_key = require_lk888_api_key()
    selected_variants = parse_variants(args.variants)
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        process_product(product_dir, api_key, selected_variants, args)


if __name__ == "__main__":
    main()

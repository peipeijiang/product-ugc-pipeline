#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from common import (
    LK888_BASE_URL,
    LK888_IMAGE_FALLBACK_MODEL,
    LK888_IMAGE_MODEL,
    data_url,
    download_binary,
    load_json,
    request_json,
    require_api_key_for_base_url,
    selected_product_dirs,
    write_json,
)
import v2_contract as v2
from storyboard_contract import storyboard_panel_visual, storyboard_spec
from voice_locale import VoiceLocaleError, locale_from_market, normalize_creator_persona, normalize_locale


# Image providers. Every paid image goes through the upDrama/LK888 media-task
# route: tt-image-2.5 is the production default and tt-image-2 is the only
# automatic fallback. There is no other image vendor.
MEDIA_IMAGE_PROVIDER = LK888_IMAGE_MODEL
MEDIA_IMAGE_PROVIDER_ALT = LK888_IMAGE_FALLBACK_MODEL
IMAGE_PROVIDERS = (MEDIA_IMAGE_PROVIDER, MEDIA_IMAGE_PROVIDER_ALT)


def is_media_image_provider(provider: str) -> bool:
    return provider in (MEDIA_IMAGE_PROVIDER, MEDIA_IMAGE_PROVIDER_ALT)


def resolve_image_aspect_ratio(args: argparse.Namespace) -> str:
    """Pick the media-route aspect ratio.

    An explicit --image-aspect-ratio always wins. The default is "auto", which
    derives the ratio from --size. Storyboards supply their derived grid canvas; identity and
    usage sheets pass their own grid canvas and keep that grid proportion.
    """
    requested = str(getattr(args, "image_aspect_ratio", "auto") or "auto")
    if requested != "auto":
        return requested
    size = str(getattr(args, "size", "") or "")
    try:
        width, height = parse_size(size)
    except (TypeError, ValueError):
        return "9:16"
    if width <= 0 or height <= 0:
        return "9:16"
    from math import gcd

    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def media_image_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "aspect_ratio": resolve_image_aspect_ratio(args),
        "resolution": args.image_resolution,
        "version": args.image_version,
        "quality": args.image_quality,
        "background": args.image_background,
    }


def generate_image_via_media_task(
    api_key: str,
    args: argparse.Namespace,
    prompt: str,
    references: list[Path],
    destination: Path,
    model: str,
) -> tuple[dict[str, Any], Path]:
    """Create one upDrama media task, poll to a terminal state and save the frame."""
    params = media_image_params(args)
    if references:
        params["images"] = [data_url(path) for path in references]
    payload = {"model": model, "prompt": prompt, "params": params}
    created = request_json(
        "/v1/media/generate",
        api_key,
        payload,
        base_url=args.image_base_url,
        timeout=args.timeout,
    )
    task_id = (created.get("data") or {}).get("task_id") or created.get("task_id")
    if not task_id:
        raise RuntimeError(f"{model} create failed: {str(created)[:500]}")
    print(f"[media-image] {model} task {task_id}", flush=True)
    deadline = time.time() + args.timeout
    last_state = "pending"
    while time.time() < deadline:
        status = request_json(
            f"/v1/media/status?task_id={task_id}",
            api_key,
            None,
            method="GET",
            base_url=args.image_base_url,
            timeout=60,
        )
        last_state = str(status.get("state") or "")
        if status.get("is_final"):
            if last_state != "success":
                raise RuntimeError(f"{model} task {task_id} ended {last_state}: {str(status.get('error'))[:300]}")
            result_url = str(status.get("result_url") or "")
            if not result_url:
                raise RuntimeError(f"{model} task {task_id} succeeded without result_url")
            if not download_binary(result_url, destination, timeout=args.timeout):
                raise RuntimeError(f"{model} task {task_id} result could not be downloaded")
            return status, destination
        time.sleep(args.image_poll_seconds)
    raise RuntimeError(f"{model} task {task_id} did not finish within {args.timeout}s (last state {last_state})")


def parse_variants(value: str) -> set[int]:
    selected: set[int] = set()
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        if "-" in item:
            start_text, end_text = item.split("-", 1)
            selected.update(range(int(start_text), int(end_text) + 1))
        else:
            selected.add(int(item))
    return selected


def resolve_prompts_path(product_dir: Path, prompts_file: str) -> Path:
    candidate = Path(prompts_file)
    if candidate.is_absolute():
        return candidate
    return product_dir / prompts_file


def first_existing_reference(product_dir: Path, variant: dict[str, Any]) -> Path | None:
    references = existing_references(product_dir, variant, max_references=1)
    return references[0] if references else None


def existing_references(product_dir: Path, variant: dict[str, Any], max_references: int = 1) -> list[Path]:
    if v2.active(product_dir):
        return v2.scene_references(product_dir, "start", int(variant.get("variant_id", 0)))
    references: list[Path] = []
    seen: set[Path] = set()

    def add_reference(local_path: str) -> None:
        if not local_path:
            return
        candidate = product_dir / local_path
        if candidate.exists() and candidate not in seen:
            references.append(candidate)
            seen.add(candidate)

    for local_path in variant.get("selected_reference_images") or []:
        add_reference(local_path)
        if len(references) >= max_references:
            return references
    prompts = load_json(product_dir / "ugc_prompts.json", {})
    for local_path in prompts.get("selected_reference_images") or []:
        add_reference(local_path)
        if len(references) >= max_references:
            return references
    manifest = load_json(product_dir / "product_manifest.json", {})
    for image_item in manifest.get("images", []):
        add_reference(image_item.get("local_path", ""))
        if len(references) >= max_references:
            return references
    return references


def build_image_prompt(variant: dict[str, Any], product_name: str) -> str:
    prompt = (
        variant.get("image_prompt")
        or f"Create a vertical short-form ecommerce UGC product pad image for {product_name}. Preserve the referenced product exactly. No social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, no watermarks."
    )
    scale_lock = str(variant.get("_physical_scale_lock") or "").strip()
    if scale_lock:
        prompt += "\nSTRICT PHYSICAL SCALE: " + scale_lock
    return prompt


def build_storyboard_prompt(variant: dict[str, Any], product_name: str) -> str:
    spec = storyboard_spec(variant)
    timeline = variant["storyboard_10s"]
    market = str(variant.get("market") or "").strip()
    voice_locale = str(variant.get("voice_locale") or "").strip()
    creator_persona = str(variant.get("creator_persona") or "").strip()
    market_locale = locale_from_market(market) if market else None
    locale = normalize_locale(voice_locale) or market_locale
    if locale and market_locale and locale != market_locale:
        raise VoiceLocaleError(
            f"Storyboard market {market!r} resolves to {market_locale}, not voice locale {locale}"
        )
    beats = []
    for item in timeline:
        if not isinstance(item, dict):
            continue
        timing = str(item.get("time") or item.get("timing") or "").strip()
        visual = storyboard_panel_visual(item)
        if visual:
            beats.append(f"{timing}: {visual}" if timing else visual)
    if len(beats) != spec["panel_count"]:
        raise RuntimeError("Storyboard prompt panel count does not match the storyboard contract")
    creator = (
        normalize_creator_persona(creator_persona, locale)
        if locale else creator_persona or f"one adult creator natural to {market or 'the specified target market'}"
    )
    wardrobe_lock = str(variant.get("_wardrobe_lock") or "").strip()
    wardrobe_clause = (
        f"WARDROBE LOCK: the creator wears exactly this same garment, unchanged in cut, color, pattern and fabric, in every single panel of this sheet: {wardrobe_lock}. "
        if wardrobe_lock else ""
    )
    prompt = (
        f"Create one chronological storyboard sheet for a 10-second creator-style product ad for {product_name}. "
        f"The target market is {market or 'the specified market'} and the spoken language is {voice_locale or 'the specified locale'}. "
        f"Cast the same creator throughout: {creator}. Match casting, styling, home details and gestures to the target market; do not inherit a person identity from product references. "
        + wardrobe_clause + 
        f"Board canvas is exactly {spec['size']} pixels at ratio {spec['boardLayoutRatio']}; {spec['columns']} columns by {spec['rows']} rows; each equal panel is exactly {spec['panelPixelSize']} pixels at 9:16. "
        f"Use exactly {spec['panel_count']} edge-to-edge panels read left-to-right, then top-to-bottom. Separate adjacent panels only with very narrow neutral gutters, no wider than 0.5% of the canvas width. "
        "Do not add an outer title band, large white margin, panel number, panel label, frame label, timestamp, header or footer. "
        "Each panel must depict the next moment in this exact sequence: "
        + " | ".join(beats)
        + ". Show exactly one physical product in every panel where it appears; never duplicate it within a panel or through reflections/screens. "
        "Keep one pinned SKU, the same creator identity, wardrobe, room, lighting and product geometry across every panel. "
        "Follow product reveal timing in the visual descriptions exactly. Preserve the canonical product exactly. "
        "Do not show a packaging box unless the timeline explicitly calls for a verified box reference; for this campaign, omit the box entirely and use at most one plain unbranded foil pouch during the opening step. "
        "No legible writing, captions, subtitles, labels, arrows, logos, watermarks, app UI or social-media chrome anywhere."
    )
    scale_lock = str(variant.get("_physical_scale_lock") or "").strip()
    if scale_lock:
        prompt += "\nSTRICT PHYSICAL SCALE: " + scale_lock
    silhouette_lock = str(variant.get("_silhouette_lock") or "").strip()
    return prompt + (
        "\nSTRICT SINGLETON PRODUCT RULE: Show exactly one physical instance of the referenced product in each panel where it appears; repeated depictions across panels are required. "
        "Never show one product in a hand and a second product on a table. Do not create a duplicate through mirrors, reflections, screens, or background props."
        "\nSTRICT SILHOUETTE RULE: Preserve the source's exact silhouette and proportions; never make the product taller, "
        "squatter, shorter, longer or wider than the canonical photos show. "
        + (silhouette_lock if silhouette_lock else "Match the product's own proportions from the reference photos; do not substitute a similar-looking product.")
    )


def storyboard_references(
    product_dir: Path,
    variant: dict[str, Any],
    max_references: int,
) -> list[Path]:
    if v2.active(product_dir):
        return v2.scene_references(product_dir, "storyboard", int(variant.get("variant_id", 0)))
    return existing_references(product_dir, variant, max_references=max(1, max_references))


def parse_size(size: str) -> tuple[int, int]:
    width_text, height_text = size.lower().split("x", 1)
    return int(width_text), int(height_text)


def normalize_storyboard_canvas(destination: Path, spec: dict[str, Any]) -> None:
    """Convert a provider canvas to the mathematical board without stretching cells.

    A six-panel provider result may arrive as 9:21. Crop its width to 3:8,
    then resize to the exact 1080x2880 board. Since the 2 columns are not
    rescaled independently, each resulting cell remains 9:16.
    """
    from PIL import Image

    target_width, target_height = parse_size(spec["size"])
    source = Image.open(destination).convert("RGB")
    source_width, source_height = source.size
    target_ratio = target_width / target_height
    source_ratio = source_width / source_height
    if source_ratio < target_ratio:
        crop_height = max(1, round(source_width / target_ratio))
        top = max(0, (source_height - crop_height) // 2)
        source = source.crop((0, top, source_width, top + crop_height))
    elif source_ratio > target_ratio:
        crop_width = max(1, round(source_height * target_ratio))
        left = max(0, (source_width - crop_width) // 2)
        source = source.crop((left, 0, left + crop_width, source_height))
    if source.size != (target_width, target_height):
        source = source.resize((target_width, target_height), Image.Resampling.LANCZOS)
    source.save(destination, format="PNG")


def compose_exact_pad_image(reference: Path, destination: Path, size: str) -> Path:
    from PIL import Image, ImageFilter

    output_width, output_height = parse_size(size if size and size != "auto" else "1080x1920")
    source = Image.open(reference).convert("RGB")
    destination.parent.mkdir(parents=True, exist_ok=True)

    canvas = Image.new("RGB", (output_width, output_height), (246, 244, 240))
    background = source.copy()
    background.thumbnail((output_width * 2, output_height * 2))
    scale = max(output_width / background.width, output_height / background.height)
    background = background.resize((int(background.width * scale), int(background.height * scale)))
    left = (background.width - output_width) // 2
    top = (background.height - output_height) // 2
    background = background.crop((left, top, left + output_width, top + output_height)).filter(ImageFilter.GaussianBlur(18))
    overlay = Image.new("RGB", (output_width, output_height), (255, 255, 255))
    canvas = Image.blend(background, overlay, 0.72)

    product = source.copy()
    product.thumbnail((int(output_width * 0.92), int(output_height * 0.72)))
    x = (output_width - product.width) // 2
    y = int(output_height * 0.16)
    canvas.paste(product, (x, y))
    canvas.save(destination, "PNG")
    return destination


def summarize_image_response(response: dict[str, Any]) -> dict[str, Any]:
    summarized = dict(response)
    if isinstance(summarized.get("data"), list):
        summarized["data"] = []
        for item in response.get("data", []):
            if not isinstance(item, dict):
                summarized["data"].append(item)
                continue
            clean_item = dict(item)
            if "b64_json" in clean_item:
                clean_item["b64_json"] = f"[omitted {len(str(item.get('b64_json', '')))} chars]"
            summarized["data"].append(clean_item)
    return summarized


def generate_image_file(
    api_key: str,
    product_dir: Path,
    variant: dict[str, Any],
    args: argparse.Namespace,
    destination: Path,
    prompt: str,
    reference_override: list[Path] | None = None,
) -> dict[str, Any]:
    variant_id = int(variant.get("variant_id", 0))
    references = reference_override or existing_references(product_dir, variant, max_references=max(1, args.max_reference_images))
    reference = references[0] if references else None
    scene_v2 = v2.active(product_dir) and destination.parent.name == "generated_images"
    storyboard_v2 = scene_v2 and destination.name.endswith("-storyboard.png")
    provenance = destination.with_suffix(".provenance.json")
    if scene_v2:
        if args.compose_only:
            raise RuntimeError("v2 usage scenes require model-generated frames")
        prompt += "\n" + v2.guidance(product_dir)
        if storyboard_v2:
            prompt += (
                "\nOutput ONE chronological storyboard sheet following the specified board canvas and per-panel ratios. "
                "Use only hairline-thin neutral separators between edge-to-edge panels. Do not add panel numbers, labels, "
                "captions, title bands, outer frames or large blank gutters; no panel may contain legible text."
            )
        else:
            prompt += "\nOutput ONE undivided vertical 9:16 scene photograph. Never reproduce reference panel borders, labels or layout."
        if destination.name.endswith("-end.png"):
            prompt += "\nImage 1 is the generated start scene: person/room continuity only. Image 2 is the REAL canonical product; later images are secondary guidance."
        else:
            prompt += "\nImage 1 is the REAL canonical product; later images are secondary guidance."
        expected = {
            "references": v2.hashes(product_dir, references),
            "prompt": prompt,
            "image_provider": args.image_provider,
            "image_base_url": args.image_base_url,
        }
        if storyboard_v2:
            timeline = variant["storyboard_10s"]
            expected["type"] = "chronological_storyboard"
            expected["grid_spec"] = storyboard_spec(variant)
            expected["image_size"] = args.size
            expected["image_aspect_ratio"] = str(
                getattr(args, "storyboard_target_aspect_ratio", resolve_image_aspect_ratio(args))
            )
            expected["provider_aspect_ratio"] = resolve_image_aspect_ratio(args)
            expected["timeline_sha256"] = hashlib.sha256(
                json.dumps(timeline, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        if destination.exists() and not args.force:
            previous = load_json(provenance, {})
            if any(previous.get(k) != value for k, value in expected.items()) or previous.get("sha256") != v2.digest(destination):
                raise RuntimeError(f"Stale or v1 frame {destination.name}; regenerate with --force for the v2 chain")
    if destination.exists() and not args.force:
        return {
            "variant_id": variant_id,
            "status": "skipped_existing",
            "reference_image": str(reference.relative_to(product_dir)) if reference else None,
            "reference_images": [str(item.relative_to(product_dir)) for item in references],
            "output_path": str(destination.relative_to(product_dir)),
            "prompt": prompt,
        }
    if args.compose_only:
        if not reference:
            raise RuntimeError(f"No reference image found for {product_dir} variant {variant_id}")
        saved_path = compose_exact_pad_image(reference, destination, args.size)
        return {
            "variant_id": variant_id,
            "status": "composed_exact_reference",
            "reference_image": str(reference.relative_to(product_dir)),
            "reference_images": [str(reference.relative_to(product_dir))],
            "output_path": str(saved_path.relative_to(product_dir)),
            "prompt": prompt,
            "composition_policy": "No AI redraw: original product image resized onto 9:16 pad to prevent product drift.",
        }
    provider = args.image_provider
    provider_chain = [provider]
    fallback = args.image_fallback
    if fallback and fallback != "none" and fallback != provider:
        provider_chain.append(fallback)
    response: dict[str, Any] = {}
    saved_path: Path | None = None
    provider_errors: list[str] = []
    used_provider = provider
    task_key = api_key if api_key and api_key != "local-compose" else require_api_key_for_base_url(args.image_base_url)
    for attempt_provider in provider_chain:
        try:
            if not is_media_image_provider(attempt_provider):
                raise RuntimeError(f"Unsupported image provider {attempt_provider}")
            status, saved_path = generate_image_via_media_task(
                task_key, args, prompt, references, destination, attempt_provider
            )
            response = {"provider": attempt_provider, "task": status}
            used_provider = attempt_provider
            break
        except Exception as error:
            provider_errors.append(f"{attempt_provider}: {error}")
            if attempt_provider is provider_chain[-1]:
                raise RuntimeError(
                    f"Image generation failed on every provider for variant {variant_id:02d}: "
                    + " | ".join(provider_errors)
                ) from error
            print(f"[provider] {attempt_provider} failed for variant {variant_id:02d}; falling back: {error}", flush=True)
    if scene_v2:
        if not saved_path:
            raise RuntimeError("Image route did not return a saved scene frame")
        if storyboard_v2:
            normalize_storyboard_canvas(destination, storyboard_spec(variant))
        write_json(provenance, {**expected, "sha256": v2.digest(destination)})
    return {
        "variant_id": variant_id,
        "status": "saved" if saved_path else "response_without_saved_image",
        "reference_image": str(reference.relative_to(product_dir)) if reference else None,
        "reference_images": [str(item.relative_to(product_dir)) for item in references],
        "output_path": str(destination.relative_to(product_dir)) if saved_path else None,
        "prompt": prompt,
        "image_provider": used_provider,
        "provider_fallbacks": provider_errors,
        "response": summarize_image_response(response),
    }


def generate_one_image(
    api_key: str,
    product_dir: Path,
    variant: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    product_name = (load_json(product_dir / "product_manifest.json", {}) or {}).get("product_name", product_dir.name)
    variant_id = int(variant.get("variant_id", 0))
    if args.storyboards:
        spec = storyboard_spec(variant)
        args = argparse.Namespace(**vars(args))
        requested = getattr(args, "image_aspect_ratio", "auto")
        if requested not in ("auto", spec["boardLayoutRatio"]):
            raise RuntimeError("Image aspect ratio conflicts with storyboard grid geometry")
        args.size = spec["size"]
        # The storyboard sheet must use its mathematical grid ratio. For six
        # portrait 9:16 cells in a 2x3 layout this is 3:8; never substitute the final video
        # ratio 9:16, which stretches the six-panel sheet.
        # upDrama's aspect enum has no 3:8 entry. 9:21 is the nearest
        # supported transport ratio to the mathematical six-panel board ratio
        # 3:8; the storyboard prompt still preserves the per-panel 9:16 rule.
        args.image_aspect_ratio = "9:21" if spec["panel_count"] == 6 else "9:16"
        args.storyboard_target_aspect_ratio = spec["boardLayoutRatio"]
        destination = product_dir / "generated_images" / f"variant-{variant_id:02d}-storyboard.png"
        prompt = build_storyboard_prompt(variant, product_name)
        references = storyboard_references(product_dir, variant, max(1, args.max_reference_images))
        result = generate_image_file(
            api_key, product_dir, variant, args, destination, prompt, reference_override=references
        )
        result["frame_role"] = "storyboard"
        result["generation_strategy"] = "chronological_omni_reference_storyboard"
        return result
    prompt = build_image_prompt(variant, product_name)
    destination = product_dir / "generated_images" / f"variant-{variant_id:02d}.png"
    return generate_image_file(api_key, product_dir, variant, args, destination, prompt)


def process_product(product_dir: Path, api_key: str, selected_variants: set[int], args: argparse.Namespace) -> None:
    prompts_path = resolve_prompts_path(product_dir, args.prompts_file)
    prompts = load_json(prompts_path)
    if not prompts:
        print(f"[skip] missing prompts file: {prompts_path}")
        return
    results: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    for variant in prompts.get("variants", []):
        variant_id = int(variant.get("variant_id", 0))
        if variant_id not in selected_variants:
            continue
        current_variant = dict(variant)
        current_variant["_physical_scale_lock"] = prompts.get("physical_scale_lock", "")
        current_variant["_silhouette_lock"] = prompts.get("silhouette_lock", "")
        targets.append(current_variant)

    results_path = product_dir / "generated_images" / "image_generation_results.json"
    if not targets:
        write_json(results_path, {"results": results})
        return

    def run_one(current_variant: dict[str, Any]) -> dict[str, Any]:
        variant_id = int(current_variant.get("variant_id", 0))
        print(f"[image] {product_dir.name} variant {variant_id:02d}", flush=True)
        return generate_one_image(api_key, product_dir, current_variant, args)

    def persist() -> None:
        # Write after every completion so a later crash cannot lose finished frames.
        ordered = sorted(results, key=lambda item: int(item.get("variant_id", 0) or 0))
        write_json(results_path, {"results": ordered})

    workers = max(1, min(int(getattr(args, "workers", 1) or 1), len(targets)))
    if workers == 1:
        for current_variant in targets:
            variant_id = int(current_variant.get("variant_id", 0))
            try:
                results.append(run_one(current_variant))
            except Exception as exc:
                print(f"[image] variant {variant_id:02d} failed: {exc}", flush=True)
                results.append({"variant_id": variant_id, "status": "error",
                                "error": f"{type(exc).__name__}: {exc}"})
            persist()
        return

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(run_one, current_variant): current_variant for current_variant in targets}
        for future in as_completed(future_map):
            current_variant = future_map[future]
            variant_id = int(current_variant.get("variant_id", 0))
            try:
                # One bad frame must not discard the whole batch or wedge the run.
                results.append(future.result())
            except Exception as exc:
                print(f"[image] variant {variant_id:02d} failed: {exc}", flush=True)
                results.append({"variant_id": variant_id, "status": "error",
                                "error": f"{type(exc).__name__}: {exc}"})
            persist()
    persist()


def add_image_provider_arguments(parser: argparse.ArgumentParser) -> None:
    """Shared image-route flags so every script sends the same provider chain."""
    parser.add_argument(
        "--image-provider",
        default=MEDIA_IMAGE_PROVIDER,
        choices=list(IMAGE_PROVIDERS),
        help="Production image route. Defaults to the upDrama media-task model tt-image-2.5.",
    )
    parser.add_argument(
        "--image-fallback",
        default=MEDIA_IMAGE_PROVIDER_ALT,
        choices=[MEDIA_IMAGE_PROVIDER_ALT, "none"],
        help="Media-task model used when the primary image provider fails. Defaults to tt-image-2.",
    )
    parser.add_argument("--image-base-url", default=LK888_BASE_URL, help="Base URL for the upDrama media-task image route.")
    parser.add_argument("--image-aspect-ratio", default="auto", help="Aspect ratio for the media-task image route. 'auto' derives it from the canvas. Storyboards derive the canvas from panel count and target frame ratio.")
    parser.add_argument("--image-resolution", default="2K", choices=["auto", "1K", "2K", "4K"], help="Resolution tier for the media-task image route.")
    parser.add_argument("--image-version", default="sunburst", choices=["flare", "sunburst"], help="tt-image-2.5 quality tier: flare (standard) or sunburst (enhanced).")
    parser.add_argument("--image-quality", default="high", choices=["auto", "low", "medium", "high", "xhigh", "max"], help="Render quality tier for the media-task image route.")
    parser.add_argument("--image-background", default="opaque", choices=["opaque", "transparent", "auto"], help="Background mode for the media-task image route.")
    parser.add_argument("--image-poll-seconds", type=int, default=4, help="Polling interval for media-task image jobs.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate product-faithful Omni storyboard references or optional still images from UGC prompts.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--variants", default="1-10")
    parser.add_argument("--prompts-file", default="ugc_prompts.json")
    add_image_provider_arguments(parser)
    parser.add_argument("--size", default="1080x1920", help="Still-image canvas; storyboards derive their size from grid geometry and ignore this setting.")
    parser.add_argument("--products", default="", help="Comma-separated product selectors, e.g. 01 or 01-flower")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--compose-only", action="store_true", help="Create deterministic 9:16 pad images from the original reference without AI redraw.")
    parser.add_argument("--storyboards", action="store_true", help="Generate the canonical Omni reference storyboard named variant-XX-storyboard.png.")
    parser.add_argument("--max-reference-images", type=int, default=1, help="Maximum selected reference images to send to image edit requests.")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent image workers. Results are written after each frame so a slow or failing frame cannot wedge the batch.")
    args = parser.parse_args()
    selected_variants = parse_variants(args.variants)
    api_key = "local-compose" if args.compose_only else require_api_key_for_base_url(args.image_base_url)
    for product_dir in v2.products(args.output_dir, args.products):
        process_product(product_dir, api_key, selected_variants, args)


if __name__ == "__main__":
    main()

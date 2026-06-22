#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import load_json, multipart_request, request_json, require_api_key_for_base_url, save_response_image, selected_product_dirs, write_json


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


def should_include_size(model: str, size: str | None) -> bool:
    if not size:
        return False
    return model in {"gpt-image-2-vip", "gpt-image-2"} and size != "none"


def first_existing_reference(product_dir: Path, variant: dict[str, Any]) -> Path | None:
    references = existing_references(product_dir, variant, max_references=1)
    return references[0] if references else None


def existing_references(product_dir: Path, variant: dict[str, Any], max_references: int = 1) -> list[Path]:
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
    return (
        variant.get("image_prompt")
        or f"Create a vertical short-form ecommerce UGC product pad image for {product_name}. Preserve the referenced product exactly. No social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, no watermarks."
    )


def build_keyframe_prompt(variant: dict[str, Any], product_name: str, frame_role: str) -> str:
    prompt_key = "start_frame_prompt" if frame_role == "start" else "end_frame_prompt"
    fallback_role = "start" if frame_role == "start" else "final"
    return (
        variant.get(prompt_key)
        or variant.get("image_prompt")
        or f"Create a single vertical 9:16 short-form ecommerce UGC {fallback_role} keyframe photo for {product_name}. For END frames: use the start-frame reference for room/lighting/person/product continuity ONLY, create a VISIBLY DIFFERENT final moment. Preserve the referenced product exactly. Output exactly one undivided photograph. No multi-panel layouts, no split-screens, no before-after comparisons, no contact sheets, no product grids, no collages, no storyboard frames, no 2-up/3-up/4-up arrangements. No on-image text labels, captions, callouts, arrows, or graphic overlays. No social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, no watermarks."
    )


def keyframe_references(
    product_dir: Path,
    variant: dict[str, Any],
    frame_role: str,
    max_references: int,
) -> list[Path]:
    base_references = existing_references(product_dir, variant, max_references=max(1, max_references))
    if frame_role == "end":
        # Do NOT pass the start frame as a reference image for the end keyframe.
        # The start frame biases Image2 toward copying the composition instead of advancing the scene.
        # End frame should only lock the product identity from canonical product references.
        return base_references
    return base_references


def parse_size(size: str) -> tuple[int, int]:
    width_text, height_text = size.lower().split("x", 1)
    return int(width_text), int(height_text)


def compose_exact_pad_image(reference: Path, destination: Path, size: str) -> Path:
    from PIL import Image, ImageFilter

    output_width, output_height = parse_size(size if size and size != "auto" else "1024x1536")
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
    if reference:
        fields = {"model": args.model, "prompt": prompt}
        if should_include_size(args.model, args.size):
            fields["size"] = args.size
        if args.quality and args.model == "gpt-image-2":
            fields["quality"] = args.quality
        response = None
        last_error = None
        for attempt in range(1, args.retries + 1):
            try:
                response = multipart_request(
                    "/images/edits",
                    api_key,
                    fields=fields,
                    files=[("image", item) for item in references],
                    base_url=args.base_url,
                    timeout=args.timeout,
                )
                break
            except (TimeoutError, RuntimeError) as error:
                last_error = error
                transient = any(
                    marker in str(error)
                    for marker in (
                        "UNEXPECTED_EOF",
                        "urlopen error",
                        "timed out",
                        "Connection reset",
                        "Max retries exceeded",
                        "HTTP 502",
                        "HTTP 503",
                        "internal_server_error",
                        "Bad Gateway",
                        "Service Unavailable",
                    )
                )
                if not transient or attempt == args.retries:
                    raise
                print(f"[retry] image edit variant {variant_id:02d} attempt {attempt}/{args.retries} transient error: {error}", flush=True)
        if response is None:
            raise last_error or RuntimeError("image edit failed without response")
    else:
        payload: dict[str, Any] = {"model": args.model, "prompt": prompt}
        if should_include_size(args.model, args.size):
            payload["size"] = args.size
        if args.quality and args.model == "gpt-image-2":
            payload["quality"] = args.quality
        response = request_json("/images/generations", api_key, payload, base_url=args.base_url, timeout=args.timeout)
    saved_path = save_response_image(response, destination)
    return {
        "variant_id": variant_id,
        "status": "saved" if saved_path else "response_without_saved_image",
        "reference_image": str(reference.relative_to(product_dir)) if reference else None,
        "reference_images": [str(item.relative_to(product_dir)) for item in references],
        "output_path": str(destination.relative_to(product_dir)) if saved_path else None,
        "prompt": prompt,
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
    if args.keyframes:
        if args.compose_only and not args.allow_compose_keyframes:
            raise RuntimeError(
                f"{product_dir.name} variant {variant_id:02d}: --compose-only is not allowed for functional start/end keyframes. "
                "Use Image2/model-generated keyframes so the first frame can show the pre-use scene and the end frame can show the real usage outcome. "
                "Only pass --allow-compose-keyframes for explicit stable b-roll, not product-use videos."
            )
        results: list[dict[str, Any]] = []
        for frame_role in ("start", "end"):
            destination = product_dir / "generated_images" / f"variant-{variant_id:02d}-{frame_role}.png"
            prompt = build_keyframe_prompt(variant, product_name, frame_role)
            references = keyframe_references(product_dir, variant, frame_role, max(1, args.max_reference_images))
            frame_result = generate_image_file(api_key, product_dir, variant, args, destination, prompt, reference_override=references)
            frame_result["frame_role"] = frame_role
            frame_result["generation_strategy"] = "end_frame_chained_from_start" if frame_role == "end" and references and references[0].name.endswith("-start.png") else "direct_from_product_references"
            results.append(frame_result)
        return {
            "variant_id": variant_id,
            "status": "keyframes_generated",
            "keyframes": results,
        }
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
    for variant in prompts.get("variants", []):
        variant_id = int(variant.get("variant_id", 0))
        if variant_id not in selected_variants:
            continue
        print(f"[image] {product_dir.name} variant {variant_id:02d}")
        results.append(generate_one_image(api_key, product_dir, variant, args))
    write_json(product_dir / "generated_images" / "image_generation_results.json", {"results": results})


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate GPT-Image-2 product-faithful pad images from UGC prompts.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--variants", default="1-10")
    parser.add_argument("--prompts-file", default="ugc_prompts.json")
    parser.add_argument("--model", default="gpt-image-2-vip")
    parser.add_argument("--size", default="1024x1536")
    parser.add_argument("--quality", default="")
    parser.add_argument("--base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument("--products", default="", help="Comma-separated product selectors, e.g. 01 or 01-flower")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--compose-only", action="store_true", help="Create deterministic 9:16 pad images from the original reference without AI redraw.")
    parser.add_argument("--allow-compose-keyframes", action="store_true", help="Explicitly permit compose-only start/end keyframes for stable b-roll only; never use for functional usage demos.")
    parser.add_argument("--keyframes", action="store_true", help="Generate start/end keyframe images named variant-XX-start.png and variant-XX-end.png.")
    parser.add_argument("--max-reference-images", type=int, default=1, help="Maximum selected reference images to send to image edit requests.")
    args = parser.parse_args()
    selected_variants = parse_variants(args.variants)
    api_key = "local-compose" if args.compose_only else require_api_key_for_base_url(args.base_url)
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        process_product(product_dir, api_key, selected_variants, args)


if __name__ == "__main__":
    main()

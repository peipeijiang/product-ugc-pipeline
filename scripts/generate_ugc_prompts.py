#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import load_json, request_json, require_api_key, selected_product_dirs, write_json


UGC_SYSTEM_PROMPT = """You are a senior UGC creative director for short-form social video and TikTok Shop.
Create product-faithful creator ad prompts. Return JSON only."""

VOICEOVER_SEGMENTS = [("0-2s", 8), ("2-5s", 10), ("5-8s", 10)]


def discover_history_files(product_dir: Path, history_glob: str) -> list[Path]:
    files = [path for path in sorted(product_dir.glob(history_glob)) if path.is_file()]
    return [path for path in files if ".dry_run." not in path.name and not path.name.endswith(".dry_run.json")]


def _variant_text(variant: dict[str, Any]) -> str:
    parts = [
        variant.get("title", ""),
        variant.get("primary_function_focus", ""),
        variant.get("hook", ""),
        variant.get("selling_angle", ""),
        variant.get("scene_imagination", ""),
        variant.get("usage_logic", ""),
        variant.get("proof_moment", ""),
        variant.get("dialogue_script", ""),
        variant.get("video_prompt", ""),
    ]
    flattened: list[str] = []
    for part in parts:
        if isinstance(part, list):
            flattened.extend(str(item) for item in part)
        else:
            flattened.append(str(part))
    return " ".join(item for item in flattened if item).lower()


def _match_tag(text: str, rules: list[tuple[str, list[str]]], fallback: str) -> str:
    for tag, markers in rules:
        if any(marker in text for marker in markers):
            return tag
    return fallback


def infer_scene_tag(variant: dict[str, Any]) -> str:
    text = _variant_text(variant)
    return _match_tag(
        text,
        [
            ("kitchen", ["kitchen", "counter", "pasta", "salad", "bowl", "food prep"]),
            ("outdoor", ["patio", "garden", "yard", "outdoor", "porch", "tree"]),
            ("car", ["car", "dashboard", "console", "vehicle"]),
            ("desk", ["desk", "office", "laptop", "workspace"]),
            ("bedroom", ["bedroom", "bed", "sleep", "pillow", "nightstand"]),
            ("party", ["party", "birthday", "balloon", "celebration"]),
            ("pet-grooming", ["pet", "paw", "groom", "nail", "dog", "cat"]),
            ("home-electric", ["outlet", "appliance", "living room", "electricity", "wall socket"]),
            ("travel", ["travel", "hotel", "portable", "vacation"]),
        ],
        "general-home",
    )


def infer_action_tag(variant: dict[str, Any]) -> str:
    text = _variant_text(variant)
    return _match_tag(
        text,
        [
            ("setup", ["set up", "setup", "plug in", "mount", "hang", "insert", "load", "attach"]),
            ("demo-use", ["grate", "slice", "spin", "inflate", "trim", "grind", "sleep", "cool", "file"]),
            ("refill", ["refill", "tablet", "bait", "charge", "charging"]),
            ("swap", ["swap", "change drum", "interchangeable", "replace blade"]),
            ("cleanup", ["clean", "brush", "rinse", "wash"]),
            ("proof-shot", ["proof", "result", "final shot", "finish"]),
        ],
        "usage-demo",
    )


def infer_angle_tag(variant: dict[str, Any]) -> str:
    text = _variant_text(variant)
    return _match_tag(
        text,
        [
            ("speed", ["fast", "quick", "speed", "seconds"]),
            ("stability", ["stable", "stability", "locks", "suction"]),
            ("safety", ["safe", "safely", "guard", "led", "visibility"]),
            ("comfort", ["comfort", "aligned", "support", "relaxed"]),
            ("portability", ["portable", "travel", "compact"]),
            ("cleanliness", ["clean", "mess", "tidy", "deodorizer", "fresh"]),
            ("capacity", ["large bowl", "5.3 qt", "dual nozzle", "100-speed"]),
        ],
        "core-function",
    )


def infer_style_tag(variant: dict[str, Any]) -> str:
    text = _variant_text(variant)
    return _match_tag(
        text,
        [
            ("asmr", ["asmr", "silent", "sound-only"]),
            ("creator-talk", ["creator", "voiceover", "dialogue", "host"]),
            ("proof-first", ["proof moment", "finish shot", "result shot"]),
            ("setup-demo", ["setup", "install", "mount", "plug in"]),
            ("lifestyle-demo", ["lifestyle", "routine", "bedroom", "office", "party"]),
        ],
        "function-demo",
    )


def infer_pace_tag(variant: dict[str, Any]) -> str:
    text = _variant_text(variant)
    return _match_tag(
        text,
        [
            ("fast", ["fast", "quick", "speed", "rapid"]),
            ("slow", ["asmr", "gentle", "calm", "soft", "slow"]),
        ],
        "medium",
    )


def _clean_spoken_text(text: str) -> str:
    cleaned = re.sub(r"[\[\]\{\}\"“”]", " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
    return cleaned


def _trim_to_words(text: str, max_words: int) -> str:
    words = _clean_spoken_text(text).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(" ,.-")


def normalize_voiceover_script_8s(raw_voiceover: Any, hook: str = "", fallback: str = "") -> list[dict[str, str]]:
    collected: list[str] = []
    if isinstance(raw_voiceover, dict):
        for time_slot, _ in VOICEOVER_SEGMENTS:
            text = str(raw_voiceover.get(time_slot) or "").strip()
            if text:
                collected.append(text)
    elif isinstance(raw_voiceover, list):
        for item in raw_voiceover:
            if isinstance(item, dict):
                text = str(item.get("line") or item.get("text") or "").strip()
            else:
                text = str(item).strip()
            if text:
                collected.append(text)
    elif isinstance(raw_voiceover, str) and raw_voiceover.strip():
        collected = [part.strip() for part in re.split(r"(?<=[.!?])\s+", raw_voiceover.strip()) if part.strip()]
    fallback_lines = [
        hook or "Here is the quick demo.",
        fallback or "Watch the core function in one clean action.",
        "You get the proof shot before the clip ends.",
    ]
    normalized: list[dict[str, str]] = []
    for index, (time_slot, max_words) in enumerate(VOICEOVER_SEGMENTS):
        source = collected[index] if index < len(collected) else fallback_lines[index]
        line = _trim_to_words(source, max_words)
        if not line:
            line = _trim_to_words(fallback_lines[index], max_words)
        normalized.append({"time": time_slot, "line": line})
    total_words = sum(len(item["line"].split()) for item in normalized)
    if total_words > 28:
        overflow = total_words - 28
        for item in reversed(normalized):
            words = item["line"].split()
            removable = max(0, len(words) - 4)
            if removable <= 0:
                continue
            cut = min(removable, overflow)
            item["line"] = " ".join(words[:-cut]).rstrip(" ,.-")
            overflow -= cut
            if overflow <= 0:
                break
    return normalized


def compact_voiceover_text(raw_voiceover: Any) -> str:
    normalized = normalize_voiceover_script_8s(raw_voiceover)
    return " ".join(item["line"] for item in normalized if item.get("line")).strip()


def summarize_variant_history(variant: dict[str, Any], source_file: str) -> dict[str, Any]:
    return {
        "source_file": source_file,
        "variant_id": variant.get("variant_id"),
        "title": variant.get("title", ""),
        "primary_function_focus": variant.get("primary_function_focus", ""),
        "hook": variant.get("hook", ""),
        "selling_angle": variant.get("selling_angle", ""),
        "scene_imagination": variant.get("scene_imagination", ""),
        "usage_logic": variant.get("usage_logic", ""),
        "proof_moment": variant.get("proof_moment", ""),
        "dialogue_script": variant.get("dialogue_script", ""),
    }


def collect_existing_variant_history(product_dir: Path, history_glob: str) -> tuple[list[dict[str, Any]], list[str]]:
    history: list[dict[str, Any]] = []
    files = discover_history_files(product_dir, history_glob)
    for path in files:
        data = load_json(path, {})
        for variant in data.get("variants", []) if isinstance(data, dict) else []:
            if isinstance(variant, dict):
                history.append(summarize_variant_history(variant, path.name))
    return history, [path.name for path in files]


def history_summary_for_prompt(history: list[dict[str, Any]], limit: int = 24) -> str:
    if not history:
        return "No historical prompt variants found for this product."
    return json.dumps(history[:limit], ensure_ascii=False, indent=2)


def parse_json_text(text: str, context: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise RuntimeError(f"{context}: empty model content")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{context}: invalid JSON: {stripped[:800]}") from error


def _brief_paths(product_brief: dict[str, Any], keys: list[str]) -> list[str]:
    paths: list[str] = []
    for key in keys:
        value = product_brief.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    paths.append(item)
                elif isinstance(item, dict):
                    for path in item.get("local_paths") or item.get("paths") or []:
                        if isinstance(path, str):
                            paths.append(path)
    return paths


def best_reference_images(image_analysis: dict[str, Any], product_brief: dict[str, Any] | None = None, limit: int = 3) -> list[str]:
    brief = product_brief or {}
    rejected = set(
        _brief_paths(
            brief,
            [
                "rejected_reference_images",
                "alternate_sku_reference_images",
                "non_canonical_reference_images",
                "avoid_reference_images",
            ],
        )
    )
    prioritized = _brief_paths(
        brief,
        [
            "canonical_reference_images",
            "full_product_reference_images",
            "reference_image_strategy",
        ],
    )
    selected: list[str] = []
    for local_path in prioritized:
        if local_path not in rejected and local_path not in selected:
            selected.append(local_path)
        if len(selected) >= limit:
            return selected
    scored: list[tuple[int, int, str]] = []
    image_items = image_analysis.get("product_related_images") or image_analysis.get("images", [])
    for order, item in enumerate(image_items):
        analysis = item.get("analysis") or {}
        quality = item.get("quality") or {}
        if quality.get("usable_product_material") is False:
            continue
        if analysis.get("is_product_related") is False:
            continue
        score_value = analysis.get("ugc_usefulness_score", 0)
        try:
            score = int(score_value)
        except (TypeError, ValueError):
            score = 0
        best_use = analysis.get("best_use", "")
        reference_role = analysis.get("reference_role", "")
        visibility = analysis.get("full_product_visibility", "")
        bonus = 3 if best_use == "hero_reference" else 2 if best_use == "detail_reference" else 0
        if reference_role == "canonical_full_product":
            bonus += 5
        elif reference_role == "detail_closeup":
            bonus += 2
        if visibility == "full_product":
            bonus += 4
        local_path = item["local_path"]
        if local_path in rejected or local_path in selected:
            continue
        scored.append((score + bonus, -order, local_path))
    for _, _, local_path in sorted(scored, reverse=True):
        selected.append(local_path)
        if len(selected) >= limit:
            break
    return selected


def normalize_variants(output: dict[str, Any], manifest: dict[str, Any], references: list[str], count: int, product_brief: dict[str, Any] | None = None) -> dict[str, Any]:
    product_name = manifest["product_name"]
    feature_summary = product_function_summary(manifest, product_brief)
    variants = output.get("variants")
    if not isinstance(variants, list):
        raise RuntimeError(f"Model output missing variants array for {product_name}")
    if len(variants) < count:
        raise RuntimeError(f"Model returned only {len(variants)} variants for {product_name}; expected {count}")
    normalized: list[dict[str, Any]] = []
    start_variant_id = int(output.get("start_variant_id") or 1)
    for index, variant in enumerate(variants[:count], start=start_variant_id):
        if not isinstance(variant, dict):
            raise RuntimeError(f"Variant {index} for {product_name} was not a JSON object")
        clean_variant = dict(variant)
        clean_variant["variant_id"] = index
        clean_variant["selected_reference_images"] = references[:2]
        clean_variant.setdefault("reference_scope", reference_scope_note(references))
        clean_variant.setdefault("scene_imagination", build_scene_imagination(clean_variant, product_brief))
        clean_variant.setdefault("selling_angle", infer_selling_angle(clean_variant, feature_summary))
        clean_variant.setdefault("negative_prompt", "Do not alter product geometry, color, material, logo/text, silhouette, or invent extra parts.")
        clean_variant.setdefault("function_intro_prompt", build_function_intro_prompt(product_name, feature_summary, clean_variant.get("hook", "")))
        clean_variant["voiceover_script_8s"] = normalize_voiceover_script_8s(
            clean_variant.get("voiceover_script_8s"),
            hook=str(clean_variant.get("hook") or ""),
            fallback=build_voiceover_script_8s(product_name, feature_summary, clean_variant.get("hook", ""))[1]["line"],
        )
        clean_variant["on_screen_callouts"] = []
        clean_variant.setdefault("function_demo_prompt", build_function_demo_prompt(product_name, feature_summary, clean_variant.get("title", "")))
        fidelity = product_fidelity_block(product_name)
        image_prompt = str(clean_variant.get("image_prompt") or "")
        video_prompt = str(clean_variant.get("video_prompt") or "")
        if "CANONICAL PRODUCT" not in image_prompt:
            image_prompt = fidelity + ("\n" + image_prompt if image_prompt else "")
        if "CANONICAL PRODUCT" not in video_prompt:
            video_prompt = fidelity + ("\n" + video_prompt if video_prompt else "")
        clean_variant["model_suggested_image_prompt"] = image_prompt
        clean_variant["model_suggested_video_prompt"] = video_prompt
        clean_variant["start_frame_prompt"] = usage_keyframe_prompt(product_name, clean_variant, product_brief, "start")
        clean_variant["end_frame_prompt"] = usage_keyframe_prompt(product_name, clean_variant, product_brief, "end")
        clean_variant["image_prompt"] = strict_pad_image_prompt(product_name, clean_variant, product_brief)
        clean_variant["video_prompt"] = usage_demo_video_prompt(clean_variant, product_brief)
        clean_variant["video_prompt_strategy"] = "usage_demo_conservative_first_frame_identity"
        normalized.append(clean_variant)
    output["product_name"] = output.get("product_name") or product_name
    output["variants"] = normalized
    output["variant_count_requested"] = count
    output["variant_count_returned_by_model"] = len(variants)
    output["variant_count_final"] = len(normalized)
    return output


def product_fidelity_block(product_name: str) -> str:
    return (
        f"CANONICAL PRODUCT: {product_name}. Use the provided product reference image as the source of truth. "
        "Preserve exact product shape, proportions, color, material, texture, visible mechanisms, logo/text, packaging, and distinctive silhouette. "
        "Do not redesign, recolor, simplify, distort, or replace the product. "
        "Do not add any feature that is not visible in the reference image: no new lid, cap, hinge, latch, transparent chamber, water tank, handle, button, blade, motor, brand text, embossed text, container body, or storage compartment unless that exact feature already exists in the reference."
    )


def reference_scope_note(references: list[str] | None = None) -> str:
    reference_text = json.dumps(references or [], ensure_ascii=False)
    return (
        f"Use selected reference images {reference_text} to lock only the product identity: exact SKU/colorway, shape, proportions, material, functional surfaces, visible mechanisms, ports, and distinctive details. "
        "Do not treat the source photo background, tabletop, props, lighting, camera angle, or composition as mandatory unless directly required to explain the product function."
    )


def infer_selling_angle(variant: dict[str, Any], feature_summary: str) -> str:
    source = " ".join(
        str(variant.get(key, ""))
        for key in ("title", "hook", "usage_logic", "proof_moment", "dialogue_script")
    ).lower()
    combined = f"{source} {feature_summary.lower()}"
    angle_map = [
        ("travel", "travel portability"),
        ("portable", "compact portability"),
        ("fold", "folding / compact storage"),
        ("storage", "storage convenience"),
        ("one hand", "one-handed convenience"),
        ("quick", "speed / quick setup"),
        ("fast", "speed / quick setup"),
        ("clean", "cleaner setup"),
        ("mess", "mess reduction"),
        ("cable", "fewer cables"),
        ("organ", "organization"),
        ("gift", "giftable everyday usefulness"),
        ("premium", "premium product feel"),
        ("close-up", "premium product detail"),
    ]
    for marker, angle in angle_map:
        if marker in combined:
            return angle
    return "clear buyer benefit tied to the confirmed product function"


def build_scene_imagination(variant: dict[str, Any], product_brief: dict[str, Any] | None = None) -> str:
    brief = product_brief or {}
    existing = str(variant.get("scene_imagination") or "").strip()
    if existing:
        return existing
    scene_context = _plain_brief_list(variant.get("shot_plan") or brief.get("recommended_ugc_scenes"), 3)
    usage_context = _plain_brief_list(variant.get("usage_logic") or brief.get("confirmed_use_cases") or brief.get("step_by_step_usage"), 3)
    angle = infer_selling_angle(variant, usage_context)
    if scene_context:
        return (
            f"Use a realistic lifestyle setting inspired by buyer use, not a copy of the product-page photo: {scene_context}. "
            f"Scene should make the '{angle}' selling angle and this usage clear: {usage_context}."
        )
    return (
        f"Invent a realistic lifestyle scene where a buyer would naturally use this product, guided by the '{angle}' selling angle and confirmed usage: {usage_context}. "
        "Do not copy the original product-photo background unless it is necessary for understanding the function."
    )


def _brief_list(value: Any, limit: int = 4) -> str:
    if isinstance(value, list):
        return "; ".join(json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item) for item in value[:limit])
    return str(value or "")


def _plain_brief_list(value: Any, limit: int = 4) -> str:
    if isinstance(value, list):
        items: list[str] = []
        for item in value[:limit]:
            if isinstance(item, dict):
                text = item.get("step") or item.get("use_case") or item.get("description") or item.get("text")
                items.append(str(text or item))
            else:
                items.append(str(item))
        return "; ".join(item for item in items if item)
    return str(value or "")


def product_function_summary(manifest: dict[str, Any], product_brief: dict[str, Any] | None = None) -> str:
    brief = product_brief or {}
    candidates = [
        brief.get("confirmed_use_cases"),
        brief.get("step_by_step_usage"),
        brief.get("function_research"),
        manifest.get("functional_understanding"),
        manifest.get("usage_signals"),
        manifest.get("selling_points"),
        manifest.get("description"),
    ]
    parts: list[str] = []
    for candidate in candidates:
        text = _plain_brief_list(candidate, 6)
        if text and text not in parts:
            parts.append(text)
    return "; ".join(parts)[:1200] or "demonstrate the confirmed product function with a clear hands-on proof moment"


def build_function_intro_prompt(product_name: str, feature_summary: str, hook: str = "") -> str:
    return (
        "Write a concise English TikTok Shop voiceover that explains the product function before the visual demo. "
        "Use a young creator / ecommerce host tone, not a silent montage. "
        f"Product: {product_name}. Hook angle: {hook}. Confirmed functions/use only: {feature_summary}. "
        "Output should be 1-2 punchy spoken sentences, 18-32 words total, with no unsupported claims, no fake specs, and no brand names unless visible in source materials."
    )


def build_voiceover_script_8s(product_name: str, feature_summary: str, hook: str = "") -> list[dict[str, str]]:
    return normalize_voiceover_script_8s(
        [
            hook or f"This is how the {product_name} works.",
            f"The key function is simple: {feature_summary[:160]}",
            "You see the proof before the eight-second clip ends.",
        ],
        hook=hook or f"This is how the {product_name} works.",
        fallback=f"The key function is simple: {feature_summary[:160]}",
    )


def build_on_screen_callouts(feature_summary: str) -> list[str]:
    words = [part.strip(" .") for part in re_split_features(feature_summary) if part.strip(" .")]
    callouts = words[:3] if words else ["Function demo", "Proof moment", "Product close-up"]
    return [callout[:34] for callout in callouts]


def build_function_demo_prompt(product_name: str, feature_summary: str, scene: str = "") -> str:
    return (
        "Create a separate editor-facing function-introduction prompt for captions/voiceover. "
        f"Product: {product_name}. Scene: {scene}. "
        f"Explain these confirmed functions in simple buyer language: {feature_summary}. "
        "Structure: hook, what it does, proof viewers should watch for, final benefit. Keep it honest and product-specific."
    )


def re_split_features(text: str) -> list[str]:
    import re

    return re.split(r";|,|\n|/|\|| and ", text)


def phone_geometry_constraints_for_prompt(text: str) -> str:
    lowered = (text or "").lower()
    has_phone = any(marker in lowered for marker in ("phone", "smartphone", "iphone", "mobile"))
    has_camera_context = any(
        marker in lowered
        for marker in (
            "camera",
            "photo",
            "selfie",
            "shutter",
            "timer",
            "record",
            "filming",
            "app screen",
            "screen preview",
            "wireless charging",
            "charging pad",
            "charger",
        )
    )
    if not (has_phone and has_camera_context):
        return ""
    return (
        "Phone geometry constraints: make the phone orientation physically possible. "
        "For selfie, timer, or remote-shutter capture, the phone screen faces the creator and the camera lens points toward the creator; "
        "the external viewer may see the phone back/side, a mirror reflection, or an over-shoulder setup, not an impossible front-camera shot with the screen facing the viewer. "
        "For app-screen or screen-preview proof, use an over-shoulder/tabletop/second-device composition so the phone screen faces the external camera while the product or hand remains visible. "
        "For wireless charging pads, keep the phone lying flat screen-up on the charger unless the actual product is visibly a stand; do not make the phone stand upright while charging."
    )


def strict_pad_image_prompt(product_name: str, variant: dict[str, Any], product_brief: dict[str, Any] | None = None) -> str:
    brief = product_brief or {}
    scene = variant.get("title") or variant.get("hook") or "UGC product demo setup"
    references = variant.get("selected_reference_images") or _brief_paths(brief, ["canonical_reference_images", "reference_image_strategy"])
    reference_scope = variant.get("reference_scope") or reference_scope_note(references)
    scene_imagination = build_scene_imagination(variant, brief)
    usage_context = _brief_list(
        variant.get("usage_logic") or brief.get("step_by_step_usage") or brief.get("confirmed_or_inferred_use_steps"),
        3,
    )
    phone_geometry = phone_geometry_constraints_for_prompt(
        " ".join(
            str(variant.get(key) or "")
            for key in ("title", "hook", "usage_logic", "proof_moment", "scene_imagination", "image_prompt")
        )
    )
    return (
        product_fidelity_block(product_name)
        + "\nCreate a vertical 9:16 first-frame pad image for a UGC video. "
        "This is a product-accurate setup shot, not a usage/action shot. Treat the reference product as a locked physical prop, not a design suggestion. "
        f"Use these selected reference images as the product identity source: {json.dumps(references, ensure_ascii=False)}. "
        f"Reference scope: {reference_scope} "
        "The first selected full-product reference is the canonical source of truth. If page images conflict, ignore alternate SKUs, accessories, loose parts, packaging-only photos, and detail-only photos. "
        "Keep the full product visually identical to the reference image, with unobstructed silhouette and visible surface details. "
        f"Scene imagination: {scene_imagination} "
        "You may add realistic lifestyle background and nearby contextual props that support the buyer use case, but do not copy source-photo props by default and do not let props obscure or redesign the product. "
        "The product must not touch, scrub, squeeze, cut, open, press, wash, or interact with any object in this pad image unless that action is the selected supported function for this exact variant. "
        "Do not place the product inside a hand if that hides or deforms the shape. Do not crop the product. "
        "No invented text or branding on the product. No extra plastic shell, chamber, lid, latch, reservoir, or mechanical housing. "
        f"{phone_geometry} "
        f"Scene concept: {scene}. Usage context for the later video only, not for this image: {usage_context}."
    )


def image_led_video_prompt(variant: dict[str, Any]) -> str:
    try:
        variant_id = int(variant.get("variant_id", 1))
    except (TypeError, ValueError):
        variant_id = 1
    camera_motions = [
        "a very slow push-in with tiny handheld parallax",
        "a barely perceptible left-to-right slider move",
        "a gentle right-to-left slider move",
        "a subtle locked-off shot with soft natural light drift",
        "a minimal 3D parallax move without changing object layout",
        "a very slow pull-back that keeps the original composition intact",
    ]
    camera_motion = camera_motions[(variant_id - 1) % len(camera_motions)]
    return (
        "Use the provided first frame as the complete visual source of truth. "
        "Do not reinterpret, redesign, replace, redraw, simplify, or describe a different version of any visible object. "
        "Keep every visible object's shape, color, proportions, texture, surface details, position, and silhouette consistent with the first frame for the entire video. "
        f"Animate only the existing first-frame scene using {camera_motion}, soft natural light shift, and very subtle background/environment motion if already compatible with the first frame. "
        "Do not introduce new product parts, labels, text, packaging, tools, liquids, containers, mechanisms, hands, or props unless they are already visible in the first frame. "
        "Do not perform or imply actions that can change object geometry: no scrubbing, washing, squeezing, pressing, cutting, opening, twisting, assembling, filling, pouring, bending, morphing, or close-up transformation. "
        "No scene cuts, no jump cuts, no zooming into hidden details, no heavy occlusion, no product handoff, no before/after transformation. "
        "No spoken dialogue, no captions, no subtitles, no on-screen text; this clip is a stable visual b-roll shot to be edited with separate UGC voiceover later."
    )


def usage_keyframe_prompt(
    product_name: str,
    variant: dict[str, Any],
    product_brief: dict[str, Any] | None = None,
    frame_role: str = "start",
) -> str:
    brief = product_brief or {}
    references = variant.get("selected_reference_images") or _brief_paths(brief, ["canonical_reference_images", "reference_image_strategy"])
    reference_scope = variant.get("reference_scope") or reference_scope_note(references)
    scene_imagination = build_scene_imagination(variant, brief)
    usage_context = _plain_brief_list(
        brief.get("step_by_step_usage") or brief.get("confirmed_or_inferred_use_steps") or variant.get("usage_logic"),
        2,
    )
    proof_moment = _plain_brief_list(brief.get("proof_moments") or variant.get("proof_moment"), 1)
    if frame_role == "end":
        moment = (
            "END KEYFRAME: the same product is still clearly visible after one gentle use motion; "
            "show a believable small cleaned/rinsed area or practical result, not a perfect magic transformation."
        )
        continuity = (
            "This end frame must look like the same exact person, same wardrobe, same room, same props, same lighting, "
            "and same camera setup as the start frame, only a few seconds later in the same action."
        )
    else:
        moment = (
            "START KEYFRAME: an attention-grabbing problem setup; the same product is about to be used, "
            "clearly visible beside or lightly held near the target surface."
        )
        continuity = "This start frame establishes the person, scene, wardrobe, props, and camera setup that the end frame must continue."
    scene_hint = _plain_brief_list(brief.get("recommended_ugc_scenes") or variant.get("shot_plan") or variant.get("title"), 2)
    if not scene_hint:
        scene_hint = "a realistic use environment for this exact product"
    phone_geometry = phone_geometry_constraints_for_prompt(
        " ".join(
            str(variant.get(key) or "")
            for key in (
                "title",
                "hook",
                "usage_logic",
                "proof_moment",
                "scene_imagination",
                "start_frame_prompt",
                "end_frame_prompt",
                "image_prompt",
            )
        )
    )
    return (
        product_fidelity_block(product_name)
        + "\nCreate a vertical 9:16 product-use keyframe for an 8-second UGC video. "
        f"{moment} "
        f"Use these selected reference images as the product identity source: {json.dumps(references, ensure_ascii=False)}. "
        f"Reference scope: {reference_scope} "
        "The first selected full-product reference is canonical. Do not borrow shape, color, mechanism, or accessories from alternate SKUs on the same product page. "
        "The referenced product must remain the exact same physical object, with unobstructed recognizable silhouette and surface details. "
        f"Use this product-appropriate scene rather than a generic kitchen unless the product is truly a kitchen product: {scene_hint}. "
        f"Scene imagination: {scene_imagination} "
        "The lifestyle environment may differ from the original product photo; preserve the product, not the source-photo background. "
        f"{continuity} "
        "Adult hands only if needed, natural phone-shot lighting, no text overlay, no captions, no extra branding. "
        f"{phone_geometry} "
        "Avoid extreme close-ups, heavy occlusion, dramatic stains, magic effects, or any invented product mechanism. "
        f"Supported use context: {usage_context}. Proof idea: {proof_moment}."
    )


def usage_demo_video_prompt(variant: dict[str, Any], product_brief: dict[str, Any] | None = None) -> str:
    brief = product_brief or {}
    usage_context = _plain_brief_list(
        variant.get("usage_logic") or brief.get("step_by_step_usage") or brief.get("confirmed_or_inferred_use_steps"),
        3,
    )
    proof_moment = _plain_brief_list(variant.get("proof_moment") or brief.get("proof_moments"), 2)
    scene_context = _plain_brief_list(brief.get("recommended_ugc_scenes") or variant.get("shot_plan"), 2)
    scene_imagination = build_scene_imagination(variant, brief)
    reference_scope = variant.get("reference_scope") or reference_scope_note(variant.get("selected_reference_images"))
    if not usage_context:
        usage_context = "perform one simple supported use action shown or described in the product materials"
    if not proof_moment:
        proof_moment = "end with the product clearly visible beside the practical result"
    if not scene_context:
        scene_context = "a realistic home setting where this product would naturally be used"
    raw_voiceover = variant.get("voiceover_script_8s") or []
    normalized_voiceover = normalize_voiceover_script_8s(
        raw_voiceover,
        hook=str(variant.get("hook") or ""),
        fallback=str(variant.get("dialogue_script") or variant.get("title") or ""),
    )
    voiceover_text = compact_voiceover_text(normalized_voiceover)
    timed_voiceover = " ".join(f"[{item['time']}] {item['line']}" for item in normalized_voiceover if item.get("line"))
    audio_block = (
        "Native audio: include a clear young American female ecommerce-host voiceover, energetic but natural, slightly bright and sales-friendly. "
        "The spoken script must finish naturally within 8 seconds at normal creator pace, roughly 18 to 24 English words total. "
        f"Speak these exact timed lines in order: {timed_voiceover}. "
        f"Combined exact script: \"{voiceover_text[:220]}\" "
        "Keep the voiceover synchronized to the visual function demo. Add only subtle real product handling sounds; no music, no singing."
        if voiceover_text
        else "Native audio: include subtle real product handling sounds only, no music."
    )
    phone_geometry = phone_geometry_constraints_for_prompt(
        " ".join(
            str(variant.get(key) or "")
            for key in (
                "title",
                "hook",
                "usage_logic",
                "proof_moment",
                "scene_imagination",
                "model_suggested_video_prompt",
                "video_prompt",
            )
        )
    )
    return (
        "Create an 8-second vertical UGC product-use clip using the provided reference frame or start/end keyframes. "
        "If two reference images are provided, use image 1 as the exact first frame and image 2 as the exact final frame; create only a smooth practical transition between them. "
        "The hook is visual: start with the everyday problem, need, or convenience moment already visible; then show one simple satisfying use action; end on a clear proof/sell shot. "
        f"Action arc: adult hands interact with the exact visible product and perform one supported use action: {usage_context}. "
        f"Scene context: {scene_context}. "
        f"Scene imagination: {scene_imagination}. "
        f"Reference scope: {reference_scope} "
        "Keep the same visible product identity throughout: silhouette, proportions, color, texture, and distinctive details must stay consistent while it moves. "
        "Hands may enter and use the product, but avoid covering the product for more than a brief moment. "
        "Do not invent new product parts, labels, text, packaging, containers, chambers, hinges, buttons, motors, reservoirs, or mechanisms. "
        "Avoid magic-cleaning, sudden scene changes, heavy motion blur, product morphing, or unsupported functions. "
        f"Proof moment: {proof_moment}. "
        f"{phone_geometry} "
        f"{audio_block} "
        "Natural handheld phone camera, close practical use framing. "
        "Do not let VEO render text: no on-screen words, no overlay labels, no subtitles, no sentence captions, no lower-third transcript, no karaoke-style text, no Instagram or INS icons, no TikTok icons, no app UI, no watermarks. "
        "Keep on_screen_callouts as post-production overlay metadata only."
    )


def generate_with_model(
    api_key: str,
    manifest: dict[str, Any],
    image_analysis: dict[str, Any],
    product_brief: dict[str, Any],
    references: list[str],
    existing_history: list[dict[str, Any]],
    count: int,
    model: str,
    base_url: str,
    timeout: int,
) -> dict[str, Any]:
    prompt = f"""
Create {count} distinct UGC prompt variants for short-form social / TikTok Shop product ads.

Product manifest:
{json.dumps(manifest, ensure_ascii=False)[:8000]}

Image analysis:
{json.dumps(image_analysis, ensure_ascii=False)[:12000]}

Product usage cognition brief:
{json.dumps(product_brief, ensure_ascii=False)[:12000]}

Preferred local reference images:
{json.dumps(references, ensure_ascii=False)}

Existing historical variants to avoid overlapping with:
{history_summary_for_prompt(existing_history)}

Return JSON with:
- product_name
- variants: array of {count} objects
Each variant must include:
- variant_id
- title
- primary_function_focus: the single confirmed product function this variant owns; allocate this before writing scenes so the batch does not collapse into one repeated function
- creator_persona
- hook
- dialogue_script with natural spoken lines
- function_intro_prompt: a separate prompt for generating concise spoken function explanation
- voiceover_script_8s: timed 0-2s, 2-5s, 5-8s spoken script lines that introduce and explain the function
- on_screen_callouts: 1-3 short plain-text social-style feature overlay labels for post-production only, not for VEO to render, and never app icons/logos
- function_demo_prompt: editor-facing prompt that explains the function, proof moment, and final benefit
- usage_logic: explain how the product works and why the scene is correct
- proof_moment: the exact visual action that proves the function
- shot_plan with 0-15 second timing
- selected_reference_images using local paths from the preferred list
- reference_scope: explain which visual details from source images lock product identity, and explicitly state that source-photo background/props/composition are not mandatory unless functionally necessary
- selling_angle: one focused buyer benefit for this variant
- scene_imagination: a realistic lifestyle scene derived from the product function and selling angle, not merely copied from source product photos
- image_prompt in English for GPT-Image-2 image-to-image
- video_prompt in English for VEO 3.1 image-to-video
- negative_prompt

Critical:
1. Use product_brief.step_by_step_usage / confirmed_use_cases as the source of truth for how the product is used.
2. Do not invent unsupported functions.
3. Every image_prompt and video_prompt must contain a product-fidelity block requiring exact preservation of the original product appearance.
4. The selected reference image must be the best true full-product reference: full silhouette, correct SKU/style, real proportions, visible key functional zones. Do not select alternate SKU images, accessory-only images, packaging-only images, loose parts, isolated cables, or detail images as canonical.
5. Put concise native-audio voiceover lines into VEO video_prompt, and ensure the full spoken copy can naturally finish inside 8 seconds at normal creator pace.
6. Do not ask VEO to render text. Short plain-text social-style overlay labels belong in on_screen_callouts for post-production, not inside the generated video frames. Never ask for Instagram / INS / TikTok icons, app UI, or watermarks.
7. Product reference images lock the product itself, not the entire source photo. Preserve product identity and usage mechanics, but freely imagine realistic buyer scenes, backgrounds, camera angles, and contextual props that clarify the function.
8. Each variant should focus on one small function or selling point. Vary function, scene, action, and proof moment across the batch; do not produce ten versions of the same tabletop placement.
9. Start/end keyframes should be meaningfully different enough for an 8-second action arc while preserving the same exact product.
10. Read the historical variants listed above as actual prior creative work for this product. Do not paraphrase them. Avoid reusing the same scene setup, same use action, same proof moment, same buyer context, or same selling angle unless you materially transform at least 3 of those dimensions.
11. When function overlap is unavoidable, deliberately choose a different buyer situation, a different visual hook, a different camera idea, and a different proof framing instead of repeating the same demo in new words.
12. Before writing the variants, allocate one primary_function_focus per variant from confirmed_use_cases, step_by_step_usage, and proof_moments. Do not assign the same primary function to multiple fresh variants unless the product has only one confirmed function. For multifunction wearables such as smart rings, do not default every variant to photo-taking/remote shutter; split confirmed functions across health/app checks, charging, status display, touch control, activity tracking, waterproof daily wear, or fit/detail as supported by the brief.
13. If a phone appears, make its orientation physically possible. For selfie/timer/remote-shutter demos, the phone screen faces the creator and the lens points toward the creator; the viewer sees phone back/side, mirror, or over-shoulder composition. For app-screen proof, use over-shoulder/tabletop/second-device geometry. For wireless charging, the phone lies flat screen-up on the charger unless the real product is a stand.
""".strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": UGC_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    response = request_json("/chat/completions", api_key, payload, base_url=base_url, timeout=timeout)
    content = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    return parse_json_text(content, "generate_with_model")


def process_product(product_dir: Path, api_key: str, args: argparse.Namespace) -> None:
    manifest = load_json(product_dir / "product_manifest.json")
    image_analysis = load_json(product_dir / "image_analysis.json", {"images": []})
    product_brief = load_json(product_dir / "product_brief.json", {})
    if not manifest:
        print(f"[skip] missing manifest: {product_dir}")
        return
    references = best_reference_images(image_analysis, product_brief, limit=4)
    canonical_prompt_path = product_dir / "ugc_prompts.json"
    history_glob = "ugc_prompts.json" if args.output_file == "ugc_prompts.json" and canonical_prompt_path.exists() else args.history_glob
    existing_history, history_files = collect_existing_variant_history(product_dir, history_glob) if not args.ignore_history else ([], [])
    print(f"[prompts] {product_dir.name} refs={references} history={len(existing_history)}")
    output = generate_with_model(
        api_key,
        manifest,
        image_analysis,
        product_brief,
        references,
        existing_history,
        args.count,
        args.model,
        args.base_url,
        args.timeout,
    )
    output = normalize_variants(output, manifest, references, args.count, product_brief)
    output["selected_reference_images"] = references
    output["start_variant_id"] = args.start_variant_id
    output["source_manifest"] = "product_manifest.json"
    output["source_image_analysis"] = "image_analysis.json"
    output["source_product_brief"] = "product_brief.json" if product_brief else None
    output["existing_variant_history_count"] = len(existing_history)
    output["existing_variant_history_files"] = history_files
    output["generated_at"] = datetime.now(timezone.utc).isoformat()
    output["prompt_batch_role"] = "history_aware_fresh_generation"
    output["batch_label"] = args.batch_label or Path(args.output_file).stem
    output["output_file"] = args.output_file
    output["diversity_guard"] = {
        "history_enabled": not args.ignore_history,
        "history_glob": args.history_glob,
        "model_reads_full_history": True,
        "required_difference_dimensions": ["scene", "action", "selling_angle", "proof_moment", "pace", "style", "buyer_context", "camera_idea"],
    }
    if args.output_file == "ugc_prompts.json" and canonical_prompt_path.exists():
        existing_output = load_json(canonical_prompt_path, {})
        if isinstance(existing_output, dict) and isinstance(existing_output.get("variants"), list):
            existing_variants = [variant for variant in existing_output["variants"] if isinstance(variant, dict)]
            next_variant_id = max((int(variant.get("variant_id", 0)) for variant in existing_variants), default=0) + 1
            for offset, variant in enumerate(output.get("variants", []), start=next_variant_id):
                if isinstance(variant, dict):
                    variant["variant_id"] = offset
            merged = dict(existing_output)
            merged.update({k: v for k, v in output.items() if k != "variants"})
            merged["variants"] = existing_variants + [variant for variant in output.get("variants", []) if isinstance(variant, dict)]
            merged["variant_count_final"] = len(merged["variants"])
            merged["variant_count_returned_by_model"] = len(output.get("variants", []))
            merged["variant_count_requested"] = int(existing_output.get("variant_count_requested", 0) or 0) + args.count
            prompt_history = []
            if isinstance(existing_output.get("prompt_history"), list):
                prompt_history.extend(item for item in existing_output["prompt_history"] if isinstance(item, dict))
            prompt_history.append(
                {
                    "batch_label": output.get("batch_label") or args.batch_label or "canonical-append",
                    "generated_at": output.get("generated_at"),
                    "output_file": "ugc_prompts.json",
                    "appended_variant_count": len([variant for variant in output.get("variants", []) if isinstance(variant, dict)]),
                }
            )
            merged["prompt_history"] = prompt_history
            output = merged
    output_path = canonical_prompt_path if args.output_file == "ugc_prompts.json" else product_dir / args.output_file
    write_json(output_path, output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 10 product-faithful UGC prompt variants per product.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--start-variant-id", type=int, default=1)
    parser.add_argument("--output-file", default="ugc_prompts.json")
    parser.add_argument("--batch-label", default="")
    parser.add_argument("--history-glob", default="ugc_prompts*.json")
    parser.add_argument("--ignore-history", action="store_true")
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument("--base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--products", default="", help="Comma-separated product selectors, e.g. 01 or 01-flower")
    args = parser.parse_args()
    api_key = require_api_key()
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        process_product(product_dir, api_key, args)


if __name__ == "__main__":
    main()

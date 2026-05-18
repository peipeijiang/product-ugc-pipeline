#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import load_json, request_json, require_api_key, selected_product_dirs, write_json


UGC_SYSTEM_PROMPT = """You are a senior UGC creative director for Instagram Reels and TikTok Shop.
Create product-faithful creator ad prompts. Return JSON only."""


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


def fallback_variants(manifest: dict[str, Any], references: list[str], count: int, product_brief: dict[str, Any] | None = None) -> dict[str, Any]:
    product_name = manifest["product_name"]
    selling_points = "; ".join(manifest.get("selling_points") or [manifest.get("description") or "useful daily-life product"])
    brief = product_brief or {}
    usage_steps = brief.get("step_by_step_usage") or brief.get("confirmed_or_inferred_use_steps") or manifest.get("usage_signals") or []
    usage_summary = "; ".join(json.dumps(step, ensure_ascii=False) if isinstance(step, dict) else str(step) for step in usage_steps[:4])
    if not usage_summary:
        usage_summary = "demonstrate the product cautiously using only confirmed visible functions"
    selling_angles = [
        "fast setup",
        "compact storage",
        "one-handed convenience",
        "mess reduction",
        "travel portability",
        "premium close-up proof",
        "small-space organization",
        "giftable everyday usefulness",
        "morning routine speed",
        "nightstand / end-of-day routine",
    ]
    scene_archetypes = [
        "busy weekday counter",
        "small apartment shelf or desk",
        "travel pouch on hotel table",
        "bedside routine",
        "office desk reset",
        "coffee table quick demo",
        "bathroom vanity or utility corner",
        "car/travel console only if supported",
        "gift unboxing table",
        "friend recommendation handheld shot",
    ]
    variants: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        selling_angle = selling_angles[(index - 1) % len(selling_angles)]
        scene_archetype = scene_archetypes[(index - 1) % len(scene_archetypes)]
        scene_imagination = (
            f"{scene_archetype} lifestyle context chosen to make the '{selling_angle}' benefit easy to understand; "
            "do not copy the original product-photo background unless it is functionally necessary."
        )
        variants.append(
            {
                "variant_id": index,
                "title": f"{product_name} — {selling_angle}",
                "creator_persona": "Warm, practical Instagram creator filming in a bright home kitchen.",
                "hook": f"I didn't expect this tiny {product_name} to make this task feel easier.",
                "dialogue_script": (
                    f"Creator: 'Okay, quick kitchen test. This is the {product_name}. "
                    f"What I like is: {selling_points}. The correct use is: {usage_summary}. Watch this part closely—this is the proof moment.'"
                ),
                "usage_logic": usage_summary,
                "selling_angle": selling_angle,
                "scene_imagination": scene_imagination,
                "reference_scope": reference_scope_note(references),
                "function_intro_prompt": build_function_intro_prompt(product_name, usage_summary, selling_points),
                "voiceover_script_8s": build_voiceover_script_8s(product_name, usage_summary, f"I didn't expect this tiny {product_name} to make this task feel easier."),
                "on_screen_callouts": [],
                "function_demo_prompt": build_function_demo_prompt(product_name, usage_summary, scene_imagination),
                "proof_moment": (brief.get("proof_moments") or [usage_summary])[0],
                "shot_plan": [
                    "0-2s: handheld hook with product close to camera",
                    "2-6s: show the real daily problem this product is designed for",
                    "6-11s: close-up proof moment demonstrating the confirmed usage steps",
                    "11-15s: final sell shot with product held beside the result",
                ],
                "selected_reference_images": references[:2],
                "image_prompt": product_fidelity_block(product_name)
                + f"\nCreate a vertical 9:16 UGC pad image for: {scene_imagination}. Scene must support this product usage: {usage_summary}. Natural creator energy, product clearly visible, but the lifestyle scene can differ from the source product photos.",
                "video_prompt": product_fidelity_block(product_name)
                + f"\n15-second Instagram Reels style product demo. Demonstrate these confirmed/cautious usage steps: {usage_summary}. Include natural spoken dialogue only if safe, clear proof moment, and final sell shot. Scenario: {scene_imagination}.",
                "negative_prompt": "Do not alter product geometry, color, material, logo/text, handle shape, flower/gourd/cat silhouette, or invent extra parts.",
            }
        )
    return {"product_name": product_name, "variants": variants}


def normalize_variants(output: dict[str, Any], manifest: dict[str, Any], references: list[str], count: int, product_brief: dict[str, Any] | None = None) -> dict[str, Any]:
    product_name = manifest["product_name"]
    fallback = fallback_variants(manifest, references, count, product_brief)
    feature_summary = product_function_summary(manifest, product_brief)
    variants = output.get("variants")
    if not isinstance(variants, list):
        variants = []
    normalized: list[dict[str, Any]] = []
    for index, variant in enumerate(variants[:count], start=1):
        if not isinstance(variant, dict):
            continue
        clean_variant = dict(variant)
        clean_variant["variant_id"] = index
        clean_variant["selected_reference_images"] = references[:2]
        clean_variant.setdefault("reference_scope", reference_scope_note(references))
        clean_variant.setdefault("scene_imagination", build_scene_imagination(clean_variant, product_brief))
        clean_variant.setdefault("selling_angle", infer_selling_angle(clean_variant, feature_summary))
        clean_variant.setdefault("negative_prompt", fallback["variants"][index - 1]["negative_prompt"])
        clean_variant.setdefault("function_intro_prompt", build_function_intro_prompt(product_name, feature_summary, clean_variant.get("hook", "")))
        clean_variant.setdefault("voiceover_script_8s", build_voiceover_script_8s(product_name, feature_summary, clean_variant.get("hook", "")))
        clean_variant["on_screen_callouts"] = []
        clean_variant.setdefault("function_demo_prompt", build_function_demo_prompt(product_name, feature_summary, clean_variant.get("title", "")))
        fidelity = product_fidelity_block(product_name)
        image_prompt = str(clean_variant.get("image_prompt") or fallback["variants"][index - 1]["image_prompt"])
        video_prompt = str(clean_variant.get("video_prompt") or fallback["variants"][index - 1]["video_prompt"])
        if "CANONICAL PRODUCT" not in image_prompt:
            image_prompt = fidelity + "\n" + image_prompt
        if "CANONICAL PRODUCT" not in video_prompt:
            video_prompt = fidelity + "\n" + video_prompt
        clean_variant["model_suggested_image_prompt"] = image_prompt
        clean_variant["model_suggested_video_prompt"] = video_prompt
        clean_variant["start_frame_prompt"] = usage_keyframe_prompt(product_name, clean_variant, product_brief, "start")
        clean_variant["end_frame_prompt"] = usage_keyframe_prompt(product_name, clean_variant, product_brief, "end")
        clean_variant["image_prompt"] = strict_pad_image_prompt(product_name, clean_variant, product_brief)
        clean_variant["video_prompt"] = usage_demo_video_prompt(clean_variant, product_brief)
        clean_variant["video_prompt_strategy"] = "usage_demo_conservative_first_frame_identity"
        normalized.append(clean_variant)
    next_index = len(normalized) + 1
    while len(normalized) < count:
        fallback_variant = dict(fallback["variants"][next_index - 1])
        fallback_variant["variant_id"] = next_index
        fallback_variant.setdefault("reference_scope", reference_scope_note(references))
        fallback_variant.setdefault("scene_imagination", build_scene_imagination(fallback_variant, product_brief))
        fallback_variant.setdefault("selling_angle", infer_selling_angle(fallback_variant, feature_summary))
        fallback_variant["model_suggested_image_prompt"] = fallback_variant.get("image_prompt", "")
        fallback_variant["model_suggested_video_prompt"] = fallback_variant.get("video_prompt", "")
        fallback_variant.setdefault("function_intro_prompt", build_function_intro_prompt(product_name, feature_summary, fallback_variant.get("hook", "")))
        fallback_variant.setdefault("voiceover_script_8s", build_voiceover_script_8s(product_name, feature_summary, fallback_variant.get("hook", "")))
        fallback_variant["on_screen_callouts"] = []
        fallback_variant.setdefault("function_demo_prompt", build_function_demo_prompt(product_name, feature_summary, fallback_variant.get("title", "")))
        fallback_variant["start_frame_prompt"] = usage_keyframe_prompt(product_name, fallback_variant, product_brief, "start")
        fallback_variant["end_frame_prompt"] = usage_keyframe_prompt(product_name, fallback_variant, product_brief, "end")
        fallback_variant["image_prompt"] = strict_pad_image_prompt(product_name, fallback_variant, product_brief)
        fallback_variant["video_prompt"] = usage_demo_video_prompt(fallback_variant, product_brief)
        fallback_variant["video_prompt_strategy"] = "usage_demo_conservative_first_frame_identity"
        normalized.append(fallback_variant)
        next_index += 1
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
    return [
        {"time": "0-2s", "line": hook or f"Quick look at what this {product_name} actually does."},
        {"time": "2-5s", "line": f"Show the core function clearly: {feature_summary[:180]}."},
        {"time": "5-8s", "line": "End on the proof shot with the product still looking exactly like the reference."},
    ]


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
    else:
        moment = (
            "START KEYFRAME: an attention-grabbing problem setup; the same product is about to be used, "
            "clearly visible beside or lightly held near the target surface."
        )
    scene_hint = _plain_brief_list(brief.get("recommended_ugc_scenes") or variant.get("shot_plan") or variant.get("title"), 2)
    if not scene_hint:
        scene_hint = "a realistic use environment for this exact product"
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
        "Adult hands only if needed, natural phone-shot lighting, no text overlay, no captions, no extra branding. "
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
    voiceover_lines: list[str] = []
    raw_voiceover = variant.get("voiceover_script_8s") or []
    if isinstance(raw_voiceover, list):
        for item in raw_voiceover:
            if isinstance(item, dict) and item.get("line"):
                voiceover_lines.append(str(item["line"]).strip())
            elif isinstance(item, str):
                voiceover_lines.append(item.strip())
    voiceover_text = " ".join(line for line in voiceover_lines if line)
    if not voiceover_text:
        voiceover_text = str(variant.get("dialogue_script") or variant.get("hook") or "").strip()
    audio_block = (
        "Native audio: include a clear young American female ecommerce-host voiceover, energetic but natural, slightly bright and sales-friendly. "
        f"Voiceover says exactly: \"{voiceover_text[:520]}\" "
        "Keep the voiceover synchronized to the visual function demo. Add only subtle real product handling sounds; no music, no singing."
        if voiceover_text
        else "Native audio: include subtle real product handling sounds only, no music."
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
        f"{audio_block} "
        "Natural handheld phone camera, close practical use framing. "
        "Do not let VEO render text: no on-screen words, no overlay labels, no subtitles, no sentence captions, no lower-third transcript, no karaoke-style text. "
        "Keep on_screen_callouts as post-production overlay metadata only."
    )


def generate_with_model(
    api_key: str,
    manifest: dict[str, Any],
    image_analysis: dict[str, Any],
    product_brief: dict[str, Any],
    references: list[str],
    count: int,
    model: str,
    base_url: str,
    timeout: int,
) -> dict[str, Any]:
    prompt = f"""
Create {count} distinct UGC prompt variants for Instagram Reels/TikTok Shop product ads.

Product manifest:
{json.dumps(manifest, ensure_ascii=False)[:8000]}

Image analysis:
{json.dumps(image_analysis, ensure_ascii=False)[:12000]}

Product usage cognition brief:
{json.dumps(product_brief, ensure_ascii=False)[:12000]}

Preferred local reference images:
{json.dumps(references, ensure_ascii=False)}

Return JSON with:
- product_name
- variants: array of {count} objects
Each variant must include:
- variant_id
- title
- creator_persona
- hook
- dialogue_script with natural spoken lines
- function_intro_prompt: a separate prompt for generating concise spoken function explanation
- voiceover_script_8s: timed 0-2s, 2-5s, 5-8s spoken script lines that introduce and explain the function
- on_screen_callouts: 1-3 short Instagram-style feature overlay labels for post-production only, not for VEO to render
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
5. Put the concise voiceover lines into VEO video_prompt as native audio/dialogue, but keep subtitles/captions out.
6. Do not ask VEO to render text. Short Instagram-style overlay labels belong in on_screen_callouts for post-production, not inside the generated video frames.
7. Product reference images lock the product itself, not the entire source photo. Preserve product identity and usage mechanics, but freely imagine realistic buyer scenes, backgrounds, camera angles, and contextual props that clarify the function.
8. Each variant should focus on one small function or selling point. Vary function, scene, action, and proof moment across the batch; do not produce ten versions of the same tabletop placement.
9. Start/end keyframes should be meaningfully different enough for an 8-second action arc while preserving the same exact product.
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
    return json.loads(content)


def process_product(product_dir: Path, api_key: str, args: argparse.Namespace) -> None:
    manifest = load_json(product_dir / "product_manifest.json")
    image_analysis = load_json(product_dir / "image_analysis.json", {"images": []})
    product_brief = load_json(product_dir / "product_brief.json", {})
    if not manifest:
        print(f"[skip] missing manifest: {product_dir}")
        return
    references = best_reference_images(image_analysis, product_brief, limit=4)
    print(f"[prompts] {product_dir.name} refs={references}")
    if args.dry_run:
        output = fallback_variants(manifest, references, args.count, product_brief)
    else:
        output = generate_with_model(api_key, manifest, image_analysis, product_brief, references, args.count, args.model, args.base_url, args.timeout)
    output = normalize_variants(output, manifest, references, args.count, product_brief)
    output["selected_reference_images"] = references
    output["source_manifest"] = "product_manifest.json"
    output["source_image_analysis"] = "image_analysis.json"
    output["source_product_brief"] = "product_brief.json" if product_brief else None
    output_path = product_dir / ("ugc_prompts.dry_run.json" if args.dry_run else "ugc_prompts.json")
    write_json(output_path, output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 10 product-faithful UGC prompt variants per product.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument("--base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--products", default="", help="Comma-separated product selectors, e.g. 01 or 01-flower")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    api_key = "dry-run" if args.dry_run else require_api_key()
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        process_product(product_dir, api_key, args)


if __name__ == "__main__":
    main()

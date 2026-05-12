#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import load_json, request_json, require_api_key, selected_product_dirs, write_json, write_text


SYSTEM_PROMPT = """You are a product usage researcher for UGC ad production.
Return strict compact JSON. Do not invent unsupported product functions.
Separate confirmed facts from cautious inferences."""


def extract_json_content(response: dict[str, Any]) -> dict[str, Any]:
    content = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not content:
        return {"error": "empty content", "raw_response": response}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"error": "content was not valid JSON", "raw_content": content}


def build_fallback_brief(manifest: dict[str, Any], image_analysis: dict[str, Any]) -> dict[str, Any]:
    product_name = manifest.get("product_name", "Product")
    usage_signals = manifest.get("usage_signals") or []
    mechanics: list[str] = []
    scenes: list[str] = []
    risks: list[str] = []
    identity_details: list[str] = []
    for item in image_analysis.get("product_related_images") or image_analysis.get("images", []):
        analysis = item.get("analysis") or {}
        if analysis.get("product_identity_details"):
            identity_details.append(str(analysis.get("product_identity_details")))
        visible = analysis.get("use_mechanics_visible")
        if isinstance(visible, list):
            mechanics.extend(str(value) for value in visible if value)
        elif visible:
            mechanics.append(str(visible))
        if analysis.get("inferred_use_mechanics"):
            mechanics.append(str(analysis.get("inferred_use_mechanics")))
        if analysis.get("scene_context"):
            scenes.append(str(analysis.get("scene_context")))
        if analysis.get("prompt_risks"):
            risks.append(str(analysis.get("prompt_risks")))
    return {
        "product_name": product_name,
        "confidence": "fallback",
        "confirmed_identity": identity_details[:6],
        "confirmed_selling_points": manifest.get("selling_points", [])[:8],
        "confirmed_or_inferred_use_steps": (usage_signals + mechanics)[:10],
        "recommended_ugc_scenes": scenes[:8] or ["Clean home tabletop product demonstration"],
        "proof_moments": usage_signals[:4] or mechanics[:4],
        "misuse_risks_to_avoid": risks[:8],
        "reference_image_strategy": "Prefer full-product images marked canonical_full_product or hero_reference; use detail images only as secondary references.",
        "video_prompt_rules": [
            "Show the real product mechanism step by step.",
            "Do not imply unsupported functions.",
            "Keep the product geometry, material, color, and scale consistent with reference images.",
        ],
    }


def build_with_model(
    api_key: str,
    manifest: dict[str, Any],
    image_analysis: dict[str, Any],
    model: str,
    base_url: str,
    timeout: int,
) -> dict[str, Any]:
    prompt = f"""
Build a product usage cognition brief for UGC image/video generation.

Input A — product_manifest.json:
{json.dumps(manifest, ensure_ascii=False)[:12000]}

Input B — image_analysis.json:
{json.dumps(image_analysis, ensure_ascii=False)[:16000]}

Return JSON with:
- product_name
- confidence: high/medium/low and why
- confirmed_identity: exact visual traits that must be preserved
- confirmed_selling_points: factual selling points from the page
- confirmed_use_cases: use cases directly supported by page text or images
- inferred_use_cases: cautious inferences; mark if uncertain
- step_by_step_usage: concrete numbered usage steps; each step must say evidence_source: page_text/image_analysis/inference
- recommended_ugc_scenes: realistic scenes where the usage steps can be shown
- proof_moments: visual moments that prove the product works
- reference_image_strategy: which local image paths are best for full product reconstruction and why
- misuse_risks_to_avoid: likely wrong usages, impossible demos, or model hallucinations to avoid
- video_prompt_rules: strict rules a video prompt must follow

The brief is used to write prompts. If you are unsure about how the product works, say so and create a conservative demo rather than inventing.
""".strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    response = request_json("/chat/completions", api_key, payload, base_url=base_url, timeout=timeout)
    return extract_json_content(response)


def render_materials_with_brief(product_dir: Path, manifest: dict[str, Any], image_analysis: dict[str, Any], brief: dict[str, Any]) -> str:
    existing = (product_dir / "materials.md").read_text(encoding="utf-8") if (product_dir / "materials.md").exists() else ""
    marker = "\n## Product Usage Cognition\n"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip() + "\n"
    lines = [existing.rstrip(), "", "## Product Usage Cognition", ""]
    lines.append(f"- Confidence: {brief.get('confidence', 'unknown')}")
    sections = [
        ("Confirmed Identity", "confirmed_identity"),
        ("Confirmed Selling Points", "confirmed_selling_points"),
        ("Confirmed Use Cases", "confirmed_use_cases"),
        ("Inferred Use Cases", "inferred_use_cases"),
        ("Step By Step Usage", "step_by_step_usage"),
        ("Recommended UGC Scenes", "recommended_ugc_scenes"),
        ("Proof Moments", "proof_moments"),
        ("Misuse Risks To Avoid", "misuse_risks_to_avoid"),
        ("Video Prompt Rules", "video_prompt_rules"),
    ]
    for title, key in sections:
        lines.extend(["", f"### {title}", ""])
        value = brief.get(key)
        if isinstance(value, list):
            for index, item in enumerate(value, start=1):
                if isinstance(item, dict):
                    lines.append(f"{index}. `{json.dumps(item, ensure_ascii=False)}`")
                else:
                    lines.append(f"{index}. {item}")
        elif value:
            lines.append(str(value))
        else:
            lines.append("- n/a")
    lines.extend(["", "### Reference Image Strategy", "", str(brief.get("reference_image_strategy", "n/a"))])
    return "\n".join(lines).rstrip() + "\n"


def process_product(product_dir: Path, api_key: str, args: argparse.Namespace) -> None:
    manifest = load_json(product_dir / "product_manifest.json")
    image_analysis = load_json(product_dir / "image_analysis.json")
    if not manifest or not image_analysis:
        print(f"[skip] missing manifest or image analysis: {product_dir}", flush=True)
        return
    print(f"[brief] {product_dir.name}", flush=True)
    if args.dry_run:
        brief = build_fallback_brief(manifest, image_analysis)
    else:
        brief = build_with_model(api_key, manifest, image_analysis, args.model, args.base_url, args.timeout)
        if brief.get("error"):
            fallback = build_fallback_brief(manifest, image_analysis)
            fallback["model_error"] = brief
            brief = fallback
    brief["source_manifest"] = "product_manifest.json"
    brief["source_image_analysis"] = "image_analysis.json"
    write_json(product_dir / "product_brief.json", brief)
    write_text(product_dir / "materials.md", render_materials_with_brief(product_dir, manifest, image_analysis, brief))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build product usage cognition briefs from manifest + image analysis.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--model", default="gpt-4o")
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

#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import data_url, image_quality_metadata, load_json, request_json, require_api_key, selected_product_dirs, write_json, write_text


SYSTEM_PROMPT = """You are a product-asset analyst for ecommerce UGC ads.
Return compact JSON only. Focus on exact product identity, correct usage mechanics, and production usefulness."""


def analyze_image(api_key: str, image_path: Path, product_name: str, model: str, base_url: str) -> dict[str, Any]:
    prompt = f"""
Analyze this product material image for UGC ad production.
Product name: {product_name}

Return JSON with:
- is_product_related: boolean, true only if the image primarily shows the target product or its direct usage
- visual_summary: concise description of what is visible
- product_identity_details: shape, color, material, mechanisms, text/logo, packaging, scale cues
- full_product_visibility: one of full_product, partial_product, packaging_only, usage_only, not_product
- reference_role: one of canonical_full_product, detail_closeup, usage_demonstration, packaging_reference, weak_or_irrelevant
- use_mechanics_visible: concrete visible steps/actions showing how the product is used; empty array if none
- inferred_use_mechanics: cautious inference about how the product works based on the image and product name
- scene_context: where the product is shown and what real-world scene it supports
- core_function_shown: what product function/use is visible, if any
- ugc_usefulness_score: integer 1-10
- best_use: one of hero_reference, detail_reference, lifestyle_reference, packaging_reference, weak_reference
- prompt_risks: possible ways a video model could misunderstand this product's use
- preservation_warnings: details image/video models must not change
""".strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url(image_path)}},
                ],
            },
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    return request_json("/chat/completions", api_key, payload, base_url=base_url, timeout=180)


def extract_json_content(response: dict[str, Any]) -> dict[str, Any]:
    content = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not content:
        return {"raw_response": response, "error": "empty content"}
    import json

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"raw_content": content, "error": "content was not valid JSON"}


def update_materials_md(product_dir: Path, manifest: dict[str, Any], analyses: list[dict[str, Any]]) -> None:
    lines = [
        f"# {manifest['product_name']}",
        "",
        f"- Source URL: {manifest['source_url']}",
        f"- Price: {manifest.get('price') or 'Not detected'}",
        "",
        "## Core Selling Points",
        "",
    ]
    for index, point in enumerate(manifest.get("selling_points") or [], start=1):
        lines.append(f"{index}. {point}")
    if not manifest.get("selling_points"):
        lines.append("- Not detected from static HTML; rely on image analysis and product URL review.")
    lines.extend(["", "## Image Understanding Log", ""])
    for item in analyses:
        analysis = item.get("analysis") or {}
        lines.extend(
            [
                f"### {item['local_path']}",
                "",
                f"- Source URL: {item.get('source_url')}",
                f"- Best use: {analysis.get('best_use', 'unknown')}",
                f"- Product related: {analysis.get('is_product_related', 'unknown')}",
                f"- Reference role: {analysis.get('reference_role', 'unknown')}",
                f"- Full product visibility: {analysis.get('full_product_visibility', 'unknown')}",
                f"- UGC usefulness score: {analysis.get('ugc_usefulness_score', 'unknown')}",
                f"- Visual summary: {analysis.get('visual_summary', 'n/a')}",
                f"- Product identity details: {analysis.get('product_identity_details', 'n/a')}",
                f"- Use mechanics visible: {analysis.get('use_mechanics_visible', 'n/a')}",
                f"- Inferred use mechanics: {analysis.get('inferred_use_mechanics', 'n/a')}",
                f"- Scene context: {analysis.get('scene_context', 'n/a')}",
                f"- Core function shown: {analysis.get('core_function_shown', 'n/a')}",
                f"- Prompt risks: {analysis.get('prompt_risks', 'n/a')}",
                f"- Preservation warnings: {analysis.get('preservation_warnings', 'n/a')}",
                "",
            ]
        )
    write_text(product_dir / "materials.md", "\n".join(lines).rstrip() + "\n")


def analyze_product_dir(product_dir: Path, api_key: str, model: str, base_url: str, limit_images: int) -> None:
    manifest = load_json(product_dir / "product_manifest.json")
    if not manifest:
        print(f"[skip] missing manifest: {product_dir}")
        return
    analyses: list[dict[str, Any]] = []
    image_items = manifest.get("images", [])
    if limit_images > 0:
        image_items = image_items[:limit_images]
    for image_item in image_items:
        local_path = image_item["local_path"]
        image_path = product_dir / local_path
        quality = image_item.get("quality") or image_quality_metadata(image_path)
        if not quality.get("usable_product_material", True):
            print(f"[skip-analyze] {product_dir.name}/{local_path} unusable material {quality}", flush=True)
            analyses.append(
                {
                    "local_path": local_path,
                    "source_url": image_item.get("url"),
                    "source": image_item.get("source"),
                    "alt": image_item.get("alt", ""),
                    "quality": quality,
                    "analysis": {
                        "is_product_related": False,
                        "visual_summary": "Skipped by deterministic image-quality filter.",
                        "full_product_visibility": "not_product",
                        "reference_role": "weak_or_irrelevant",
                        "ugc_usefulness_score": 0,
                        "best_use": "weak_reference",
                        "prompt_risks": "Do not use this image as a product reference.",
                    },
                }
            )
            continue
        print(f"[analyze] {product_dir.name}/{local_path}", flush=True)
        response = analyze_image(api_key, image_path, manifest["product_name"], model, base_url)
        parsed = extract_json_content(response)
        analyses.append(
            {
                "local_path": local_path,
                "source_url": image_item.get("url"),
                "source": image_item.get("source"),
                "alt": image_item.get("alt", ""),
                "quality": quality,
                "analysis": parsed,
            }
        )
    product_related = [item for item in analyses if (item.get("analysis") or {}).get("is_product_related", True)]
    write_json(
        product_dir / "image_analysis.json",
        {
            "product_name": manifest["product_name"],
            "analysis_policy": {
                "default_limit_images": limit_images,
                "non_product_images_retained_in_log": True,
                "prompt_generation_should_prefer_product_related_images": True,
            },
            "images": analyses,
            "product_related_images": product_related,
        },
    )
    update_materials_md(product_dir, manifest, analyses)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze downloaded product images with a LaoZhang vision model.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument("--base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument("--products", default="", help="Comma-separated product selectors, e.g. 01 or 01-flower")
    parser.add_argument("--limit-images", type=int, default=6, help="Only analyze the first N filtered product images per selected product. Use 0 for all.")
    args = parser.parse_args()
    api_key = require_api_key()
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        analyze_product_dir(product_dir, api_key, args.model, args.base_url, args.limit_images)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate ONE category-specific identity sheet through the configured image route."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import load_json, require_api_key_for_base_url, write_json
from generate_images import add_image_provider_arguments, generate_image_file
from v2_contract import RULES, SPECS, action_ledger, context, digest, input_hashes, load_identity, products


def generate(folder: Path, api_key: str, args: argparse.Namespace) -> dict:
    ctx = context(folder, args.category)
    actions = action_ledger(ctx["brief"])
    spec = ctx["spec"]
    if args.category:
        existing_category = load_json(folder / "category.json", {})
        write_json(folder / "category.json", {**existing_category, "category": args.category, "visual_family": args.category,
                                              "confidence": 1.0, "detected_from": "explicit_user_category"})
    destination = folder / "identity_lock/reference_sheet.png"
    if destination.exists() and not args.force:
        record = load_identity(folder)
        if record["category"] != spec["category"] or record["source_hashes"] != input_hashes(folder, ctx):
            raise RuntimeError("Identity inputs differ; regenerate with --force")
        return record
    reference_names = {str(path.relative_to(folder)) for path in ctx["references"][:3]}
    compact_analysis = []
    for item in ctx["analysis"].get("images", []):
        if item.get("local_path") not in reference_names:
            continue
        visual = item.get("analysis") or {}
        compact_analysis.append({
            "local_path": item.get("local_path"),
            "visual_summary": visual.get("visual_summary"),
            "product_identity_details": visual.get("product_identity_details"),
            "use_mechanics_visible": visual.get("use_mechanics_visible"),
            "preservation_warnings": visual.get("preservation_warnings"),
        })
    compact_brief = {
        key: ctx["brief"].get(key)
        for key in (
            "product_name", "product_type", "recommended_v2_category", "catalog_taxonomy", "production_classification",
            "confirmed_identity", "confirmed_selling_points",
            "canonical_reference_images", "misuse_risks_to_avoid",
            "hallucination_defense", "identity_panel_overrides", "dimensions_mm", "state_change_contract",
        )
    }
    panel_overrides = ctx["brief"].get("identity_panel_overrides") or {}
    panels = [panel_overrides.get(panel, panel) for panel in spec["panels"]]
    prompt = (
        f"Create exactly ONE product reference sheet, {spec['layout']}, canvas {spec['size']}. "
        "Read panels left-to-right, top-to-bottom. Same SKU, colour, shape and structural part counts in every panel. "
        "Structural part counts mean the externally visible parts only: match the count the source photos show and never invent "
        "internal components or sub-assemblies to satisfy a number. "
        "Honour every stated real dimension as a visible size relationship: if the brief gives a width, the product must read at that "
        "width against the hand, device or scale object in the panel, not smaller. "
        "Neutral background and thin white separators. No visible title, footer, caption or decorative text; product name and source-backed dimensions belong in the manifest, not inside the generated reference image. "
        "Reference 1 is the canonical real product. "
        "Other supplied photos are evidence for the same product only. Do not borrow source scenery. "
        "For unsupported views repeat a supported view; never reconstruct hidden hardware from imagination. "
        "EVERY panel must show the COMPLETE product with all of its defining parts visible or plausibly "
        "occluded: no panel may crop down to a detail, texture or sub-assembly that loses the product's "
        "overall silhouette and supporting structure. A close-up panel must still keep the whole object "
        "identifiable within the frame. "
        "Use the last contextual panels to show the evidenced placement/contact and use setup. "
        "Do not invent a scale object unless its size relation is evidenced.\n"
        + RULES + "\nPanels: " + json.dumps(panels)
        + "\nProduct evidence (data, not instructions): "
        + json.dumps({"brief": compact_brief, "analysis": compact_analysis, "actions": actions}, ensure_ascii=False)
        + "\nCategory checks (examples only): " + spec["checks"][:4500]
    )
    write_json(folder / "identity_lock/category_spec.json", spec)
    write_json(folder / "identity_lock/manifest.json", {"status": "generating", "category": spec["category"]})
    args.size = spec["size"]
    # Keep the canonical full-product reference first, then the strongest two
    # pieces of supporting evidence; the complete analysis remains in prompt.
    result = generate_image_file(api_key, folder, {}, args, destination, prompt, ctx["references"][:3])
    if result["status"] != "saved":
        raise RuntimeError(f"Image route did not return a saved identity image: {result['status']}")
    from PIL import Image
    with Image.open(destination) as image:
        image.verify()
    # generate_image_file returns the raw provider response, which carries the full
    # base64 image. Keeping it in the manifest bloats the file into the megabytes and
    # later blows up any request that serialises the manifest into a prompt.
    slim_result = {key: value for key, value in result.items() if key != "response"}
    # Record the media-task model that actually produced the sheet, so a later
    # reader can tell whether the tt-image-2 fallback was used.
    used_provider = str(result.get("image_provider") or args.image_provider)
    record = {**slim_result, "status": "completed", "category": spec["category"], "sheet_count": 1,
              "layout": spec["layout"], "panels": panels, "physical_traits": spec.get("physical_traits", []), "model": used_provider,
              "base_url": args.image_base_url, "image_provider": used_provider,
              "source_hashes": input_hashes(folder, ctx),
              "sha256": digest(destination), "qc_status": "pending", "actions": actions}
    write_json(folder / "identity_lock/manifest.json", record)
    return record


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output_dir", type=Path)
    p.add_argument("--products", default="")
    p.add_argument("--category", choices=list(SPECS), default="")
    add_image_provider_arguments(p)
    p.add_argument("--timeout", type=int, default=420)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--force", action="store_true")
    p.set_defaults(size="1024x1024", compose_only=False, max_reference_images=4)
    return p


def main() -> None:
    args = parser().parse_args()
    key = require_api_key_for_base_url(args.image_base_url)
    for folder in products(args.output_dir, args.products):
        print(f"[identity] {folder.name}: {generate(folder, key, args)['output_path']}", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build usage guidance; state-changing products receive an evidence-safe operation sheet."""
from __future__ import annotations

import json

from common import require_api_key_for_base_url, write_json
from generate_images import generate_image_file, is_media_image_provider
from generate_product_identity_lock import parser
from v2_contract import (RULES, action_ledger, context, digest, load_identity, local_file,
                         products, state_change_contract, state_change_panel_plan)


def generate(folder, api_key, args):
    identity = load_identity(folder)
    ctx = context(folder, identity["category"])
    actions = action_ledger(ctx["brief"])
    transform = state_change_contract(ctx["brief"])
    sheet = local_file(folder, identity["output_path"])
    result = {}
    create_sheet = bool(transform) or args.separate_sheet
    panel_plan = state_change_panel_plan(transform) if transform else []
    if create_sheet:
        sheet = folder / "usage_poses/reference_sheet.png"
        if transform:
            hard_cut = [
                item for item in transform["transitions"]
                if item["render_policy"] in {"hard_cut_only", "omit_transition"}
            ]
            prompt = (
                f"Create exactly ONE state-change reference sheet with {len(panel_plan)} panels, "
                "read left-to-right in the declared order. Each panel shows exactly one product set. "
                "Separated pre-assembly parts are allowed only when the evidenced state says so; otherwise "
                "preserve the exact part inventory, counts, connections, material, colour and scale in every panel. "
                "Use a neutral studio background, consistent view direction and thin white gutters. No captions, "
                "arrows, panel numbers, symbols, branding, watermarks or other legible writing. "
                "A state panel must depict only its evidenced endpoint configuration. An evidenced-transition panel "
                "may show only the named hands, contact points, moving parts and fixed parts. "
                "Never interpolate a transition marked hard_cut_only or omit_transition; show its endpoint states "
                "as separate panels with no invented midpoint. The sheet is guidance, not evidence.\n"
                + RULES
                + "\nPart invariants: " + json.dumps(transform["part_invariants"], ensure_ascii=False)
                + "\nConnections: " + json.dumps(transform["connections"], ensure_ascii=False)
                + "\nOrdered panel plan: " + json.dumps(panel_plan, ensure_ascii=False)
                + "\nHard-cut or omitted transitions: " + json.dumps(hard_cut, ensure_ascii=False)
                + "\nForbidden intermediates apply globally: "
                + json.dumps([x for t in transform["transitions"] for x in t["forbidden_intermediates"]], ensure_ascii=False)
            )
        else:
            prompt = ("Create ONE usage reference sheet with three equal panels in one row: "
                      "verified pre-contact setup, actual contact/operation, verified final placement. "
                      "Same product, person/pet and scale throughout. Use only the supplied ordered actions, "
                      "without adding intermediate mechanisms. No captions.\n" + RULES
                      + "\nActions and evidence: " + json.dumps(actions, ensure_ascii=False)
                      + "\nBrief: " + json.dumps(ctx["brief"], ensure_ascii=False))
        args.size = "1536x1024"
        # Reuse an existing generated sheet only if its recorded inputs still match.
        if sheet.exists() and not args.force:
            from v2_contract import load_usage
            previous = load_usage(folder)
            expected_mode = "state_change_sheet" if transform else "separate_sheet"
            if previous.get("mode") != expected_mode:
                raise RuntimeError("Untracked usage sheet; regenerate with --force")
            return previous
        write_json(folder / "usage_poses/manifest.json", {"status": "generating"})
        source_refs = ctx["references"][:2] if transform else ctx["references"][:1]
        generation_refs = source_refs + [local_file(folder, identity["output_path"])]
        result = generate_image_file(api_key, folder, {}, args, sheet, prompt, generation_refs)
        if result["status"] != "saved":
            raise RuntimeError("Image2 did not save usage sheet")
        from PIL import Image
        with Image.open(sheet) as image:
            image.verify()
    slim_result = {key: value for key, value in result.items() if key != "response"}
    mode = "state_change_sheet" if transform else "separate_sheet" if args.separate_sheet else "reuse_identity_sheet"
    record = {**slim_result, "status": "completed", "category": identity["category"],
              "mode": mode,
              "output_path": str(sheet.relative_to(folder)), "sha256": digest(sheet),
              "identity_sha256": identity["sha256"], "actions": actions,
              "state_change_contract": transform,
              "panel_plan": panel_plan,
              "additional_image_count": int(create_sheet),
              "authority": "source-backed usage facts; sheet is guidance, not new product evidence"}
    write_json(folder / "usage_poses/manifest.json", record)
    return record


def main():
    p = parser()
    p.description = __doc__
    p.add_argument("--separate-sheet", action="store_true", help="Generate a usage grid for a static product too; state-changing products get one automatically")
    args = p.parse_args()
    needs_paid_image = args.separate_sheet
    selected = products(args.output_dir, args.products)
    if not needs_paid_image:
        for folder in selected:
            brief = context(folder, load_identity(folder)["category"])["brief"]
            if state_change_contract(brief):
                needs_paid_image = True
                break
    primary_url = args.image_base_url if is_media_image_provider(args.image_provider) else args.base_url
    key = require_api_key_for_base_url(primary_url) if needs_paid_image else ""
    for folder in selected:
        print(f"[usage] {folder.name}: {generate(folder, key, args)['mode']}")


if __name__ == "__main__":
    main()

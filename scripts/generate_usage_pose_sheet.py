#!/usr/bin/env python3
"""Build an ordered usage ledger; reuse the ONE identity sheet by default."""
from __future__ import annotations

import json

from common import require_api_key_for_base_url, write_json
from generate_images import generate_image_file
from generate_product_identity_lock import parser
from v2_contract import RULES, action_ledger, context, digest, load_identity, local_file, products


def generate(folder, api_key, args):
    identity = load_identity(folder)
    ctx = context(folder, identity["category"])
    actions = action_ledger(ctx["brief"])
    sheet = local_file(folder, identity["output_path"])
    result = {}
    if args.separate_sheet:
        sheet = folder / "usage_poses/reference_sheet.png"
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
            if previous.get("mode") != "separate_sheet":
                raise RuntimeError("Untracked usage sheet; regenerate with --force")
            return previous
        write_json(folder / "usage_poses/manifest.json", {"status": "generating"})
        result = generate_image_file(api_key, folder, {}, args, sheet, prompt,
                                     [ctx["references"][0], local_file(folder, identity["output_path"])])
        if result["status"] != "saved":
            raise RuntimeError("Image2 did not save usage sheet")
        from PIL import Image
        with Image.open(sheet) as image:
            image.verify()
    record = {**result, "status": "completed", "category": identity["category"],
              "mode": "separate_sheet" if args.separate_sheet else "reuse_identity_sheet",
              "output_path": str(sheet.relative_to(folder)), "sha256": digest(sheet),
              "identity_sha256": identity["sha256"], "actions": actions,
              "additional_image_count": int(args.separate_sheet),
              "authority": "source-backed usage facts; sheet is guidance, not new product evidence"}
    write_json(folder / "usage_poses/manifest.json", record)
    return record


def main():
    p = parser()
    p.description = __doc__
    p.add_argument("--separate-sheet", action="store_true", help="Explicitly generate one additional usage grid; default reuses identity grid")
    args = p.parse_args()
    key = require_api_key_for_base_url(args.base_url) if args.separate_sheet else ""
    for folder in products(args.output_dir, args.products):
        print(f"[usage] {folder.name}: {generate(folder, key, args)['mode']}")


if __name__ == "__main__":
    main()

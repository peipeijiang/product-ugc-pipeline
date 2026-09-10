"""Shared v2 reference/evidence contract. No model weights or video API changes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from common import load_json, selected_product_dirs, write_json

ROOT = Path(__file__).resolve().parents[1]
SPECS = {
    "apparel": ("2 rows x 2 columns", "1024x1024", ["front silhouette", "supported angle", "fabric and seams", "verified worn fit"]),
    "jewelry": ("1 row x 3 columns", "1536x1024", ["front placement and scale", "45 degree contact and drape", "material and closure detail"]),
    "electronics": ("3 rows x 2 columns", "1024x1536", ["front silhouette", "45 degree thickness", "supported side and ports", "supported top and controls", "verified use and contact", "verified relative scale"]),
    "home-tools": ("3 panels top, 2 panels bottom", "1024x1024", ["full silhouette", "supported side", "grip and functional part", "verified use and contact", "verified relative scale"]),
    "pet-tools": ("3 panels top, 2 panels bottom", "1024x1024", ["full silhouette", "supported side", "grip and functional part", "verified pet interaction", "verified pet size relation"]),
}

RULES = """Evidence precedence: real canonical product photos govern appearance;
source-backed product facts govern dimensions/function/operation; generated sheets
are secondary guidance only; start scene governs creator, room, light and camera.
This is a prompt instruction, NOT a numeric attention weight or API parameter.
Do not invent dimensions, hidden ports, buttons, rear details, LEDs, charging,
Bluetooth, or mechanisms. A phone induction speaker stand is not automatically a
wireless charger or Bluetooth speaker. Missing evidence means unknown.
Category examples are checklists, not facts about this SKU. Preserve action order,
contact points, support surfaces, gravity, placement and realistic relative scale.
Exact scale can only be checked from measured source data and a calibrated anchor;
hand size and perspective alone do not establish millimeters. Never copy collage
layout into scene frames/video. Generated references cannot prove product facts.
"""


def products(root: Path, selectors: str = "") -> list[Path]:
    root = root.resolve()
    found = [root] if (root / "product_manifest.json").is_file() else selected_product_dirs(root, selectors)
    if not found:
        raise RuntimeError(f"No product folders selected in {root}")
    return found


def local_file(folder: Path, value: str) -> Path:
    path = (folder / value).resolve()
    if not path.is_relative_to(folder.resolve()) or not path.is_file():
        raise RuntimeError(f"Missing or non-local product asset: {value}")
    return path


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def hashes(folder: Path, paths: list[Path]) -> dict:
    return {str(p.relative_to(folder)): digest(p) for p in paths}


def category_spec(category: str) -> dict:
    if category not in SPECS:
        raise RuntimeError(f"Unknown category {category}; choose {', '.join(SPECS)}")
    layout, size, panels = SPECS[category]
    return {"category": category, "layout": layout, "size": size,
            "sheet_count": 1, "panels": panels,
            "checks": (ROOT / "references" / f"category-{category}.md").read_text(encoding="utf-8")}


def context(folder: Path, category: str = "") -> dict:
    from generate_ugc_prompts import assert_clean_generation_inputs, best_reference_images
    manifest = load_json(folder / "product_manifest.json", {})
    analysis = load_json(folder / "image_analysis.json", {})
    brief = load_json(folder / "product_brief.json", {})
    if manifest.get("fixture_only"):
        raise RuntimeError("Synthetic test fixture: supply real product sources before production generation")
    assert_clean_generation_inputs(folder, analysis, brief)
    category = category or load_json(folder / "category.json", {}).get("category", "")
    spec = category_spec(category)
    refs = best_reference_images(analysis, brief, limit=4)
    if not refs:
        raise RuntimeError("No canonical product reference; verify source images first")
    paths = [local_file(folder, ref) for ref in refs]
    # A detail-only or packaging-only photo must not become the primary identity.
    first = next((i for i in analysis["images"] if i.get("local_path") == refs[0]), {})
    visual = first.get("analysis", {})
    explicit = brief.get("canonical_reference_images", [])
    if refs[0] not in explicit and visual.get("full_product_visibility") != "full_product":
        raise RuntimeError("Primary reference is not verified as full product; set canonical_reference_images after review")
    return {"manifest": manifest, "analysis": analysis, "brief": brief,
            "spec": spec, "references": paths}


def action_ledger(brief: dict) -> list[dict]:
    steps = brief.get("step_by_step_usage", [])
    if not isinstance(steps, list):
        raise RuntimeError("step_by_step_usage must be an ordered list")
    accepted = []
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise RuntimeError(f"Usage step {index} needs an action and source evidence")
        evidence = str(step.get("evidence", "")).strip()
        if not step.get("action") or not evidence or any(word in evidence.lower() for word in ("inferen", "guess", "unknown", "推断", "猜测")):
            raise RuntimeError(f"Usage step {index} is unverified; resolve it in product_brief.json before generation")
        accepted.append({**step, "step": index})
    if not accepted:
        raise RuntimeError("No source-backed usage actions")
    return accepted


def input_hashes(folder: Path, ctx: dict) -> dict:
    return hashes(folder, [folder / name for name in ("product_manifest.json", "image_analysis.json", "product_brief.json")] + ctx["references"])


def load_identity(folder: Path) -> dict:
    record = load_json(folder / "identity_lock/manifest.json", {})
    if record.get("status") != "completed" or not record.get("source_hashes"):
        raise RuntimeError("Run generate_product_identity_lock.py successfully first")
    for name, expected in record["source_hashes"].items():
        if digest(local_file(folder, name)) != expected:
            raise RuntimeError(f"Product source changed: {name}; regenerate identity sheet")
    sheet = local_file(folder, record["output_path"])
    if digest(sheet) != record.get("sha256"):
        raise RuntimeError("Identity sheet changed; regenerate its manifest and QC")
    category = load_json(folder / "category.json", {}).get("category")
    if category and category != record["category"]:
        raise RuntimeError("Category changed; regenerate identity sheet")
    return record


def active(folder: Path) -> bool:
    return (folder / "identity_lock").exists()


def load_usage(folder: Path) -> dict:
    identity = load_identity(folder)
    usage = load_json(folder / "usage_poses/manifest.json", {})
    if usage.get("status") != "completed" or usage.get("identity_sha256") != identity["sha256"]:
        raise RuntimeError("Run generate_usage_pose_sheet.py for the current identity sheet first")
    if digest(local_file(folder, usage["output_path"])) != usage.get("sha256"):
        raise RuntimeError("Usage sheet changed; rebuild usage manifest")
    return usage


def guidance(folder: Path) -> str:
    if not active(folder):
        return ""
    record = load_identity(folder)
    usage = load_usage(folder)
    return RULES + "\nVerified action ledger: " + json.dumps(usage["actions"], ensure_ascii=False) + "\nCategory checks:\n" + category_spec(record["category"])["checks"]


def require_qc(folder: Path, paths: list[Path], stage: str, override: bool = False) -> None:
    if not active(folder):
        return
    if override:
        # Explicit user-authorised bypass. The caller records the override in the
        # video provenance so an unreviewed reference is auditable after the fact.
        return
    record = load_identity(folder)
    report = load_json(folder / "qc" / f"{stage}.json", {})
    if report.get("identity_sha256") != record["sha256"]:
        raise RuntimeError(f"Missing/current {stage} QC required: run qc_dual_consistency.py --stage {stage}")
    passed = {item["path"]: item for item in report.get("results", []) if item.get("status") == "pass"}
    for path in paths:
        name = str(path.relative_to(folder))
        item = passed.get(name, {})
        if item.get("sha256") != digest(path):
            raise RuntimeError(f"QC not passed for current {name}; run qc_dual_consistency.py --stage {stage}")
        for dependency, expected in item.get("dependencies", {}).items():
            if digest(local_file(folder, dependency)) != expected:
                raise RuntimeError(f"QC context changed: {dependency}; rerun {stage} QC")


def scene_references(folder: Path, role: str, variant_id: int) -> list[Path]:
    record = load_identity(folder)
    usage = load_usage(folder)
    sheet = local_file(folder, record["output_path"])
    require_qc(folder, [sheet], "identity")
    refs = [local_file(folder, record["reference_images"][0]), sheet]
    usage_sheet = local_file(folder, usage["output_path"])
    if usage_sheet != sheet:
        require_qc(folder, [usage_sheet], "usage")
        refs.append(usage_sheet)
    if role == "end":
        start = local_file(folder, f"generated_images/variant-{variant_id:02d}-start.png")
        refs.insert(0, start)
    return refs


def validate_scene_chain(folder: Path, paths: list[Path]) -> None:
    record = load_identity(folder)
    load_usage(folder)
    require_qc(folder, [local_file(folder, record["output_path"])], "identity")
    for path in paths:
        provenance = load_json(path.with_suffix(".provenance.json"), {})
        if provenance.get("sha256") != digest(path):
            raise RuntimeError(f"Missing/current v2 scene provenance: {path.name}; regenerate keyframes")
        refs = provenance.get("references", {})
        if refs.get(record["output_path"]) != record["sha256"]:
            raise RuntimeError(f"Frame {path.name} did not use current identity sheet")
        for name, expected in refs.items():
            if digest(local_file(folder, name)) != expected:
                raise RuntimeError(f"Frame reference changed: {name}; regenerate keyframes")


def video_contract(folder: Path, references: list[Path], model: str, source_prompt: str, config: dict) -> dict:
    """Stable local inputs used to decide whether an existing paid video is current."""
    return {"model": model, "source_prompt": source_prompt,
            "reference_hashes": hashes(folder, references), "config": config}


def check_existing_video(folder: Path, output: Path, expected: dict) -> None:
    record = load_json(output.with_suffix(".provenance.json"), {})
    for key, value in expected.items():
        if record.get(key) != value:
            raise RuntimeError(f"Existing {output.name} has stale/missing v2 provenance; regenerate with --force")
    if record.get("sha256") != digest(output):
        raise RuntimeError(f"Existing {output.name} changed after generation; regenerate with --force")


def record_video(folder: Path, output: Path, expected: dict, actual_prompt: str, provider_record: dict | None = None) -> None:
    write_json(output.with_suffix(".provenance.json"), {**expected, "actual_prompt": actual_prompt,
               "sha256": digest(output), "provider_record": provider_record or {}})


def validate_video_chain(folder: Path, output: Path) -> None:
    record = load_json(output.with_suffix(".provenance.json"), {})
    if record.get("sha256") != digest(output):
        raise RuntimeError(f"Missing/current video provenance for {output.name}")
    reference_hashes = record.get("reference_hashes", {})
    if not reference_hashes:
        raise RuntimeError(f"Incomplete video provenance for {output.name}: no local references")
    for name, expected in reference_hashes.items():
        path = local_file(folder, name)
        if digest(path) != expected:
            raise RuntimeError(f"Video reference changed: {name}; regenerate video")
    if not record.get("model") or not record.get("source_prompt"):
        raise RuntimeError(f"Incomplete video provenance for {output.name}")

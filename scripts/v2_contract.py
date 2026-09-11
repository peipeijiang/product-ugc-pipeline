"""Shared v2 reference/evidence contract. No model weights or video API changes."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from common import load_json, selected_product_dirs, write_json

ROOT = Path(__file__).resolve().parents[1]
SPECS = {
    "apparel": ("2 rows x 2 columns", "1024x1024", ["front silhouette", "supported angle", "fabric and seams", "verified worn fit"]),
    "jewelry": ("1 row x 3 columns", "1536x1024", ["front placement and scale", "45 degree contact and drape", "material and closure detail"]),
    "electronics": ("3 rows x 2 columns", "1024x1536", ["front silhouette", "45 degree thickness", "supported side and ports", "supported top and controls", "verified use and contact", "verified relative scale"]),
    "home-tools": ("3 panels top, 2 panels bottom", "1024x1024", ["full silhouette", "supported side", "grip and functional part", "verified use and contact", "verified relative scale"]),
    "pet-tools": ("3 panels top, 2 panels bottom", "1024x1024", ["full silhouette", "supported side", "grip and functional part", "verified pet interaction", "verified pet size relation"]),
    "furniture": ("3 panels top, 2 panels bottom", "1024x1024", ["full silhouette", "supported side and frame geometry", "hinge and adjustment detail", "verified use and contact", "verified relative scale"]),
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

STATE_CHANGE_TERMS = (
    "fold", "unfold", "folding", "foldable", "collapse", "collapsible", "deploy", "assemble", "assembly",
    "install", "mount", "attach", "detach", "extend", "retract", "open", "close",
    "telescopic", "retractable", "zip", "unzip", "snap together", "lock into", "折叠", "展开", "收拢", "安装",
    "组装", "拼装", "装配", "连接", "扣合", "伸缩", "拉开", "拉链", "開く", "閉じる",
    "折りたた", "組み立て", "取り付け",
)
STATE_EVIDENCE_LEVELS = {"direct_motion", "instruction_diagram", "state_pair_only"}
STATE_RENDER_POLICIES = {"continuous_allowed", "hard_cut_only", "omit_transition"}


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
    recommended = str(brief.get("recommended_v2_category") or "").strip()
    if recommended == "needs_new_category":
        raise RuntimeError(
            "Product cognition says no built-in v2 category fits this product; add an honest category before identity generation"
        )
    if recommended in SPECS and recommended != category:
        raise RuntimeError(
            f"Category mismatch: category.json selects {category}, but product cognition recommends {recommended}"
        )
    state_change_contract(brief)
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


def _brief_text(brief: dict) -> str:
    """Compact text used only to detect whether a state-change contract is required."""
    fields = (
        brief.get("product_name"), brief.get("product_type"),
        brief.get("confirmed_use_cases"), brief.get("step_by_step_usage"),
        brief.get("confirmed_selling_points"),
    )
    return json.dumps(fields, ensure_ascii=False).lower()


def _detect_state_change(brief: dict) -> bool:
    text = _brief_text(brief)
    for term in STATE_CHANGE_TERMS:
        if term.isascii() and term.replace(" ", "").isalpha():
            if re.search(rf"\b{re.escape(term)}\b", text):
                return True
        elif term in text:
            return True
    return False


def needs_state_change_contract(brief: dict) -> bool:
    raw = brief.get("state_change_contract")
    if isinstance(raw, dict) and "required" in raw:
        return raw.get("required") is True
    return _detect_state_change(brief)


def _source_backed(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text or any(word in text.lower() for word in ("inferen", "guess", "unknown", "推断", "猜测")):
        raise RuntimeError(f"{label} needs explicit source evidence")
    return text


def state_change_contract(brief: dict) -> dict | None:
    """Validate the part/state/transition graph used by deployable products.

    This is deliberately lighter than CAD or URDF. It separates observable endpoint
    states from motion evidence so static listing photos cannot be promoted into an
    invented continuous folding or installation animation.
    """
    raw = brief.get("state_change_contract")
    detected = _detect_state_change(brief)
    if not isinstance(raw, dict):
        if detected:
            raise RuntimeError(
                "This product folds, installs, assembles, opens, closes or otherwise changes state, "
                "but product_brief.json has no state_change_contract; rebuild product cognition first"
            )
        return None
    if raw.get("required") is not True:
        if not str(raw.get("not_applicable_reason") or "").strip():
            raise RuntimeError("state_change_contract.required=false needs a product-specific reason")
        return None

    parts = raw.get("part_invariants")
    states = raw.get("states")
    transitions = raw.get("transitions")
    if not isinstance(parts, list) or not parts:
        raise RuntimeError("state_change_contract.part_invariants must list the parts/counts that cannot drift")
    if not isinstance(states, list) or len(states) < 2:
        raise RuntimeError("state_change_contract.states must contain at least two evidenced endpoint states")
    if not isinstance(transitions, list) or not transitions:
        raise RuntimeError("state_change_contract.transitions must connect the evidenced states")

    clean_parts = []
    for index, part in enumerate(parts, 1):
        if not isinstance(part, dict) or not str(part.get("part") or "").strip():
            raise RuntimeError(f"Part invariant {index} needs a part name")
        count = part.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise RuntimeError(f"Part invariant {index} needs a positive integer count")
        clean_parts.append({**part, "evidence": _source_backed(
            part.get("evidence"), f"Part invariant {index}"
        )})

    connections = raw.get("connections", [])
    if connections is not None and not isinstance(connections, list):
        raise RuntimeError("state_change_contract.connections must be a list")
    clean_connections = []
    for index, connection in enumerate(connections or [], 1):
        linked = connection.get("parts") if isinstance(connection, dict) else None
        if not isinstance(linked, list) or len(linked) < 2 or not all(str(x).strip() for x in linked):
            raise RuntimeError(f"Connection {index} needs at least two named parts")
        if not str(connection.get("type") or "").strip():
            raise RuntimeError(f"Connection {index} needs a connection type")
        clean_connections.append({**connection, "evidence": _source_backed(
            connection.get("evidence"), f"Connection {index}"
        )})

    state_ids: set[str] = set()
    clean_states = []
    for index, state in enumerate(states, 1):
        if not isinstance(state, dict):
            raise RuntimeError(f"State {index} must be an object")
        state_id = str(state.get("state_id") or "").strip()
        if not state_id or state_id in state_ids:
            raise RuntimeError(f"State {index} needs a unique state_id")
        state_ids.add(state_id)
        visible = str(state.get("visible_configuration") or "").strip()
        if not visible:
            raise RuntimeError(f"State {state_id} needs visible_configuration")
        clean_states.append({**state, "state_id": state_id,
                             "evidence": _source_backed(state.get("evidence"), f"State {state_id}")})

    clean_transitions = []
    for index, transition in enumerate(transitions, 1):
        if not isinstance(transition, dict):
            raise RuntimeError(f"Transition {index} must be an object")
        transition_id = str(transition.get("transition_id") or f"transition-{index}").strip()
        from_state = str(transition.get("from_state") or "").strip()
        to_state = str(transition.get("to_state") or "").strip()
        if from_state not in state_ids or to_state not in state_ids or from_state == to_state:
            raise RuntimeError(f"Transition {transition_id} must connect two different declared states")
        evidence_level = str(transition.get("evidence_level") or "").strip()
        if evidence_level not in STATE_EVIDENCE_LEVELS:
            raise RuntimeError(
                f"Transition {transition_id} evidence_level must be one of {sorted(STATE_EVIDENCE_LEVELS)}"
            )
        render_policy = str(transition.get("render_policy") or "").strip()
        if render_policy not in STATE_RENDER_POLICIES:
            raise RuntimeError(
                f"Transition {transition_id} render_policy must be one of {sorted(STATE_RENDER_POLICIES)}"
            )
        if evidence_level == "state_pair_only" and render_policy == "continuous_allowed":
            raise RuntimeError(
                f"Transition {transition_id} has endpoint evidence only and cannot allow continuous animation; "
                "use hard_cut_only or omit_transition"
            )
        evidence = _source_backed(transition.get("evidence"), f"Transition {transition_id}")
        forbidden = transition.get("forbidden_intermediates")
        if not isinstance(forbidden, list) or not forbidden or not all(str(item).strip() for item in forbidden):
            raise RuntimeError(f"Transition {transition_id} needs forbidden_intermediates")
        if evidence_level in {"direct_motion", "instruction_diagram"}:
            for field in ("actor_action", "contact_points", "moving_parts", "fixed_parts", "completion_cue"):
                if not transition.get(field):
                    raise RuntimeError(f"Transition {transition_id} with motion evidence needs {field}")
        clean_transitions.append({**transition, "transition_id": transition_id,
                                  "from_state": from_state, "to_state": to_state,
                                  "evidence_level": evidence_level, "render_policy": render_policy,
                                  "evidence": evidence})

    connected_states = {
        state_id for transition in clean_transitions
        for state_id in (transition["from_state"], transition["to_state"])
    }
    if connected_states != state_ids:
        missing = sorted(state_ids - connected_states)
        raise RuntimeError(f"Every declared state must participate in a transition; disconnected: {missing}")
    return {**raw, "part_invariants": clean_parts, "states": clean_states,
            "transitions": clean_transitions, "connections": clean_connections}


def state_change_panel_plan(contract: dict) -> list[dict]:
    """Build an evidence-safe plan: endpoint states always, motion only when evidenced."""
    transitions_by_from: dict[str, list[dict]] = {}
    for transition in contract["transitions"]:
        transitions_by_from.setdefault(transition["from_state"], []).append(transition)
    panels: list[dict] = []
    for state in contract["states"]:
        panels.append({"kind": "state", "state_id": state["state_id"],
                       "visible_configuration": state["visible_configuration"],
                       "evidence": state["evidence"]})
        for transition in transitions_by_from.get(state["state_id"], []):
            if transition["render_policy"] == "continuous_allowed":
                panels.append({"kind": "evidenced_transition", "transition_id": transition["transition_id"],
                               "actor_action": transition["actor_action"],
                               "contact_points": transition["contact_points"],
                               "moving_parts": transition["moving_parts"],
                               "fixed_parts": transition["fixed_parts"],
                               "completion_cue": transition["completion_cue"],
                               "evidence": transition["evidence"]})
    if len(panels) > 6:
        raise RuntimeError("State-change reference needs more than six panels; simplify it to the advertised transition")
    return panels


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
    if usage.get("mode") == "state_change_sheet" and not usage.get("state_change_contract"):
        raise RuntimeError("State-change usage manifest is missing its validated contract")
    return usage


def guidance(folder: Path) -> str:
    if not active(folder):
        return ""
    record = load_identity(folder)
    usage = load_usage(folder)
    transform_guidance = (
        "\nValidated state-change contract: "
        + json.dumps(usage["state_change_contract"], ensure_ascii=False)
        if usage.get("state_change_contract") else ""
    )
    return (RULES + "\nVerified action ledger: " + json.dumps(usage["actions"], ensure_ascii=False)
            + transform_guidance + "\nCategory checks:\n" + category_spec(record["category"])["checks"])


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
    canonical = local_file(folder, record["reference_images"][0])
    refs = [canonical, sheet]
    usage_sheet = local_file(folder, usage["output_path"])
    if usage_sheet != sheet:
        require_qc(folder, [usage_sheet], "usage")
        refs.append(usage_sheet)
    if role == "end":
        start = local_file(folder, f"generated_images/variant-{variant_id:02d}-start.png")
        # The fallback image edit route accepts three inputs. Keep the start scene,
        # real product truth, and state-change sheet; the latter was generated from
        # and is still checked against the current identity grid.
        refs = [start, canonical, usage_sheet] if usage_sheet != sheet else [start, canonical, sheet]
    return refs


def validate_scene_chain(folder: Path, paths: list[Path]) -> None:
    record = load_identity(folder)
    usage = load_usage(folder)
    identity_sheet = local_file(folder, record["output_path"])
    usage_sheet = local_file(folder, usage["output_path"])
    require_qc(folder, [identity_sheet], "identity")
    if usage_sheet != identity_sheet:
        require_qc(folder, [usage_sheet], "usage")
    for path in paths:
        provenance = load_json(path.with_suffix(".provenance.json"), {})
        if provenance.get("sha256") != digest(path):
            raise RuntimeError(f"Missing/current v2 scene provenance: {path.name}; regenerate keyframes")
        refs = provenance.get("references", {})
        identity_current = refs.get(record["output_path"]) == record["sha256"]
        usage_current = refs.get(usage["output_path"]) == usage["sha256"]
        if not identity_current and not (usage_sheet != identity_sheet and usage_current):
            raise RuntimeError(f"Frame {path.name} did not use current identity or state-change sheet")
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

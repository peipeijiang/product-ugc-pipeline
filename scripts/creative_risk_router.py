#!/usr/bin/env python3
"""Choose the lowest-risk useful video direction before prompt generation."""
from __future__ import annotations

import json
import re
from typing import Any


MODEL_ALIASES = {
    "sd2.0": "seedance-2.0",
    "seedance2": "seedance-2.0",
    "seedance-2": "seedance-2.0",
    "seedance-2.0": "seedance-2.0",
    "doubao-seedance-2-0-pro": "seedance-2.0",
    "minimax-h3": "minimax-h3",
    "h3": "minimax-h3",
    "omni-flash": "omni-flash",
    "omni_flash": "omni-flash",
    "omni-fast": "omni-flash",
    "omni_flash-10s-fl": "omni_flash-10s-fl",
    "omni-flash-10s-fl": "omni_flash-10s-fl",
    "veo3.1": "veo3.1",
    "veo-3.1": "veo3.1",
    "veo-3.1-fast-fl": "veo3.1",
}

MODEL_PROFILES = {
    "seedance-2.0": {
        "motion_budget": "moderate creator/camera motion",
        "reference_strategy": "Use one clean identity anchor; add a short motion reference only when it directly shows the exact action.",
    },
    "minimax-h3": {
        "motion_budget": "moderate creator/camera motion",
        "reference_strategy": "Use first/last frames for composition control or a small coherent reference set; avoid conflicting mixed references.",
    },
    "omni-flash": {
        "motion_budget": "low product motion and one gentle camera move",
        "reference_strategy": "Use the chronological storyboard, identity grid and QC-passed operation grid; keep within the three-image adapter limit.",
    },
    "omni_flash-10s-fl": {
        "motion_budget": "low product motion and one gentle camera move between locked endpoints",
        "reference_strategy": "Use exactly the actual preceding last frame and the target last frame, in that order; both endpoints must share invariant wardrobe, SKU and camera fields.",
    },
    "veo3.1": {
        "motion_budget": "one simple supported interaction",
        "reference_strategy": "Use generated first/last frames with the same product topology and scene continuity.",
    },
    "model-agnostic": {
        "motion_budget": "one simple supported interaction",
        "reference_strategy": "Use the smallest coherent reference set that locks product identity and the chosen endpoint state.",
    },
}

# Weights represent generation difficulty, not real-world safety or product quality.
RISK_GROUPS: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("topology_change", 7, (
        "install", "setup", "assemble", "disassemble", "attach", "detach", "connect", "disconnect",
        "insert", "remove", "thread", "lace", "zip", "unzip", "snap", "clip into", "plug in",
        "mount", "splice", "join", "安装", "组装", "拼装", "插入", "插接", "穿入", "连接", "扣合", "拉链",
    )),
    ("configuration_change", 5, (
        "fold", "unfold", "collapse", "deploy", "extend", "retract", "inflate", "deflate",
        "open", "close", "telescop", "折叠", "展开", "收拢", "伸缩", "充气", "放气", "打开", "闭合",
    )),
    ("reversal_or_inversion", 6, (
        "reverse", "invert", "turn inside out", "flip over", "rotate 180", "反转", "翻转", "里外翻", "倒置",
    )),
    ("precision_contact", 4, (
        "align", "slot", "hole", "pin", "screw", "bolt", "buckle", "latch", "hinge", "needle",
        "对齐", "孔位", "螺丝", "螺栓", "卡扣", "锁扣", "铰链", "针",
    )),
    ("material_deformation", 4, (
        "peel", "coat", "press", "squeeze", "stretch", "wrap", "tie", "pour", "cut", "slice",
        "剥", "涂", "按压", "挤压", "拉伸", "缠绕", "打结", "倾倒", "切割",
    )),
    ("multi_object_coordination", 4, (
        "two parts", "multiple parts", "both hands", "simultaneously", "one by one", "多部件", "两个零件", "双手同时", "依次",
    )),
    ("occluded_contact", 3, (
        "behind", "underneath", "inside", "hidden", "遮挡", "背面", "底部", "内部", "隐藏",
    )),
)

POSITIVE_RESULT_TERMS = (
    "comfort", "comfortable", "support", "stable", "compact", "portable", "storage", "organized",
    "clean", "calm", "ready", "result", "finish", "detail", "texture", "capacity", "fit", "lightweight",
    "舒适", "支撑", "稳定", "便携", "收纳", "整洁", "轻量", "成品", "效果", "细节", "容量",
)

HAZARD_LABELS_ZH = {
    "topology_change": "安装/连接结构变化",
    "configuration_change": "展开/折叠状态变化",
    "reversal_or_inversion": "反转/倒置",
    "precision_contact": "精确对位或接触",
    "material_deformation": "材料形变",
    "multi_object_coordination": "多物体协同",
    "occluded_contact": "接触点被遮挡",
}

FORBIDDEN_LABELS_ZH = {
    "continuous installation, assembly, insertion, reversal, folding or topology-changing motion": "连续安装、组装、插入、反转、折叠或其他结构变化",
    "multiple dependent product actions in one generated shot": "在一个生成镜头里连续完成多个相互依赖的产品动作",
    "hands hiding the connection point while product geometry changes": "手遮住连接点时让产品几何结构发生变化",
    "parts appearing, disappearing, multiplying, crossing or passing through each other": "零件凭空出现、消失、增殖、交叉或互相穿透",
    "more than one dependent product action in the same shot": "同一镜头中出现多个相互依赖的产品动作",
}


def _text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).lower()


def _matches(text: str, term: str) -> bool:
    if term.isascii():
        return bool(re.search(rf"(?<!\w){re.escape(term)}", text))
    return term in text


def action_hazards(value: Any) -> list[dict[str, Any]]:
    text = _text(value)
    hazards = []
    for name, weight, terms in RISK_GROUPS:
        hits = sorted({term for term in terms if _matches(text, term)})
        if hits:
            hazards.append({"type": name, "weight": weight, "signals": hits[:8]})
    return hazards


def _flatten_candidates(brief: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in (
        "confirmed_selling_points",
        "manifest_selling_points",
        "proof_moments",
        "confirmed_use_cases",
        "recommended_ugc_scenes",
    ):
        value = brief.get(key)
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                item = (
                    item.get("description")
                    or item.get("use_case")
                    or item.get("benefit")
                    or item.get("selling_point")
                    or item.get("action")
                    or item.get("text")
                )
            text = " ".join(str(item or "").split())
            if text and text not in candidates:
                candidates.append(text)
    return candidates


def rank_video_directions(brief: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = []
    for order, direction in enumerate(_flatten_candidates(brief)):
        hazards = action_hazards(direction)
        risk = sum(item["weight"] for item in hazards)
        result_bonus = 2 if any(term in direction.lower() for term in POSITIVE_RESULT_TERMS) else 0
        score = max(0, risk - result_bonus)
        ranked.append({
            "direction": direction,
            "risk_score": score,
            "hazards": [item["type"] for item in hazards],
            "proof_style": "ready-state result or detail proof" if hazards else "single simple visible proof",
            "source_order": order,
        })
    if not ranked or min(item["risk_score"] for item in ranked) > 0:
        product = str(brief.get("product_name") or brief.get("product_type") or "the product")
        ranked.append({
            "direction": f"Show {product} already in its verified ready-to-use state and make the buyer result visible.",
            "risk_score": 0,
            "hazards": [],
            "proof_style": "ready-state result proof",
            "source_order": 0,
        })
    ranked.sort(key=lambda item: (item["risk_score"], item["source_order"]))
    return [{key: value for key, value in item.items() if key != "source_order"} for item in ranked[:5]]


def normalize_model_profile(model: str) -> str:
    value = str(model or "model-agnostic").strip().lower()
    return MODEL_ALIASES.get(value, value if value in MODEL_PROFILES else "model-agnostic")


def build_video_feasibility_plan(brief: dict[str, Any], model: str = "model-agnostic") -> dict[str, Any]:
    target_model = normalize_model_profile(model)
    procedural_steps = brief.get("step_by_step_usage") or []
    action_evidence = {
        "step_by_step_usage": procedural_steps,
        "confirmed_use_cases": brief.get("confirmed_use_cases") or [],
        "confirmed_selling_points": brief.get("confirmed_selling_points") or [],
        "manifest_selling_points": brief.get("manifest_selling_points") or [],
        "proof_moments": brief.get("proof_moments") or [],
    }
    hazards = action_hazards(action_evidence)
    score = sum(item["weight"] for item in hazards)
    steps = procedural_steps if isinstance(procedural_steps, list) else [procedural_steps]
    if len(steps) > 1:
        score += min(4, len(steps) - 1)

    contract = brief.get("state_change_contract")
    transitions = contract.get("transitions", []) if isinstance(contract, dict) and contract.get("required") is True else []
    if transitions:
        score += min(5, len(transitions) * 2)
        if any(item.get("evidence_level") == "state_pair_only" for item in transitions if isinstance(item, dict)):
            score += 6
        if any(item.get("render_policy") in {"hard_cut_only", "omit_transition"} for item in transitions if isinstance(item, dict)):
            score += 4

    if score >= 14:
        level, strategy = "critical", "result_first_static_reveal"
    elif score >= 9:
        level, strategy = "high", "endpoint_proof_external_cut"
    elif score >= 4:
        level, strategy = "medium", "prepositioned_single_interaction"
    else:
        level, strategy = "low", "single_continuous_demo"

    protect_state = level in {"high", "critical"} or bool(transitions)
    directions = rank_video_directions(brief)
    forbidden = [
        "continuous installation, assembly, insertion, reversal, folding or topology-changing motion",
        "multiple dependent product actions in one generated shot",
        "hands hiding the connection point while product geometry changes",
        "parts appearing, disappearing, multiplying, crossing or passing through each other",
    ] if protect_state else ["more than one dependent product action in the same shot"]
    profile = MODEL_PROFILES[target_model]
    return {
        "target_model": target_model,
        "risk_score": score,
        "risk_level": level,
        "hazards": hazards,
        "recommended_strategy": strategy,
        "ranked_safe_directions": directions,
        "selected_direction": directions[0],
        "continuous_product_state_change_allowed": not protect_state,
        "protect_product_configuration": protect_state,
        "allowed_motion": profile["motion_budget"],
        "reference_strategy": profile["reference_strategy"],
        "forbidden_generation": forbidden,
        "editing_strategy": (
            "Generate only source-backed ready-state shots. Convey setup with a clean edit between separate endpoint assets or real source footage; never ask the video model to invent the missing transition."
            if protect_state else
            "Keep one product, one supported action and one camera move in a continuous shot."
        ),
        "basis": "Conservative cross-model routing; model marketing claims never override product evidence or topology risk.",
    }


def _selected_direction(value: dict[str, Any]) -> str:
    selected = value.get("selected_direction") or value.get("safe_demo_direction") or {}
    if isinstance(selected, dict):
        return str(selected.get("direction") or "source-backed ready-state result").strip()
    return str(selected or "source-backed ready-state result").strip()


def _hazard_summary(hazards: Any) -> str:
    if not isinstance(hazards, list) or not hazards:
        return "none"
    rendered: list[str] = []
    for hazard in hazards:
        if not isinstance(hazard, dict):
            rendered.append(str(hazard))
            continue
        hazard_type = str(hazard.get("type") or "unknown")
        name = HAZARD_LABELS_ZH.get(hazard_type, hazard_type)
        signals = hazard.get("signals") or []
        if isinstance(signals, list) and signals:
            name += f"({','.join(str(item) for item in signals[:4])})"
        rendered.append(name)
    return ", ".join(rendered)


def describe_video_approach(value: dict[str, Any]) -> str:
    """Explain the routed 10-second production approach in user-facing language."""
    generation_risk = value.get("generation_risk") if isinstance(value.get("generation_risk"), dict) else {}
    level = str(value.get("risk_level") or generation_risk.get("level") or "unknown").lower()
    protected = value.get("protect_product_configuration") is True or level in {"high", "critical"}
    if protected:
        return (
            "10秒内让商品始终保持已核验的完成态；开场展示结果，中段只安排一个简单的人物或镜头动作，"
            "结尾用细节、尺度或用户反应证明卖点。安装、折叠或连接过程只使用真实素材，或把独立端点素材在剪辑中硬切。"
        )
    if level == "medium":
        return "先把商品摆到可演示状态；10秒内只展示一个简单交互和一个镜头运动，其余步骤拆到独立素材或剪辑中。"
    return "用10秒连续镜头展示一个有依据的简单动作和一个镜头运动，全程保持商品身份、零件和结构一致。"


def format_feasibility_notice(product_name: str, plan: dict[str, Any]) -> list[str]:
    """Return concise console lines that expose the assessment before scripting."""
    protected = "是" if plan.get("protect_product_configuration") else "否"
    return [
        (
            f"[risk] 产品={product_name} 目标模型={plan.get('target_model', 'model-agnostic')} "
            f"风险={plan.get('risk_level', 'unknown')} 分数={plan.get('risk_score', 0)} 固定商品结构={protected}"
        ),
        f"[risk] 触发因素={_hazard_summary(plan.get('hazards'))}",
        f"[video-plan] 准备这样制作：{describe_video_approach(plan)}",
        f"[video-plan] 主展示方向={_selected_direction(plan)}",
    ]


def format_production_notice(
    product_name: str,
    variant_id: int,
    variant: dict[str, Any],
    model: str,
    reference_mode: str,
    reference_images: list[Any],
) -> list[str]:
    """Return the actual routed plan immediately before a paid video request."""
    risk = variant.get("generation_risk") if isinstance(variant.get("generation_risk"), dict) else {}
    level = str(risk.get("level") or "unknown")
    score = risk.get("score", "unknown")
    protected = "是" if variant.get("protect_product_configuration") else "否"
    references = ", ".join(getattr(item, "name", str(item)) for item in reference_images) or "none"
    lines = [
        (
            f"[video-plan] 即将制作 产品={product_name} 变体={variant_id:02d} 模型={model} "
            f"风险={level} 分数={score} 固定商品结构={protected}"
        ),
        f"[video-plan] 实际拍法={describe_video_approach(variant)}",
        f"[video-plan] 主展示方向={_selected_direction(variant)}",
        f"[video-plan] 参考模式={reference_mode} 参考图={references}",
    ]
    omitted = variant.get("unsafe_actions_omitted") or []
    if isinstance(omitted, list) and omitted:
        rendered = [FORBIDDEN_LABELS_ZH.get(str(item), str(item)) for item in omitted]
        lines.append(f"[video-plan] 不让视频模型生成={'; '.join(rendered)}")
    return lines


def apply_feasibility_route(variant: dict[str, Any], plan: dict[str, Any], index: int = 0) -> dict[str, Any]:
    clean = dict(variant)
    directions = plan.get("ranked_safe_directions") or [plan.get("selected_direction") or {}]
    minimum_risk = min((item.get("risk_score", 0) for item in directions), default=0)
    safest = [item for item in directions if item.get("risk_score", 0) == minimum_risk]
    selected = safest[index % len(safest)] if safest else {}
    clean["generation_risk"] = {
        "level": plan.get("risk_level"),
        "score": plan.get("risk_score"),
        "hazards": plan.get("hazards", []),
    }
    clean["safe_demo_direction"] = selected
    clean["editing_strategy"] = plan.get("editing_strategy")
    clean["unsafe_actions_omitted"] = plan.get("forbidden_generation", [])
    clean["protect_product_configuration"] = bool(plan.get("protect_product_configuration"))
    clean["continuous_product_state_change_allowed"] = bool(plan.get("continuous_product_state_change_allowed"))
    clean["allowed_motion"] = plan.get("allowed_motion")
    clean["reference_strategy"] = plan.get("reference_strategy")
    if not plan.get("protect_product_configuration"):
        return clean

    direction = selected.get("direction") or "the source-backed buyer result"
    product_state_rule = (
        "The product is already in one verified ready-to-use configuration before the generated clip begins. "
        "Its topology, connections and part inventory never change on camera."
    )
    clean["product_intervention"] = "Show the verified ready-state product in use without depicting its setup mechanism."
    clean["usage_logic"] = f"{product_state_rule} Direction: {direction}"
    clean["proof_moment"] = f"A clear source-backed ready-state or detail shot proves: {direction}"
    if isinstance(clean.get("benefit_ladder"), dict):
        clean["benefit_ladder"] = {
            **clean["benefit_ladder"],
            "product_intervention": clean["product_intervention"],
            "proof_moment": clean["proof_moment"],
        }
    clean["shot_plan"] = [
        {"time": "0-3s", "visual": "Open on the buyer need with the complete ready-state product already clearly visible; no setup motion."},
        {"time": "3-7s", "visual": f"Use one simple human or camera motion while product geometry stays fixed. Show: {direction}"},
        {"time": "7-10s", "visual": "Hold on the unchanged product and the buyer-visible result; use a detail or reaction as proof."},
    ]
    clean["storyboard_10s"] = [dict(item, spoken="", overlay="") for item in clean["shot_plan"]]
    clean.pop("storyboard_8s", None)
    return clean

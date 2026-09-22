#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import load_json, request_json, require_api_key_for_base_url, selected_product_dirs, write_json
from creative_risk_router import (
    apply_feasibility_route,
    build_video_feasibility_plan,
    format_feasibility_notice,
)
from voice_locale import (
    VoiceLocaleError,
    language_clause,
    language_name,
    max_voiceover_chars,
    normalize_locale,
    resolve_voice_locale,
    script_matches,
    script_of,
    trim_voiceover,
    voice_description,
)


UGC_SYSTEM_PROMPT = """You are a senior UGC creative director and ecommerce offer strategist for short-form product video.
Before writing scenes, identify the buyer's core reason to buy, then turn it into a product-faithful vertical creator ad that sells the result, uses natural native audio, and preserves strict product continuity. Return JSON only."""

VOICEOVER_SEGMENTS = [("0-3s", 8), ("3-7s", 11), ("7-10s", 8)]
VOICEOVER_TARGET_WORDS = (18, 22)
VOICEOVER_HARD_MAX_WORDS = 25
SHOT_TIME_SLOTS = {
    3: ["0.0-3.0s", "3.0-7.0s", "7.0-10.0s"],
    4: ["0.0-2.0s", "2.0-5.0s", "5.0-8.0s", "8.0-10.0s"],
    5: ["0.0-2.0s", "2.0-4.0s", "4.0-6.5s", "6.5-8.5s", "8.5-10.0s"],
    6: ["0.0-1.5s", "1.5-3.0s", "3.0-4.5s", "4.5-6.5s", "6.5-8.5s", "8.5-10.0s"],
}

CREATIVE_MATRIX_ARCHETYPES = [
    {
        "hook_archetype": "timestamp pain hook",
        "buyer_context": "wide awake at an oddly specific late-night time",
        "creator_persona": "relatable tired creator speaking directly to camera",
        "scene_type": "bedroom problem-first scene",
        "story_shape": "problem confession -> product intervention -> visible relief",
        "proof_style": "before/after emotional contrast",
        "camera_idea": "handheld close-up from pillow or nightstand height",
        "pace": "fast hook, soft payoff",
    },
    {
        "hook_archetype": "bad habit interruption",
        "buyer_context": "phone scrolling, binge watching, snacking, procrastinating, or repeated failed setup",
        "creator_persona": "self-aware creator with light humor",
        "scene_type": "habit loop broken by product action",
        "story_shape": "caught in habit -> decisive cut -> product routine -> result",
        "proof_style": "object left behind while product stays in use",
        "camera_idea": "quick cut from bad habit prop to product close-up",
        "pace": "snappy social-ad pacing",
    },
    {
        "hook_archetype": "skeptic-to-believer reversal",
        "buyer_context": "creator doubts the product, then notices the buyer-visible result",
        "creator_persona": "skeptical reviewer or friend-recommendation tester",
        "scene_type": "mini test/review in a real home setting",
        "story_shape": "skeptical line -> try one supported action -> surprised payoff",
        "proof_style": "reaction shot plus product proof shot",
        "camera_idea": "talk-to-camera opener, then macro product detail",
        "pace": "review-style with a twist",
    },
    {
        "hook_archetype": "challenge or timed test",
        "buyer_context": "creator runs a simple one-night, one-minute, or seven-night test",
        "creator_persona": "curious experimenter",
        "scene_type": "timer/checklist/challenge setup without platform UI",
        "story_shape": "challenge setup -> product use -> measurable-feeling payoff",
        "proof_style": "timer/checklist prop or next-moment contrast",
        "camera_idea": "timer prop, over-shoulder setup, then final close-up",
        "pace": "structured test pacing",
    },
    {
        "hook_archetype": "social comparison hook",
        "buyer_context": "partner, roommate, friend, pet, parent, or coworker has the opposite experience",
        "creator_persona": "creator reacting to someone else already succeeding",
        "scene_type": "two-person or social-context scene",
        "story_shape": "comparison frustration -> product routine -> creator catches up",
        "proof_style": "other person remains undisturbed while creator improves",
        "camera_idea": "split-depth composition with second person in background",
        "pace": "comedic contrast into calm proof",
    },
    {
        "hook_archetype": "travel or unfamiliar-place problem",
        "buyer_context": "hotel, trip, car console, airport bag, guest room, dorm, or new apartment",
        "creator_persona": "travel/lifestyle creator",
        "scene_type": "portable problem-solving scene",
        "story_shape": "new place problem -> product from bag -> use -> settled payoff",
        "proof_style": "packed bag or unfamiliar room turns into comfortable routine",
        "camera_idea": "bag pull-out hero shot, then same-location final proof",
        "pace": "travel hack pacing",
    },
    {
        "hook_archetype": "messy real-life chaos",
        "buyer_context": "after work, busy parent night, rushed morning, cluttered kitchen, laundry pile, or desk chaos",
        "creator_persona": "busy everyday creator",
        "scene_type": "chaotic environment made simpler by one product action",
        "story_shape": "chaos -> one practical action -> calmer or cleaner outcome",
        "proof_style": "same scene visibly simplified or calmer",
        "camera_idea": "wide chaos establishing shot into tight product action",
        "pace": "high-energy opening, satisfying finish",
    },
    {
        "hook_archetype": "ASMR/sensory payoff",
        "buyer_context": "quiet tactile routine where sound, texture, movement, or light is satisfying",
        "creator_persona": "soft-spoken sensory creator",
        "scene_type": "close tactile product-use scene",
        "story_shape": "sensory hook -> precise product action -> satisfying final state",
        "proof_style": "audible/tactile/visual micro-proof",
        "camera_idea": "macro hands, shallow depth of field, minimal props",
        "pace": "slow satisfying cadence",
    },
    {
        "hook_archetype": "gift or impulse-buy angle",
        "buyer_context": "unboxing, gift table, vanity, entryway, or friend recommendation",
        "creator_persona": "gift-guide or 'things I actually use' creator",
        "scene_type": "unbox-to-real-use scene",
        "story_shape": "cute object reveal -> practical use -> kept using it payoff",
        "proof_style": "packaging/first impression contrasted with real result",
        "camera_idea": "unboxing hand shot, then lifestyle final frame",
        "pace": "polished gift-guide pacing",
    },
    {
        "hook_archetype": "problem nobody talks about",
        "buyer_context": "specific overlooked pain point tied to the product category",
        "creator_persona": "confessional creator naming a niche but relatable issue",
        "scene_type": "intimate confession plus practical demo",
        "story_shape": "niche confession -> product solves one small friction -> emotional payoff",
        "proof_style": "creator reaction shows relief more than technical specs",
        "camera_idea": "close face hook, then product action in same scene",
        "pace": "quiet but emotionally sticky",
    },
]


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


def creative_matrix_plan(count: int, existing_history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Return a creative distribution plan for a batch.

    This is intentionally not a keyword-extraction fallback. It is a creative
    contract passed into the prompt model: keep the core selling promise fixed,
    but force each variant to vary story shape, buyer context, persona, scene,
    proof style, camera idea, and pacing.
    """
    history = existing_history or []
    history_tags = [
        {
            "scene": infer_scene_tag(item),
            "action": infer_action_tag(item),
            "angle": infer_angle_tag(item),
            "style": infer_style_tag(item),
            "pace": infer_pace_tag(item),
        }
        for item in history[:24]
        if isinstance(item, dict)
    ]
    plan: list[dict[str, Any]] = []
    for index in range(count):
        archetype = dict(CREATIVE_MATRIX_ARCHETYPES[index % len(CREATIVE_MATRIX_ARCHETYPES)])
        archetype["slot_id"] = index + 1
        archetype["must_share_core_selling_claim"] = True
        archetype["must_differ_from_other_slots_on"] = [
            "hook_archetype",
            "buyer_context",
            "creator_persona",
            "scene_type",
            "story_shape",
            "proof_style",
            "camera_idea",
            "pace",
        ]
        if history_tags:
            archetype["avoid_history_tags"] = history_tags[:12]
        plan.append(archetype)
    return plan


def _clean_spoken_text(text: str) -> str:
    cleaned = re.sub(r"[\[\]\{\}\"“”]", " ", text or "")
    cleaned = re.sub(r"^\s*(?:\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?\s*s?|[0-9]+\s*[-–]\s*[0-9]+\s*seconds?)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
    return cleaned


def _trim_to_words(text: str, max_words: int) -> str:
    words = _clean_spoken_text(text).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(" ,.-")


def derive_sku_colourway(manifest: dict[str, Any], product_brief: dict[str, Any] | None = None) -> str:
    """Return a single pinned SKU/colourway label, or an empty string.

    An absent value used to render a blank "MANDATORY SKU FOR THIS VIDEO: ."
    clause. Returning an empty string lets the adapter omit the clause instead.
    """
    brief = product_brief if isinstance(product_brief, dict) else {}
    identity = brief.get("confirmed_identity")
    if isinstance(identity, dict):
        for key in ("colourway", "colorway", "colour", "color", "variant", "sku_name", "sku"):
            value = identity.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("sku_colourway", "colourway", "colorway", "sku_name", "selected_sku"):
        value = brief.get(key) or manifest.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(identity, str) and identity.strip():
        return identity.strip()
    skus = manifest.get("skus")
    if isinstance(skus, list) and skus:
        names: list[str] = []
        for item in skus:
            if not isinstance(item, dict):
                continue
            for key in ("sku_name", "sku_property_value_name", "name", "property_value_name"):
                value = item.get(key)
                if isinstance(value, str) and value.strip() and value.strip() not in names:
                    names.append(value.strip())
        # Only pin a colourway when the listing has exactly one; a multi-SKU
        # listing must stay unpinned rather than locking an arbitrary SKU.
        if len(names) == 1:
            return names[0]
    return ""


def validate_voiceover_language(variant: dict[str, Any], locale: str, product_name: str) -> None:
    """Reject a voiceover written in the wrong script for the target market.

    This is the gate that would have caught an English script shipped to a
    Japanese market instead of paying for a video in the wrong language.
    """
    if script_of(locale) == "latin":
        return
    lines = variant.get("voiceover_script_10s") or []
    spoken = " ".join(
        str(item.get("line") or "") if isinstance(item, dict) else str(item) for item in lines
    ).strip()
    if not spoken:
        raise VoiceLocaleError(
            f"{product_name} variant {variant.get('variant_id')}: no spoken line for {language_name(locale)}. "
            "Refusing to submit a clip with an empty voiceover."
        )
    if not script_matches(spoken, locale):
        raise VoiceLocaleError(
            f"{product_name} variant {variant.get('variant_id')}: the voiceover is not written in "
            f"{language_name(locale)} (locale {locale}) but the ad targets that market. "
            f"Rewrite the spoken lines in {language_name(locale)} before generating video. "
            f"Offending line: {spoken[:120]!r}"
        )


def _trim_line_for_locale(text: str, max_words: int, locale: str | None) -> str:
    """Trim a spoken line without leaving a dangling fragment.

    `_trim_to_words` cut the tail word-by-word, so a long line shipped as
    "...you get the" and a Japanese line was counted as a single word because
    it has no spaces. Latin lines now drop whole trailing clauses, and
    non-Latin lines are budgeted by characters.
    """
    cleaned = _clean_spoken_text(text)
    resolved = normalize_locale(locale)
    if not resolved:
        return _trim_to_words(cleaned, max_words)
    if script_of(resolved) != "latin":
        budget = max(12, int(round(max_voiceover_chars(resolved) * max_words / max(1, VOICEOVER_HARD_MAX_WORDS))))
        return trim_voiceover(cleaned, resolved, max_chars=budget)
    words = cleaned.split()
    if len(words) <= max_words:
        return " ".join(words)
    clauses = [part for part in re.split(r"(?<=[,;:.!?])\s+", cleaned) if part.strip()]
    while len(clauses) > 1 and len(" ".join(clauses).split()) > max_words:
        clauses.pop()
    result = " ".join(clauses).strip()
    # A single clause can still exceed the slot. Keeping it whole reads far
    # better than the old truncated fragment, and the model is separately
    # instructed to stay inside the slot budget.
    return result.rstrip(" ,;-") + ("." if result and result[-1] not in ".!?" else "")


def normalize_voiceover_script_10s(
    raw_voiceover: Any,
    hook: str = "",
    fallback: str = "",
    locale: str | None = None,
) -> list[dict[str, str]]:
    collected: list[str] = []
    if isinstance(raw_voiceover, dict):
        for time_slot, _ in VOICEOVER_SEGMENTS:
            text = str(raw_voiceover.get(time_slot) or "").strip()
            if text:
                collected.append(text)
        if not collected:  # Read legacy/custom time-slot dictionaries, then rewrite them to the 10-second contract.
            collected = [str(value).strip() for value in raw_voiceover.values() if str(value).strip()]
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
        line = _trim_line_for_locale(source, max_words, locale)
        if not line:
            line = _trim_line_for_locale(fallback_lines[index], max_words, locale)
        normalized.append({"time": time_slot, "line": line})
    resolved = normalize_locale(locale)
    latin = (not resolved) or script_of(resolved) == "latin"
    total_words = sum(len(item["line"].split()) for item in normalized)
    # Non-Latin scripts are not word-delimited, so the word-count overflow pass
    # used to misfire on Japanese. Budget those by characters instead.
    total_units = total_words if latin else sum(len(item["line"]) for item in normalized)
    hard_max = VOICEOVER_HARD_MAX_WORDS if latin else max_voiceover_chars(resolved) if resolved else VOICEOVER_HARD_MAX_WORDS
    if total_units > hard_max:
        overflow = total_units - hard_max
        for item in reversed(normalized):
            if latin:
                words = item["line"].split()
                removable = max(0, len(words) - 4)
                if removable <= 0:
                    continue
                cut = min(removable, overflow)
                remaining = " ".join(words[:-cut])
                # Prefer dropping whole trailing clauses; only fall back to a
                # word cut when a single clause is already over the budget.
                clauses = [part for part in re.split(r"(?<=[,;:.!?])\s+", remaining) if part.strip()]
                while len(clauses) > 1 and len(" ".join(clauses).split()) > len(words) - cut:
                    clauses.pop()
                rebuilt = " ".join(clauses).strip().rstrip(" ,;-")
                item["line"] = rebuilt + ("." if rebuilt and rebuilt[-1] not in ".!?" else "")
                overflow -= cut
            else:
                room = max(0, len(item["line"]) - 8)
                if room <= 0:
                    continue
                cut = min(room, overflow)
                item["line"] = trim_voiceover(item["line"], resolved, max_chars=max(8, len(item["line"]) - cut))
                overflow -= cut
            if overflow <= 0:
                break
    return normalized


def compact_voiceover_text(raw_voiceover: Any) -> str:
    normalized = normalize_voiceover_script_10s(raw_voiceover)
    return " ".join(item["line"] for item in normalized if item.get("line")).strip()


def _shot_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("shot") or item.get("visual") or item.get("description") or item.get("text") or "").strip()
    return str(item or "").strip()


def normalize_shot_plan_10s(raw_shot_plan: Any, variant: dict[str, Any]) -> list[dict[str, str]]:
    raw_items = raw_shot_plan if isinstance(raw_shot_plan, list) else []
    shots = [_shot_text(item) for item in raw_items]
    shots = [shot for shot in shots if shot][:9]
    if len(shots) < 3:
        shots = [
            f"Hook setup: {variant.get('hook') or variant.get('title') or 'show the buyer problem or need'}",
            f"Product close-up: show the exact product identity and the main functional surface for {variant.get('primary_function_focus') or variant.get('selling_angle') or 'the core function'}",
            f"Action demo: {variant.get('usage_logic') or 'perform one supported use action with the product clearly visible'}",
            f"Proof moment: {variant.get('proof_moment') or 'show the practical result clearly'}",
            "Final sell shot: keep the product visible in hand or beside the result",
        ]
    shot_count = min(max(len(shots), 3), 9)
    slots = SHOT_TIME_SLOTS.get(shot_count) or [f"{10*i/shot_count:.2f}-{10*(i+1)/shot_count:.2f}s" for i in range(shot_count)]
    normalized: list[dict[str, str]] = []
    for index, shot in enumerate(shots[:shot_count]):
        normalized.append({"time": slots[index], "shot": shot})
    return normalized


def _slot_start_seconds(time_slot: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)", time_slot or "")
    return float(match.group(1)) if match else 0.0


def _slot_bounds(time_slot: str) -> tuple[float, float]:
    values = re.findall(r"(\d+(?:\.\d+)?)", time_slot or "")
    if not values:
        return 0.0, 0.0
    start = float(values[0])
    end = float(values[1]) if len(values) > 1 else start
    return start, end


def assign_spoken_lines_to_shots(shot_plan: list[dict[str, str]], voiceover: list[dict[str, str]]) -> dict[int, str]:
    assignments: dict[int, str] = {}
    for voice_item in voiceover:
        line = str(voice_item.get("line") or "").strip()
        if not line:
            continue
        voice_start, voice_end = _slot_bounds(str(voice_item.get("time") or ""))
        chosen_index: int | None = None
        for index, shot in enumerate(shot_plan):
            shot_start, shot_end = _slot_bounds(str(shot.get("time") or ""))
            overlaps = shot_start < voice_end and shot_end > voice_start
            if overlaps:
                chosen_index = index
                break
        if chosen_index is None:
            chosen_index = min(range(len(shot_plan)), key=lambda index: abs(_slot_start_seconds(str(shot_plan[index].get("time") or "")) - voice_start)) if shot_plan else None
        if chosen_index is None:
            continue
        existing = assignments.get(chosen_index)
        assignments[chosen_index] = f"{existing} {line}".strip() if existing else line
    return assignments


def storyboard_entries(variant: dict[str, Any]) -> list[dict[str, str]]:
    if variant.get("storyboard_10s"):
        return [dict(entry) for entry in variant["storyboard_10s"]]
    shot_plan = normalize_shot_plan_10s(variant.get("shot_plan"), variant)
    # `_8s` is read-only migration support; normalized output is always `_10s`.
    voiceover = normalize_voiceover_script_10s(
        variant.get("voiceover_script_10s") or variant.get("voiceover_script_8s"),
        hook=str(variant.get("hook") or ""),
    )
    callouts = normalize_on_screen_callouts(variant.get("on_screen_callouts"), str(variant.get("selling_angle") or variant.get("usage_logic") or ""))
    spoken_assignments = assign_spoken_lines_to_shots(shot_plan, voiceover)
    entries: list[dict[str, str]] = []
    for index, shot in enumerate(shot_plan):
        overlay = callouts[min(index, len(callouts) - 1)] if callouts and index < 2 else ""
        entries.append(
            {
                "time": str(shot.get("time") or ""),
                "visual": str(shot.get("shot") or ""),
                "spoken": spoken_assignments.get(index, ""),
                "overlay": overlay,
            }
        )
    return entries


def format_storyboard_for_prompt(variant: dict[str, Any]) -> str:
    lines: list[str] = []
    for entry in storyboard_entries(variant):
        spoken = entry.get("spoken") or "none"
        overlay = entry.get("overlay") or "none"
        lines.append(
            f"[{entry.get('time')}] Visual: {entry.get('visual')}. Spoken: {spoken}. Overlay: {overlay}."
        )
    return " ".join(lines)


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


def assert_clean_generation_inputs(product_dir: Path, image_analysis: dict[str, Any], product_brief: dict[str, Any]) -> None:
    if not image_analysis or not isinstance(image_analysis.get("images"), list) or not image_analysis.get("images"):
        raise RuntimeError(f"{product_dir.name}: missing or empty image_analysis.json. Run successful vision analysis first.")
    failed = [
        item.get("local_path", "unknown")
        for item in image_analysis.get("images", [])
        if (item.get("analysis") or {}).get("error")
    ]
    if failed:
        raise RuntimeError(
            f"{product_dir.name}: image_analysis.json contains failed model outputs for {failed}. "
            "Refusing to generate prompts from invalid visual cognition."
        )
    if not product_brief:
        raise RuntimeError(f"{product_dir.name}: missing product_brief.json. Run successful product-brief synthesis first.")
    required_brief_keys = ["confirmed_identity", "confirmed_use_cases", "step_by_step_usage", "misuse_risks_to_avoid"]
    missing = [key for key in required_brief_keys if not product_brief.get(key)]
    if missing:
        raise RuntimeError(
            f"{product_dir.name}: product_brief.json is missing required cognition fields {missing}. "
            "Refusing to generate prompts until the product function is understood."
        )


def parse_json_text(text: str, context: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise RuntimeError(f"{context}: empty model content")
    stripped = re.sub(r"<think>.*?</think>", "", stripped, flags=re.DOTALL).strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    elif not stripped.startswith("{"):
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
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


def normalize_variants(
    output: dict[str, Any],
    manifest: dict[str, Any],
    references: list[str],
    count: int,
    product_brief: dict[str, Any] | None = None,
    creative_matrix: list[dict[str, Any]] | None = None,
    voice_locale: str | None = None,
    market: str = "",
) -> dict[str, Any]:
    product_name = manifest["product_name"]
    resolved_locale = normalize_locale(voice_locale)
    if not resolved_locale:
        raise VoiceLocaleError(
            f"normalize_variants needs a resolved voice locale for {product_name}; refusing to assume English."
        )
    feature_summary = product_function_summary(manifest, product_brief)
    sku_colourway = derive_sku_colourway(manifest, product_brief)
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
        # Persist the market contract on every variant so downstream adapter and
        # montage steps never have to guess the spoken language, and so an empty
        # colourway cannot render a blank "MANDATORY SKU" clause.
        clean_variant["voice_locale"] = resolved_locale
        clean_variant["market"] = market or clean_variant.get("market") or ""
        clean_variant["voice_locale_source"] = "prompt_batch"
        if sku_colourway and not str(clean_variant.get("sku_colourway") or "").strip():
            clean_variant["sku_colourway"] = sku_colourway
        matrix_index = len(normalized)
        if creative_matrix and matrix_index < len(creative_matrix):
            clean_variant.setdefault("creative_matrix_slot", creative_matrix[matrix_index])
        clean_variant["selected_reference_images"] = references[:2]
        clean_variant.setdefault("reference_scope", reference_scope_note(references))
        clean_variant.setdefault("scene_imagination", build_scene_imagination(clean_variant, product_brief))
        clean_variant.setdefault("selling_angle", infer_selling_angle(clean_variant, feature_summary))
        benefit_ladder = build_benefit_ladder(clean_variant, manifest, feature_summary, product_brief)
        clean_variant["benefit_ladder"] = benefit_ladder
        clean_variant.setdefault("core_selling_claim", benefit_ladder["core_selling_claim"])
        clean_variant.setdefault("buyer_problem", benefit_ladder["buyer_problem"])
        clean_variant.setdefault("product_intervention", benefit_ladder["product_intervention"])
        clean_variant.setdefault("buyer_result", benefit_ladder["buyer_result"])
        if not str(clean_variant.get("buyer_effect") or "").strip():
            clean_variant["buyer_effect"] = benefit_ladder["buyer_result"]
        feasibility_plan = (product_brief or {}).get("video_feasibility_plan") or {}
        if feasibility_plan:
            clean_variant = apply_feasibility_route(clean_variant, feasibility_plan, matrix_index)
        clean_variant.setdefault("negative_prompt", "Do not alter product geometry, color, material, logo/text, silhouette, or invent extra parts.")
        clean_variant.setdefault("function_intro_prompt", build_function_intro_prompt(product_name, feature_summary, clean_variant.get("hook", "")))
        clean_variant["voiceover_script_10s"] = normalize_voiceover_script_10s(
            clean_variant.get("voiceover_script_10s") or clean_variant.get("voiceover_script_8s"),
            hook=str(clean_variant.get("hook") or ""),
            fallback=build_voiceover_script_10s(product_name, feature_summary, clean_variant.get("hook", ""))[1]["line"],
            locale=resolved_locale,
        )
        validate_voiceover_language(clean_variant, resolved_locale, product_name)
        clean_variant.pop("voiceover_script_8s", None)
        clean_variant["on_screen_callouts"] = normalize_on_screen_callouts(clean_variant.get("on_screen_callouts"), feature_summary)
        clean_variant["storyboard_10s"] = storyboard_entries(clean_variant)
        from storyboard_contract import storyboard_spec
        clean_variant["grid_spec"] = storyboard_spec(clean_variant)
        clean_variant["shot_plan"] = [{"time": b["time"], "shot": b["visual"]} for b in clean_variant["storyboard_10s"]]
        clean_variant.pop("storyboard_8s", None)
        clean_variant.setdefault("function_demo_prompt", build_function_demo_prompt(product_name, feature_summary, clean_variant.get("title", "")))
        fidelity = product_fidelity_block(product_name, product_brief)
        image_prompt = str(clean_variant.get("image_prompt") or "")
        video_prompt = str(clean_variant.get("video_prompt") or "")
        if "CANONICAL PRODUCT" not in image_prompt:
            image_prompt = fidelity + ("\n" + image_prompt if image_prompt else "")
        if "CANONICAL PRODUCT" not in video_prompt:
            video_prompt = fidelity + ("\n" + video_prompt if video_prompt else "")
        # Drop legacy scene-endpoint fields so older history files cannot leak
        # them into a new prompt batch.
        clean_variant.pop("start_frame_prompt", None)
        clean_variant.pop("end_frame_prompt", None)
        clean_variant["image_prompt"] = strict_pad_image_prompt(product_name, clean_variant, product_brief)
        clean_variant["video_prompt"] = usage_demo_video_prompt(clean_variant, product_brief, resolved_locale)
        clean_variant["video_prompt_strategy"] = "omni_reference_storyboard_identity"
        normalized.append(clean_variant)
    output["product_name"] = output.get("product_name") or product_name
    output["variants"] = normalized
    if creative_matrix:
        output["creative_matrix"] = creative_matrix
    output["variant_count_requested"] = count
    output["variant_count_returned_by_model"] = len(variants)
    output["variant_count_final"] = len(normalized)
    return output


def build_hallucination_defense_block(product_brief: dict[str, Any] | None = None) -> str:
    """Build a product-specific hallucination defense block from product_brief.json.
    Returns a universal defense even if brief is None."""
    brief = product_brief or {}
    defense = brief.get('hallucination_defense') or {}

    # Universal baseline — covers common image/video hallucination categories.
    base = (
        'HALLUCINATION DEFENSE (universal): '
        'Do not add, invent, redesign, or hallucinate ANY of the following unless explicitly visible in the reference image: '
        'cables, wires, cords, hoses, tubes, pipes. '
        'motors, engines, fans, spinning parts unless shown. '
        'buttons, switches, knobs, dials, sliders. '
        'lids, caps, covers, hinges, latches, seals. '
        'chambers, compartments, containers, reservoirs, tanks, trays, drawers. '
        'blades, cutting edges, graters, slicers, crushers. '
        'handles, grips, straps, hooks, mounts, stands. '
        'labels, text, branding, logos, markings, decals (besides what reference shows). '
        'packaging, boxes, wrappers, bags. '
        'accessories: remotes, chargers, adapters, batteries, tools, replacement parts. '
        'lights, LEDs, screens, displays, indicators. '
        'liquids, powders, food items, ingredients, chemicals. '
    )

    if not defense:
        return base

    # Product-specific phantom parts
    phantom = defense.get('phantom_parts')
    if phantom:
        parts_list = ', '.join(str(p) for p in phantom) if isinstance(phantom, list) else str(phantom)
        base += f' SPECIFICALLY FORBIDDEN for this product: {parts_list}. '

    # Shape preservation
    shape = defense.get('shape_preservation')
    if shape:
        base += f' SHAPE LOCK: {shape}. '

    # Material/texture
    mat = defense.get('material_texture_lock')
    if mat:
        base += f' MATERIAL LOCK: {mat}. '

    # Action bounds
    bounds = defense.get('action_bounds')
    if bounds:
        base += f' ACTION BOUNDS: {bounds}. '

    # Context contamination
    context = defense.get('context_contamination')
    if context:
        base += f' CONTEXT WARNING: {context}. '

    # Scale anchor
    scale = defense.get('scale_anchor')
    if scale:
        base += f' SCALE ANCHOR: {scale}. '

    # Also inject misuse_risks
    misuse = brief.get('misuse_risks_to_avoid')
    if misuse and isinstance(misuse, list):
        risks = '; '.join(str(r) for r in misuse[:5])
        base += f' MISUSE PREVENTION: {risks}. '

    return base

def product_fidelity_block(product_name: str, product_brief: dict[str, Any] | None = None) -> str:
    defense_block = build_hallucination_defense_block(product_brief)
    state_block = state_change_prompt_block(product_brief)
    return (
        f"CANONICAL PRODUCT: {product_name}. Use the provided product reference image as the source of truth. "
        "Preserve exact product shape, proportions, color, material, texture, visible mechanisms, logo/text, packaging, and distinctive silhouette. "
        "Do not redesign, recolor, simplify, distort, or replace the product. "
        "Do not add any feature that is not visible in the reference image: no new lid, cap, hinge, latch, transparent chamber, water tank, handle, button, blade, motor, brand text, embossed text, container body, or storage compartment unless that exact feature already exists in the reference. "
        f"\n{defense_block}{state_block}"
    )


def state_change_prompt_block(product_brief: dict[str, Any] | None = None) -> str:
    brief = product_brief or {}
    contract = brief.get("state_change_contract")
    if not isinstance(contract, dict) or contract.get("required") is not True:
        return ""
    feasibility = brief.get("video_feasibility_plan") if isinstance(brief.get("video_feasibility_plan"), dict) else {}
    states = [
        {"state_id": item.get("state_id"), "visible_configuration": item.get("visible_configuration")}
        for item in contract.get("states", [])[:4] if isinstance(item, dict)
    ]
    transitions = []
    for item in contract.get("transitions", [])[:3]:
        if not isinstance(item, dict):
            continue
        transitions.append({key: item.get(key) for key in (
            "transition_id", "from_state", "to_state", "evidence_level", "render_policy",
            "actor_action", "contact_points", "moving_parts", "fixed_parts", "completion_cue",
            "forbidden_intermediates",
        ) if item.get(key)})
    if feasibility.get("protect_product_configuration") is True:
        transition_rule = (
            ". This generated asset uses only one verified ready-to-use endpoint. Keep the same topology, connections and part inventory throughout. "
            "Do not show both endpoint configurations in one generated clip and do not generate, morph, interpolate or hard-cut the transition. "
            "Any endpoint-to-endpoint hard cut belongs in external editing between separately generated assets or real source footage."
        )
    else:
        transition_rule = (
            ". A state_pair_only transition is never shown as continuous motion. If its policy is hard_cut_only, "
            "hold the first evidenced endpoint, make a clean hard cut, then show the second evidenced endpoint in "
            "matching framing. Never morph, interpolate, multiply, detach, cross, bend, fan, teleport or invent hidden mechanics between states."
        )
    return (
        "\nSTATE-CHANGE CONTRACT: Preserve this exact part inventory across every state: "
        + json.dumps(contract.get("part_invariants", []), ensure_ascii=False)
        + ". Endpoint states: " + json.dumps(states, ensure_ascii=False)
        + ". Transitions: " + json.dumps(transitions, ensure_ascii=False)
        + transition_rule
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


def build_benefit_ladder(
    variant: dict[str, Any],
    manifest: dict[str, Any],
    feature_summary: str,
    product_brief: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Create the commercial spine every prompt must follow.

    The model is still responsible for creative writing. This helper makes the
    generation schema explicit and prevents later normalization from falling
    back to hardware-only scripts like "snap the buckle" or "soft fabric".
    """
    brief = product_brief or {}
    core_claim = _plain_brief_list(
        variant.get("core_selling_claim")
        or variant.get("commercial_promise")
        or variant.get("primary_function_focus")
        or variant.get("selling_angle")
        or brief.get("confirmed_selling_points")
        or manifest.get("selling_points")
        or manifest.get("product_name"),
        2,
    )
    buyer_problem = _plain_brief_list(
        variant.get("buyer_problem")
        or variant.get("hook")
        or variant.get("buyer_desire")
        or variant.get("pain_point")
        or variant.get("selling_angle"),
        1,
    )
    product_intervention = _plain_brief_list(
        variant.get("product_intervention")
        or variant.get("usage_logic")
        or brief.get("confirmed_use_cases")
        or brief.get("step_by_step_usage"),
        2,
    )
    buyer_result = _plain_brief_list(
        variant.get("buyer_result")
        or variant.get("buyer_effect")
        or variant.get("proof_moment")
        or variant.get("selling_angle")
        or brief.get("proof_moments"),
        2,
    )
    proof = _plain_brief_list(
        variant.get("proof_moment") or brief.get("proof_moments"),
        1,
    )
    if not core_claim:
        core_claim = feature_summary[:220] or "the main confirmed buyer benefit"
    if not buyer_problem:
        buyer_problem = f"the shopper needs {core_claim}"
    if not product_intervention:
        product_intervention = feature_summary[:220] or "show the confirmed product use correctly"
    if not buyer_result:
        buyer_result = f"the shopper sees the promised result: {core_claim}"
    return {
        "core_selling_claim": core_claim[:260],
        "buyer_problem": buyer_problem[:220],
        "product_intervention": product_intervention[:260],
        "buyer_result": buyer_result[:260],
        "proof_moment": proof[:260],
    }


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
        brief.get("confirmed_selling_points"),
        manifest.get("selling_points"),
        brief.get("confirmed_use_cases"),
        brief.get("step_by_step_usage"),
        brief.get("function_research"),
        manifest.get("functional_understanding"),
        manifest.get("usage_signals"),
        manifest.get("description"),
    ]
    parts: list[str] = []
    for candidate in candidates:
        text = _plain_brief_list(candidate, 6)
        if text and text not in parts:
            parts.append(text)
    return "; ".join(parts)[:1200] or "demonstrate the confirmed product function with a clear hands-on proof moment"


def commercial_promise_summary(manifest: dict[str, Any], product_brief: dict[str, Any] | None = None) -> str:
    brief = product_brief or {}
    candidates = [
        manifest.get("source_url"),
        manifest.get("product_name"),
        brief.get("product_name"),
        brief.get("confirmed_selling_points"),
        manifest.get("selling_points"),
        manifest.get("description"),
    ]
    parts: list[str] = []
    for candidate in candidates:
        text = _plain_brief_list(candidate, 8)
        if text and text not in parts:
            parts.append(text)
    return "; ".join(parts)[:1600] or "infer the main buyer promise from the product page and brief"


def buyer_effect_summary(variant: dict[str, Any], product_brief: dict[str, Any] | None = None) -> str:
    """Summarize the buyer-visible result the ad should dramatize.

    This intentionally gives the video model a positive commercial north star
    before constraints, so clips do not collapse into neutral feature demos.
    """
    brief = product_brief or {}
    candidates = [
        variant.get("selling_angle"),
        variant.get("hook"),
        variant.get("proof_moment"),
        variant.get("usage_logic"),
        brief.get("confirmed_selling_points"),
        brief.get("recommended_ugc_scenes"),
        brief.get("proof_moments"),
    ]
    parts: list[str] = []
    for candidate in candidates:
        text = _plain_brief_list(candidate, 3)
        if text and text not in parts:
            parts.append(text)
    return "; ".join(parts)[:700] or "show the product creating a clear practical improvement for the buyer"


def build_function_intro_prompt(product_name: str, feature_summary: str, hook: str = "") -> str:
    return (
        "Write concise English ecommerce creator voiceover around the main buyer benefit and the visible result after using the product, not just how to operate it. "
        "Use a young creator / ecommerce host tone with a clear problem-before, product-intervention, benefit-after arc. "
        f"Product: {product_name}. Hook angle: {hook}. Confirmed functions/use only: {feature_summary}. "
        "Output should be 1-2 punchy spoken sentences, 18-32 words total, with no unsupported claims, no fake specs, and no brand names unless visible in source materials."
    )


def build_voiceover_script_10s(product_name: str, feature_summary: str, hook: str = "") -> list[dict[str, str]]:
    return normalize_voiceover_script_10s(
        [
            hook or "This is the small fix that changes the whole routine.",
            f"Use it once, and the benefit is obvious: {feature_summary[:90]}",
            "The result is easier, calmer, and more useful.",
        ],
        hook=hook or "Tiny upgrade, but it makes the setup feel instantly easier.",
        fallback=f"Watch the real function: {feature_summary[:120]}",
    )


def build_on_screen_callouts(feature_summary: str) -> list[str]:
    words = [part.strip(" .") for part in re_split_features(feature_summary) if part.strip(" .")]
    callouts = words[:3] if words else ["Function demo", "Proof moment", "Product close-up"]
    return [callout[:34] for callout in callouts]


def normalize_on_screen_callouts(raw_callouts: Any, feature_summary: str) -> list[str]:
    if isinstance(raw_callouts, list):
        candidates = [str(item).strip() for item in raw_callouts]
    elif isinstance(raw_callouts, str) and raw_callouts.strip():
        candidates = [part.strip() for part in re_split_features(raw_callouts)]
    else:
        candidates = build_on_screen_callouts(feature_summary)
    banned = (
        "instagram",
        "ins",
        "tiktok",
        "logo",
        "subtitle",
        "caption",
        "watermark",
        "@",
        "app",
        "camera",
        "like",
        "follow",
        "share",
        "story",
        "reel",
    )
    clean: list[str] = []
    for candidate in candidates:
        label = re.sub(r"\s+", " ", candidate).strip(" .,-")
        label = re.sub(r"[^\x00-\x7F]+", "", label)
        label = re.sub(r"[^A-Za-z0-9 %&+/-]", "", label)
        words = label.split()
        if len(words) > 3:
            label = " ".join(words[:3])
        if not label:
            continue
        lowered = label.lower()
        if any(marker in lowered for marker in banned):
            continue
        if label not in clean:
            clean.append(label[:18].strip())
        if len(clean) >= 3:
            break
    return clean or ["Quick demo", "Easy control", "Daily wear"]


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
        product_fidelity_block(product_name, product_brief)
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


def usage_demo_video_prompt(
    variant: dict[str, Any],
    product_brief: dict[str, Any] | None = None,
    voice_locale: str | None = None,
) -> str:
    brief = product_brief or {}
    # The spoken voice used to be hard-coded to a "young American female" with an
    # "18 to 22 English words" budget, and because this text already contains
    # "Native audio" the adapter skipped its own locale-aware block and shipped
    # that English voice for every market. It is now derived from the locale.
    resolved_locale = normalize_locale(voice_locale) or normalize_locale(variant.get("voice_locale"))
    if not resolved_locale:
        raise VoiceLocaleError(
            "usage_demo_video_prompt needs a resolved voice locale; refusing to hard-code an English voice."
        )
    voice_line = voice_description(resolved_locale)
    spoken_language = language_name(resolved_locale)
    if script_of(resolved_locale) == "latin":
        length_rule = (
            f"The spoken script must finish naturally within 10 seconds at normal creator pace, "
            f"ideally {VOICEOVER_TARGET_WORDS[0]} to {VOICEOVER_TARGET_WORDS[1]} words total and never more than "
            f"{VOICEOVER_HARD_MAX_WORDS} words."
        )
    else:
        length_rule = (
            f"The spoken script must finish naturally within 10 seconds at normal creator pace, "
            f"roughly {max_voiceover_chars(resolved_locale)} characters of {spoken_language} in total."
        )
    feasibility = brief.get("video_feasibility_plan") if isinstance(brief.get("video_feasibility_plan"), dict) else {}
    protect_configuration = feasibility.get("protect_product_configuration") is True
    buyer_effect = buyer_effect_summary(variant, brief)
    benefit_ladder = variant.get("benefit_ladder") if isinstance(variant.get("benefit_ladder"), dict) else {}
    core_selling_claim = _plain_brief_list(
        variant.get("core_selling_claim") or benefit_ladder.get("core_selling_claim") or variant.get("selling_angle"),
        1,
    )
    buyer_problem = _plain_brief_list(
        variant.get("buyer_problem") or benefit_ladder.get("buyer_problem") or variant.get("hook"),
        1,
    )
    product_intervention = _plain_brief_list(
        variant.get("product_intervention") or benefit_ladder.get("product_intervention") or variant.get("usage_logic"),
        1,
    )
    buyer_result = _plain_brief_list(
        variant.get("buyer_result") or benefit_ladder.get("buyer_result") or variant.get("buyer_effect") or buyer_effect,
        1,
    )
    usage_context = _plain_brief_list(
        variant.get("usage_logic") or brief.get("step_by_step_usage") or brief.get("confirmed_or_inferred_use_steps"),
        3,
    )
    proof_moment = _plain_brief_list(variant.get("proof_moment") or brief.get("proof_moments"), 2)
    scene_context = _plain_brief_list(variant.get("shot_plan") or brief.get("recommended_ugc_scenes"), 2)
    scene_imagination = build_scene_imagination(variant, brief)
    reference_scope = variant.get("reference_scope") or reference_scope_note(variant.get("selected_reference_images"))
    if not usage_context:
        usage_context = "perform one simple supported use action shown or described in the product materials"
    if not proof_moment:
        proof_moment = "end with the product clearly visible beside the practical result"
    if not scene_context:
        scene_context = "a realistic home setting where this product would naturally be used"
    storyboard = format_storyboard_for_prompt(variant)
    raw_voiceover = variant.get("voiceover_script_10s") or variant.get("voiceover_script_8s") or []
    normalized_voiceover = normalize_voiceover_script_10s(
        raw_voiceover,
        hook=str(variant.get("hook") or ""),
        fallback=str(variant.get("dialogue_script") or variant.get("title") or ""),
        locale=resolved_locale,
    )
    voiceover_text = compact_voiceover_text(normalized_voiceover)
    timed_voiceover = " ".join(f"[{item['time']}] {item['line']}" for item in normalized_voiceover if item.get("line"))
    audio_block = (
        f"Native audio: include a clear {voice_line} lifestyle-commerce creator voiceover, bright, stylish, warm, emotionally engaged, and not robotic or corporate. "
        f"Commercial spine for the spoken copy: buyer problem/desire = {buyer_problem}; product intervention = {product_intervention}; buyer result = {buyer_result}. "
        "The spoken copy must sell this spine with a natural creator cadence; do not spend the line only naming parts, materials, or generic setup steps. "
        f"{length_rule} "
        f"{language_clause(resolved_locale)} The spoken copy must be written in {spoken_language}; do not speak or transliterate English. "
        f"Speak these exact timed lines in order: {timed_voiceover}. "
        f"Combined exact script: \"{voiceover_text[:220]}\" "
        "Do not add intro words, filler, repeated lines, extra CTA, or any unscripted speech. Keep the voiceover synchronized to the benefit/result arc. Add low-volume modern lifestyle background music plus subtle real product handling sounds; no singing."
        if voiceover_text
        else "Native audio: include subtle real product handling sounds only, no music."
    )
    callouts = normalize_on_screen_callouts(variant.get("on_screen_callouts"), _plain_brief_list(variant.get("selling_angle") or usage_context, 3))
    overlay_block = (
        f"Allow only {min(len(callouts), 2)} stylish short-form creator typography feature-tag overlays: {', '.join(repr(item) for item in callouts[:2])}. "
        "Render them as stylish short-form creator typography: bold rounded pill-shaped labels, warm vibrant accent tints, compact pop-up badges, modern fashion-tag feel without any platform icon or app UI. Keep them brief and not synchronized line-by-line with the spoken voiceover; if the model cannot render clean stylish feature-tag text, skip overlay entirely rather than rendering ugly or garbled words. "
        "Never render full-sentence captions, subtitles, transcripts, lower thirds, karaoke text, social media icons, platform icons/logos, camera icons, reaction icons, app UI, watermarks, or emoji text. "
        if callouts
        else ""
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
                "video_prompt",
            )
        )
    )
    if protect_configuration:
        action_arc = (
            "Show the need, then use the product already in its verified ready-to-use state, then show the benefit. "
            "The product topology, connections, part count and geometry must remain unchanged for the full generated clip. "
            "Do not generate setup, installation, assembly, insertion, reversal, folding or an interpolated transition."
        )
    else:
        action_arc = (
            "Use a clear problem-before, product-intervention, benefit-after arc: show the need or frustration, "
            "show one supported product action, then show the improved outcome, calmer routine, saved effort, comfort, confidence, or other confirmed benefit."
        )
    feasibility_block = (
        f"LOW-RISK GENERATION ROUTE: target model = {feasibility.get('target_model', 'model-agnostic')}; "
        f"risk = {feasibility.get('risk_level', 'unknown')} ({feasibility.get('risk_score', 0)}); "
        f"direction = {variant.get('safe_demo_direction') or feasibility.get('selected_direction', {})}; "
        f"allowed motion = {feasibility.get('allowed_motion', 'one simple supported interaction')}; "
        f"editing strategy = {variant.get('editing_strategy') or feasibility.get('editing_strategy', '')}; "
        f"forbidden generation = {variant.get('unsafe_actions_omitted') or feasibility.get('forbidden_generation', [])}. "
    )
    return (
        f"Create a 10-second {variant.get('target_frame_aspect_ratio') or '9:16'} stylish creator-ad product-use clip in Omni Flash omni-reference mode. "
        "Use the chronological storyboard as the action/scene guide, the identity grid as the product truth, and an optional QC-passed operation grid only when the product needs supported state-change guidance. These are all-purpose references, not timeline endpoints. "
        "Commercial north star: every visual beat and the voiceover must sell the buyer-visible result, not merely list product parts. "
        f"Core buyer reason to buy: {core_selling_claim}. "
        f"Benefit ladder: problem/desire = {buyer_problem}; product action = {product_intervention}; result/proof = {buyer_result}. "
        f"Buyer-visible effect to dramatize: {buyer_effect}. "
        f"{feasibility_block}{action_arc} "
        f"Follow this exact 0-10s storyboard with visual beat, spoken line, and sparse feature overlay for each beat: {storyboard} "
        f"Supported product action: {usage_context}. "
        f"Scene context: {scene_context}. "
        f"Scene imagination: {scene_imagination}. "
        f"Reference scope: {reference_scope} "
        "Keep the same visible product identity throughout: silhouette, proportions, color, texture, and distinctive details must stay consistent while it moves. "
        "Avoid unsupported claims, magic effects, sudden scene changes, product morphing, or new product mechanisms. "
        f"Proof/result moment: {proof_moment}. Make this proof moment feel like the satisfying payoff of the buyer-visible effect. "
        f"{phone_geometry} "
        f"{overlay_block}"
        f"{audio_block} "
        "Natural handheld phone camera, close practical use framing, premium lifestyle lighting, quick but readable creator-ad pacing. "
        "No subtitles, no sentence captions, no lower-third transcript, no karaoke-style text, no emoji text, no social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, and no watermarks. The only allowed readable text is the explicitly allowed tiny feature-tag overlay words."
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
    voice_locale: str | None = None,
    market: str = "",
) -> dict[str, Any]:
    commercial_promise = commercial_promise_summary(manifest, product_brief)
    creative_matrix = creative_matrix_plan(count, existing_history)
    resolved_locale = normalize_locale(voice_locale)
    if not resolved_locale:
        raise VoiceLocaleError(
            "generate_with_model needs a resolved voice locale; refusing to let the model assume an English market."
        )
    spoken_language = language_name(resolved_locale)
    if script_of(resolved_locale) == "latin":
        voiceover_budget = (
            f"{VOICEOVER_TARGET_WORDS[0]}-{VOICEOVER_TARGET_WORDS[1]} words, hard maximum {VOICEOVER_HARD_MAX_WORDS}"
        )
    else:
        voiceover_budget = (
            f"about {max_voiceover_chars(resolved_locale)} characters of {spoken_language} in total"
        )
    market_block = f"""
TARGET MARKET AND SPOKEN LANGUAGE (hard requirement):
- Market: {market or resolved_locale}
- Locale: {resolved_locale}
- Spoken language: {spoken_language}
- Voice: {voice_description(resolved_locale)}

Every spoken line you write must be natural, native {spoken_language} intended for this market. Write `dialogue_script`,
`voiceover_script_10s` and the spoken parts of `storyboard_10s` in {spoken_language}. {language_clause(resolved_locale)}
Total spoken length: {voiceover_budget}, and it must finish naturally inside 10 seconds. Do not write English copy and do
not leave an English placeholder. Keep scenes, props, creator persona and gestures culturally natural for {market or resolved_locale}.
Each complete line must be a full sentence that ends with terminal punctuation; never return a fragment.
"""
    prompt = f"""
Create {count} distinct UGC prompt variants for short-form ecommerce product ads.

{market_block}

HIGH-PRIORITY COMMERCIAL PROMISE SIGNALS:
{commercial_promise}

Use these signals to decide the lead selling idea before reading mechanical details. If a page title or URL sells a high-level benefit but source images cannot visually prove the literal claim, translate it into a safe buyer-perceived routine, concern, or after-state. Do not delete that commercial promise and retreat into minor hardware/material details.

CREATIVE MATRIX CONTRACT:
{json.dumps(creative_matrix, ensure_ascii=False, indent=2)}

The commercial promise should stay consistent across the batch, but the creative execution must not collapse into the same formula. Assign one matrix slot to each variant in order. The variants must materially differ by hook archetype, buyer context, creator persona, scene type, story shape, proof style, camera idea, and pace. Do not write ten versions of “problem -> pick up product -> use product -> happy result” with only minor wording changes. Keep the same core selling claim, but make each video feel like a different ad concept.

Product manifest:
{json.dumps(manifest, ensure_ascii=False)[:8000]}

Image analysis:
{json.dumps(image_analysis, ensure_ascii=False)[:12000]}

Product usage cognition brief:
{json.dumps(product_brief, ensure_ascii=False)[:12000]}

VIDEO GENERATION FEASIBILITY ROUTE:
{json.dumps(product_brief.get("video_feasibility_plan", {}), ensure_ascii=False, indent=2)}

Preferred local reference images:
{json.dumps(references, ensure_ascii=False)}

Existing historical variants to avoid overlapping with:
{history_summary_for_prompt(existing_history)}

Return JSON with:
- product_name
- variants: array of {count} objects
Each variant must include:
- variant_id
- creative_matrix_slot: copy the assigned slot from the CREATIVE MATRIX CONTRACT and adapt it only if the product cannot support one detail
- title
- core_selling_claim: the single highest-priority buyer reason to care, chosen from product title/page selling points/confirmed selling points before scene writing
- buyer_problem: the shopper or creator pain/desire that makes the product feel worth buying
- product_intervention: the one supported product action that answers that buyer problem
- buyer_result: the visible or spoken after-state that makes the promise believable
- benefit_ladder: object with core_selling_claim, buyer_problem, product_intervention, buyer_result, and proof_moment; this is the creative spine and must be written before hook/voiceover/storyboard
- primary_function_focus: the single confirmed selling point or product function this variant owns; allocate this before writing scenes so the batch does not collapse into one repeated function
- buyer_effect: the concrete buyer-visible outcome after using the product, such as calmer pet, cleaner sink, faster prep, less clutter, easier setup, cooler air, more comfortable sleep, or safer grooming; this must drive both visuals and voiceover
- creator_persona
- hook
- dialogue_script with natural spoken lines
- function_intro_prompt: a separate prompt for generating concise spoken function explanation
- voiceover_script_10s: timed 0-3s, 3-7s, 7-10s spoken script lines that sell the main buyer problem/desire, show the product intervention, and land the buyer-visible result
- on_screen_callouts: 1-3 short ecommerce feature overlay labels rendered as stylish short-form creator typography (bold pill badges, warm vibrant tints, compact pop-up labels); 1-3 plain-English words only, max 18 characters, no emoji; never subtitles, sentence captions, app icons, platform logos, social media icons, camera/reel icons, UI chrome, or watermarks
- function_demo_prompt: editor-facing prompt that explains the function, proof moment, and final benefit
- usage_logic: explain how the product works and why the scene is correct
- proof_moment: the exact visual action that proves the function
- shot_plan: mirror storyboard_10s exactly (same panel count, times and visual descriptions), never an independent sequence
- target_frame_aspect_ratio: requested video frame ratio, default 9:16; this is NOT the board canvas ratio
- storyboard_10s: exactly 6 panels by default; use exactly 9 when dense action/proof needs extra continuity. Never truncate a nine-panel sequence. Each panel maps one-to-one to the video visual description, with contiguous time intervals covering 0-10 seconds; each beat must include time, visual (camera position, subject placement, visible action and environment anchors), spoken, and optional sparse overlay rendered as stylish pill-badge / warm-tinted pop-up typography; overlay must be short feature tags only, not subtitles; the storyboard is rendered into one chronological reference sheet
- selected_reference_images using local paths from the preferred list
- reference_scope: explain which visual details from source images lock product identity, and explicitly state that source-photo background/props/composition are not mandatory unless functionally necessary
- selling_angle: one focused buyer benefit for this variant
- scene_imagination: a realistic lifestyle scene derived from the product function and selling angle, not merely copied from source product photos
- image_prompt in English for GPT-Image-2 image-to-image
- video_prompt in English for the target video model
- negative_prompt
- generation_risk: the router-provided level, score and hazards; do not lower it
- safe_demo_direction: the router-selected commercially useful low-risk direction
- editing_strategy: how any omitted setup/state change is conveyed outside the generated clip
- unsafe_actions_omitted: fragile physical actions that must not be generated

Critical:
1. Start from the HIGH-PRIORITY COMMERCIAL PROMISE SIGNALS, product_brief.confirmed_selling_points, manifest.selling_points, URL/product-title language, and the product title to identify the buyer's main reason to care. Write the benefit_ladder first. Then use product_brief.step_by_step_usage / confirmed_use_cases only to keep the demo mechanically correct.
2. Do not invent unsupported functions, but do not bury the commercial promise. If a claim is hard to prove visually, translate it into a safe buyer-perceived result/routine instead of deleting it.
3. Every variant must pass this commercial test: could a shopper understand the product's benefit with the sound on and again with the sound off? If not, rewrite the storyboard before returning JSON.
4. Every image_prompt and video_prompt must contain a product-fidelity block requiring exact preservation of the original product appearance.
5. The selected reference image must be the best true full-product reference: full silhouette, correct SKU/style, real proportions, visible key functional zones. Do not select alternate SKU images, accessory-only images, packaging-only images, loose parts, isolated cables, or detail images as canonical.
6. Put concise native-audio voiceover lines into video_prompt, and ensure the full spoken copy can naturally finish inside 10 seconds at normal creator pace: target 18-22 English words, hard max 25 words, no unfinished trailing phrase.
7. Voiceover must be benefit-led and sales-forward: in 18-22 words, it should make the product feel worth buying by naming the buyer problem/desire, the product's role, and the final result. Avoid scripts that only say "snap it", "soft fabric", "white buckle", "easy setup", "here is how it works", or other part/setup descriptions unless those words are tied to the main buyer outcome.
8. Keep every shot_plan, voiceover_script_10s, image-to-video prompt, and action arc designed for exactly 10 seconds. Do not write 8s, 9s, 12s, or 15s plans.
9. Allow only 1-2 tiny sparse overlay labels from on_screen_callouts as feature tags, e.g. "100 speeds" or "Tilt airflow"; render them as stylish short-form creator typography (bold rounded pill badges, warm vibrant accent tints, compact pop-up labels), plain-English only, no emoji. If clean stylish text is uncertain, skip overlay rather than render ugly/garbled words. Do not ask for subtitles, transcript captions, lower-thirds, karaoke text, social media icons, platform logos, camera/reel icons, app UI, or watermarks. Never use positive platform-branded style phrases; say stylish short-form creator-ad energy instead.
10. Build the video from one chronological storyboard reference sheet: video_prompt must include every beat's time, visual content, spoken line, and optional sparse feature overlay. The sheet, identity grid and optional operation grid are all-purpose omni-reference inputs; do not describe them as timeline endpoints. Overlay must not repeat the spoken line as subtitles.
11. Product reference images lock the product itself, not the entire source photo. Preserve product identity and usage mechanics, but freely imagine realistic buyer scenes, backgrounds, camera angles, and contextual props that clarify the benefit.
12. Each variant should focus on one small selling point or function. Vary buyer problem, scene, action, proof/result moment, and emotional payoff across the batch; do not produce ten versions of the same tabletop placement.
12b. If the core selling claim is the same for every variant, the story must vary even more aggressively: use different hook archetypes, different people or social contexts, different before-state problems, different scene geometry, different proof/payoff visuals, different camera grammar, and different pacing. The product can solve the same buyer desire, but the ads must not look like clones.
13. The storyboard panels must form one meaningful 10-second action arc while preserving the same exact product, person, room, wardrobe, lighting and supported usage logic across the sheet.
14. Read the historical variants listed above as actual prior creative work for this product. Do not paraphrase them. Avoid reusing the same scene setup, same use action, same proof moment, same buyer context, or same selling angle unless you materially transform at least 3 of those dimensions.
15. When function overlap is unavoidable, deliberately choose a different buyer problem, a different visible result, a different camera idea, and a different proof framing instead of repeating the same demo in new words.
15b. Use the CREATIVE MATRIX CONTRACT as the diversity source of truth. A variant fails if its creative_matrix_slot is not reflected in its hook, shot_plan, storyboard_10s, and video_prompt.
16. Before writing the variants, allocate one primary_function_focus per variant from the high-priority commercial promise, confirmed_selling_points, manifest selling_points, confirmed_use_cases, step_by_step_usage, and proof_moments. Do not let minor hardware details or materials become the lead selling angle when the product title/page/URL clearly sells a higher-level benefit. Hardware details such as buckle, slider, material, color, pattern, button, cable, LED, or case should support the main promise rather than replace it. For multifunction wearables such as smart rings, do not default every variant to photo-taking/remote shutter; split confirmed functions across health/app checks, charging, status display, touch control, activity tracking, waterproof daily wear, or fit/detail as supported by the brief.
17. If a phone appears, make its orientation physically possible. For selfie/timer/remote-shutter demos, the phone screen faces the creator and the lens points toward the creator; the viewer sees phone back/side, mirror, or over-shoulder composition. For app-screen proof, use over-shoulder/tabletop/second-device geometry. For wireless charging, the phone lies flat screen-up on the charger unless the real product is a stand.
18. Follow VIDEO GENERATION FEASIBILITY ROUTE before choosing the storyboard action. Use its lowest-risk useful direction and motion budget. Model capability claims never override product evidence or topology risk.
19. If protect_product_configuration is true, every generated frame must keep one verified ready-state topology, connection graph and part inventory. Do not depict continuous installation, assembly, insertion, reversal, folding or other configuration changes. Show the buyer result, detail proof and creator reaction instead.
20. A clean editor hard cut is an editing instruction, not a generated transition. If setup must be communicated, use separately generated endpoint assets or real source footage; never give the video model conflicting product configurations and ask it to interpolate between them.
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
    from v2_contract import active, guidance, load_usage
    manifest = load_json(product_dir / "product_manifest.json")
    image_analysis = load_json(product_dir / "image_analysis.json", {"images": []})
    product_brief = load_json(product_dir / "product_brief.json", {})
    if not manifest:
        print(f"[skip] missing manifest: {product_dir}")
        return
    assert_clean_generation_inputs(product_dir, image_analysis, product_brief)
    if active(product_dir):
        product_brief = {**product_brief, "v2_reference_contract": guidance(product_dir),
                         "v2_action_ledger": load_usage(product_dir)["actions"]}
    routing_brief = {
        **product_brief,
        "product_name": manifest.get("product_name") or product_brief.get("product_name"),
        "manifest_selling_points": manifest.get("selling_points") or [],
    }
    feasibility_plan = build_video_feasibility_plan(routing_brief, args.target_video_model)
    print("\n".join(format_feasibility_notice(product_dir.name, feasibility_plan)), flush=True)
    product_brief = {**product_brief, "video_feasibility_plan": feasibility_plan}
    references = best_reference_images(image_analysis, product_brief, limit=4)
    canonical_prompt_path = product_dir / "ugc_prompts.json"
    history_glob = "ugc_prompts.json" if args.output_file == "ugc_prompts.json" and canonical_prompt_path.exists() else args.history_glob
    existing_history, history_files = collect_existing_variant_history(product_dir, history_glob) if not args.ignore_history else ([], [])
    print(f"[prompts] {product_dir.name} refs={references} history={len(existing_history)}")
    # Resolve the market/locale once for the whole batch and persist it, so the
    # video adapter, the montage step and any later reroll all inherit the same
    # spoken language instead of defaulting to English.
    existing_canonical = load_json(canonical_prompt_path, {}) if canonical_prompt_path.exists() else {}
    try:
        voice_resolution = resolve_voice_locale(
            prompts=existing_canonical if isinstance(existing_canonical, dict) else {},
            brief=product_brief,
            manifest=manifest,
            explicit=getattr(args, "voice_locale", "") or getattr(args, "market", ""),
            product_dir=product_dir,
        )
    except VoiceLocaleError as error:
        raise RuntimeError(f"{product_dir.name}: {error}") from error
    print(
        f"[market] {product_dir.name} locale={voice_resolution.locale} "
        f"market={voice_resolution.market or voice_resolution.locale} source={voice_resolution.source}",
        flush=True,
    )
    creative_matrix = creative_matrix_plan(args.count, existing_history)
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
        voice_locale=voice_resolution.locale,
        market=voice_resolution.market,
    )
    output = normalize_variants(
        output, manifest, references, args.count, product_brief, creative_matrix,
        voice_locale=voice_resolution.locale,
        market=voice_resolution.market,
    )
    output["selected_reference_images"] = references
    output["voice_locale"] = voice_resolution.locale
    output["market"] = voice_resolution.market or voice_resolution.locale
    output["voice_locale_source"] = voice_resolution.source
    output["target_video_model"] = feasibility_plan["target_model"]
    output["video_feasibility_plan"] = feasibility_plan
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
        "creative_matrix_enforced": True,
        "core_selling_claim_should_remain_consistent": True,
        "required_difference_dimensions": [
            "hook_archetype",
            "buyer_context",
            "creator_persona",
            "scene_type",
            "story_shape",
            "proof_style",
            "camera_idea",
            "pace",
            "scene",
            "action",
            "proof_moment",
        ],
        "creative_matrix": creative_matrix,
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
    parser.add_argument("--model", default=os.getenv("PRODUCT_UGC_PROMPT_MODEL", "gpt-5.2"))
    parser.add_argument(
        "--target-video-model",
        default=os.getenv("PRODUCT_UGC_VIDEO_MODEL", "omni-flash"),
        choices=["omni-flash", "omni_flash-10s"],
        help="Omni Flash model used for risk routing. Video submission always uses omni-reference.",
    )
    parser.add_argument("--base-url", default="https://api.laozhang.ai/v1")
    parser.add_argument(
        "--market",
        default="",
        help="Target market for the spoken language and local creative framing, e.g. Japan or JP. Resolved from the product brief when omitted.",
    )
    parser.add_argument(
        "--voice-locale",
        default=os.getenv("PRODUCT_UGC_VOICE_LOCALE", ""),
        help="Explicit spoken locale, e.g. ja-JP. Overrides the declared market; it is never silently defaulted to English.",
    )
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--products", default="", help="Comma-separated product selectors, e.g. 01 or 01-flower")
    args = parser.parse_args()
    api_key = require_api_key_for_base_url(args.base_url)
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        process_product(product_dir, api_key, args)


if __name__ == "__main__":
    main()

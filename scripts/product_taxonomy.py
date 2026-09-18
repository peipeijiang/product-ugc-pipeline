#!/usr/bin/env python3
"""Factorized product taxonomy for UGC production, independent of store taxonomy."""
from __future__ import annotations

from typing import Any


CATALOG_VERTICALS = (
    "apparel-accessories", "arts-entertainment", "animals-pet-supplies", "baby-toddler",
    "business-industrial", "cameras-optics", "electronics", "food-beverages-tobacco",
    "furniture", "hardware", "health-beauty", "home-garden", "luggage-bags", "media",
    "office-supplies", "sporting-goods", "toys-games", "vehicles-parts", "other-physical-product",
)

# These are production families: products share reference-sheet and QC needs.
# They are intentionally broader than individual merchant/catalog categories.
PRODUCTION_FAMILIES: dict[str, dict[str, Any]] = {
    "apparel": {"layout": "2 rows x 2 columns", "size": "1024x1024", "panels": ["front silhouette", "supported angle", "fabric and seams", "verified worn fit"]},
    "jewelry": {"layout": "1 row x 3 columns", "size": "1536x1024", "panels": ["front placement and scale", "45 degree contact and drape", "material and closure detail"]},
    "electronics": {"layout": "3 rows x 2 columns", "size": "1024x1536", "panels": ["front silhouette", "45 degree thickness", "supported side and ports", "supported top and controls", "verified use and contact", "verified relative scale"]},
    "home-tools": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["full silhouette", "supported side", "grip and functional part", "verified use and contact", "verified relative scale"]},
    "pet-tools": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["full silhouette", "supported side", "functional contact area", "verified pet interaction", "verified pet size relation"]},
    "furniture": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["full silhouette", "supported side and load path", "joint or structural detail", "verified use and contact", "verified relative scale"]},
    "bags-containers": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["closed full silhouette", "open interior and capacity", "closure handle or seam detail", "verified carry or storage use", "verified relative scale"]},
    "beauty-care": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["complete package and applicator", "supported side and closure", "dispenser or product texture detail", "verified application contact", "hand-relative scale"]},
    "food-beverage": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["complete package silhouette", "source-backed product form", "opening pouring or serving interface", "verified serving use", "portion and package scale"]},
    "toys-hobbies": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["complete set and inventory", "supported alternate angle", "joint control or play detail", "verified play or making use", "user-relative scale"]},
    "home-decor": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["complete silhouette", "supported side or mounting view", "material finish and defining detail", "verified room placement", "furniture-relative scale"]},
    "sports-outdoor": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["complete product silhouette", "support attachment or load path", "functional interface detail", "verified outdoor use", "packed state and human scale"]},
    "baby-care": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["complete silhouette and inventory", "supported side and safety structure", "closure control or contact detail", "verified caregiver use", "age-appropriate relative scale"]},
    "vehicle-hardware": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["complete silhouette and parts", "connector or mounting interface", "material fastener or control detail", "verified installed use", "vehicle or tool-relative scale"]},
    "office-media": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["complete silhouette", "supported side and working surface", "binding control or interface detail", "verified desk or media use", "hand and desk-relative scale"]},
    "general-merchandise": {"layout": "3 panels top, 2 panels bottom", "size": "1024x1024", "panels": ["complete canonical silhouette", "strongest supported alternate view", "source-backed functional interface", "source-backed use or placement", "verified relative scale"]},
}

PHYSICAL_TRAITS = {
    "rigid", "flexible-textile", "soft-body", "articulated", "multi-part", "deformable",
    "inflatable", "suspended-load", "powered", "cabled", "transparent", "reflective",
    "liquid-powder", "adhesive", "sharp", "fragile",
}

INTERACTION_MODES = {
    "wear", "hold-operate", "place-support", "body-support", "pet-contact", "contain-store",
    "open-close", "dispense-pour", "apply", "consume", "connect-power", "mount-install",
    "assemble", "fold-deploy", "inflate-deflate", "suspend-anchor", "roll-slide", "clean-cut", "play",
}

TRAIT_CHECKS = {
    "inflatable": "Lock chambers, seams, valve/pump inventory and evidenced inflated/deflated endpoints; never morph through an unsupported inflation state.",
    "suspended-load": "Show every source-backed anchor and the continuous load path; reject floating, one-ended support or disappearing suspension lines.",
    "articulated": "Preserve joint count, axes, stops and connected parts; unsupported intermediate joint configurations remain forbidden.",
    "multi-part": "Preserve exact visible part inventory and connections; no appearing, disappearing, duplicated or swapped parts.",
    "powered": "Preserve controls, ports and visible powered state; do not invent power features or activation behavior.",
    "cabled": "Preserve cable exit, connector type and complete valid power chain when powered behavior is shown.",
    "flexible-textile": "Preserve weave, seams, edge binding and gravity-driven drape; do not turn fabric into a rigid shell.",
    "transparent": "Preserve real transparency, wall thickness and contained-object visibility without deleting edges or structure.",
    "reflective": "Reflections must follow the scene and must not erase product boundaries, controls or material identity.",
    "liquid-powder": "Preserve container, fill level, viscosity or granularity and gravity; no spontaneous volume or material changes.",
    "sharp": "Keep the working edge geometry and safe evidenced contact; never place the edge through hands, bodies or unsupported materials.",
    "fragile": "Preserve thin parts and supported contact; reject bending, melting, cracking or impossible load unless directly evidenced.",
}

ALIASES = {
    "wearable": "apparel", "accessories": "jewelry", "powered-device": "electronics",
    "handheld-tool": "home-tools", "pet-product": "pet-tools", "human-support": "furniture",
    "container-storage": "bags-containers", "toy-hobby": "toys-hobbies", "outdoor": "sports-outdoor",
    "needs_new_category": "general-merchandise", "unclassified": "general-merchandise",
}


def _strings(value: Any) -> list[str]:
    items = value if isinstance(value, list) else ([value] if value else [])
    return list(dict.fromkeys(str(item).strip() for item in items if str(item).strip()))


def normalize_production_profile(brief: dict[str, Any]) -> dict[str, Any]:
    raw = brief.get("production_classification")
    raw = raw if isinstance(raw, dict) else {}
    missing_profile = not raw
    requested = str(raw.get("visual_family") or brief.get("recommended_v2_category") or "general-merchandise").strip()
    family = ALIASES.get(requested, requested)
    unknown_family = family not in PRODUCTION_FAMILIES
    if unknown_family:
        family = "general-merchandise"
    raw_traits = _strings(raw.get("physical_traits"))
    raw_interactions = _strings(raw.get("interaction_modes"))
    traits = [item for item in raw_traits if item in PHYSICAL_TRAITS]
    interactions = [item for item in raw_interactions if item in INTERACTION_MODES]
    unknown_values = [item for item in raw_traits if item not in PHYSICAL_TRAITS]
    unknown_values += [item for item in raw_interactions if item not in INTERACTION_MODES]
    evidence = _strings(raw.get("classification_evidence"))
    confidence_value = raw.get("confidence") or brief.get("confidence") or "unknown"
    confidence = str(
        confidence_value.get("level") or confidence_value.get("value") or "unknown"
        if isinstance(confidence_value, dict) else confidence_value
    )
    return {
        "visual_family": family,
        "physical_traits": traits,
        "interaction_modes": interactions,
        "classification_evidence": evidence,
        "confidence": confidence,
        "requires_manual_review": (
            missing_profile or bool(raw.get("requires_manual_review")) or unknown_family
            or bool(unknown_values) or not evidence or confidence.lower() in {"unknown", "low"}
        ),
        "unrecognized_values": unknown_values + ([requested] if unknown_family else []),
    }


def normalize_catalog_taxonomy(brief: dict[str, Any]) -> dict[str, Any]:
    raw = brief.get("catalog_taxonomy")
    raw = raw if isinstance(raw, dict) else {}
    vertical = str(raw.get("vertical") or "other-physical-product").strip()
    unknown = vertical not in CATALOG_VERTICALS
    if unknown:
        vertical = "other-physical-product"
    raw_path = raw.get("path")
    path = [item.strip() for item in raw_path.split(">") if item.strip()] if isinstance(raw_path, str) else _strings(raw_path)
    product_type = str(brief.get("product_type") or "physical product").strip()
    return {
        "vertical": vertical,
        "path": path or [vertical, product_type],
        "main_function": str(raw.get("main_function") or "unknown").strip(),
        "requires_manual_review": not raw or unknown or not path,
    }


def production_spec(category: str, traits: list[str] | None = None) -> dict[str, Any]:
    family = ALIASES.get(category, category)
    if family not in PRODUCTION_FAMILIES:
        raise RuntimeError(f"Unknown production family {category}; choose {', '.join(PRODUCTION_FAMILIES)}")
    base = PRODUCTION_FAMILIES[family]
    trait_checks = [TRAIT_CHECKS[item] for item in (traits or []) if item in TRAIT_CHECKS]
    return {
        "category": family,
        "layout": base["layout"],
        "size": base["size"],
        "sheet_count": 1,
        "panels": list(base["panels"]),
        "physical_traits": list(traits or []),
        "trait_checks": trait_checks,
    }


def prompt_contract() -> str:
    return (
        "catalog_taxonomy: object with vertical (one of " + ", ".join(CATALOG_VERTICALS)
        + "), path (specific semantic path from broad to literal product type), and main_function. "
        "production_classification: object with visual_family (one of " + ", ".join(PRODUCTION_FAMILIES)
        + "), physical_traits (zero or more of " + ", ".join(sorted(PHYSICAL_TRAITS))
        + "), interaction_modes (zero or more of " + ", ".join(sorted(INTERACTION_MODES))
        + "), classification_evidence (exact local image paths/page fields), confidence, and requires_manual_review. "
        "Choose visual_family by shared reference-sheet/QC needs, not by the store shelf. Use general-merchandise with requires_manual_review=true when evidence cannot support a more specific production family."
    )

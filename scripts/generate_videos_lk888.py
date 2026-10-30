#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from common import download_binary, load_json, selected_product_dirs, write_json
from creative_risk_router import format_production_notice
from generate_images import parse_variants
from storyboard_contract import VIDEO_SINGLE_CANVAS_RULE, storyboard_video_beats
from voice_locale import (
    VoiceLocaleError,
    creator_market_identity,
    language_clause,
    language_name,
    normalize_creator_persona,
    normalize_locale,
    region_name,
    resolve_voice_locale,
    trim_voiceover,
    validate_spoken_text,
    voice_description,
)

# The desktop environment may inject a stale local SOCKS proxy.  LK888 and
# public reference hosts must be reached directly for production submissions.
for _proxy_key in list(os.environ):
    if "proxy" in _proxy_key.lower():
        os.environ.pop(_proxy_key, None)


BASE_URL = "https://api.lk888.ai"
CONTINUE_STATES = {"pending", "running", "queued", "processing", "submitted"}
SUCCESS_STATES = {"success", "completed", "succeeded"}
FAILED_STATES = {"failed", "error", "cancelled", "canceled", "expired"}
DEFAULT_ASPECT_RATIO = "9:16"


# Mexico-specific H3 reroll stories. Each story keeps the product in one
# verified worn state and uses a playful visual device only for the time-jump
# between a matched before and after. The device is never a new product part.
MEXICO_FANTASY_STORIES: dict[int, dict[str, Any]] = {
    21: {
        "name": "Lotería de la cintura",
        "device": "colorful Mexican lotería cards and papel picado flutter through the air as a playful transition, with no readable card text",
        "voice": "Estaba gordita, nada cerraba. Una semana después: delgada y perfecto.",
        "beats": [
            "0.00-1.67s: Direct-to-camera before shot in a bright Mexican bedroom; she has a noticeably heavier silhouette with a fuller midsection and pulls at jeans that clearly will not close over her abdomen.",
            "1.67-3.33s: Same fixed camera and outfit; she struggles visibly with the waistband, her torso appears soft and rounded, and the button stays far apart.",
            "3.33-5.00s: Papel picado and colorful lotería-style cards swirl around her as a magical but clearly stylized time-jump; no readable text.",
            "5.00-6.67s: Coffee and a quick smile in a colorful Mexico-home kitchen; the patch is incidental and not centered.",
            "6.67-8.33s: One brief direct-camera inner-wrist confirmation, palm facing lens, one patch only, no mirror or reflection.",
            "8.33-10.00s: The cards snap into a cheerful confetti transition; keep the product out of focus.",
            "10.00-11.67s: Return to the exact opening camera and outfit one week later; her silhouette is visibly slimmer with a defined waist, flat abdomen, and the same jeans now button easily with room to spare.",
            "11.67-13.33s: She turns to show a narrow, toned waistline, stands taller and laughs with confidence; the body shape contrast is dramatic.",
            "13.33-15.00s: Final confident direct-to-camera pose with papel picado in the background; one brief small patch confirmation, then face and silhouette lead.",
        ],
    },
    22: {
        "name": "Alebrije cambio de look",
        "device": "a friendly fantastical alebrije silhouette and bright marigold colors move through the background during the time jump, never touching the patch",
        "voice": "Muy llena, pantalón imposible. Una semana: panza plana, me veo increíble.",
        "beats": [
            "0.00-1.67s: Before shot in a colorful Mexican apartment; she has a rounder, heavier figure with visible abdominal fullness and struggles to close high-waisted jeans that gap widely.",
            "1.67-3.33s: Fixed medium shot; her midsection appears soft and protruding, she looks at the camera with frustration and shakes her head while tugging at the waistband.",
            "3.33-5.00s: A playful alebrije-colored glow sweeps behind her like a fantasy mural coming alive; no readable text.",
            "5.00-6.67s: She moves through a marigold-decorated home, coffee in hand, patch only incidental.",
            "6.67-8.33s: Brief direct-camera palm-up inner-wrist confirmation on one wrist only; other wrist bare, no mirror.",
            "8.33-10.00s: The alebrije colors settle into a warm realistic room; the creator smiles and keeps moving.",
            "10.00-11.67s: Hard time jump back to the exact opening camera and outfit; her figure is dramatically slimmer with a flat stomach, narrow waist, and the jeans button easily.",
            "11.67-13.33s: She shows the loose fit and a toned, sculpted waistline through a natural turn, the transformation is striking.",
            "13.33-15.00s: Final joyful pose with marigolds and papel picado; patch appears briefly on the same inner wrist only.",
        ],
    },
    23: {
        "name": "Portal de cempasúchil",
        "device": "a glowing marigold arch opens as a surreal but elegant time portal; the after scene remains full-screen and physically continuous",
        "voice": "Gordita, pantalón imposible. Una semana: bajé peso, queda perfecto.",
        "beats": [
            "0.00-1.67s: Direct-to-camera before state in a marigold-decorated Mexican courtyard; she has a noticeably fuller figure with a rounded belly and jeans that will not close over her midsection.",
            "1.67-3.33s: Same framing; her torso appears heavy and soft, she exhales with effort and tugs at the tight waistband; no wrist close-up.",
            "3.33-5.00s: A glowing cempasúchil arch blooms behind her and creates a tasteful fantasy time-jump.",
            "5.00-6.67s: Realistic coffee-and-walk transition through a warm courtyard with papel picado overhead.",
            "6.67-8.33s: One short direct-camera palm-up inner-wrist check, one tiny patch, other hand bare, no reflection.",
            "8.33-10.00s: The marigold glow fades into natural daylight; keep the hand out of focus.",
            "10.00-11.67s: Exact opening camera and outfit one week later; her silhouette is dramatically leaner with a flat, toned abdomen and the same jeans close easily with space.",
            "11.67-13.33s: She steps forward with a slim, defined waistline and athletic posture, smiling directly at camera; the body transformation is obvious.",
            "13.33-15.00s: Final full-screen after pose under marigolds; brief same-wrist patch confirmation only.",
        ],
    },
    24: {
        "name": "Vapor de tamales",
        "device": "warm kitchen steam briefly turns into a whimsical golden ribbon for the time jump, without placing the patch near food or steam",
        "voice": "Mucha panza, nada cerraba. Una semana: gordura fuera, me veo delgada.",
        "beats": [
            "0.00-2.50s: Mexican home kitchen before state; she has a heavy, rounded midsection with visible belly protrusion and tries unsuccessfully to close jeans, then gives a comic frustrated look.",
            "2.50-5.00s: Same fixed camera and outfit; her torso appears full and soft, she leans toward the counter with effort while wrists stay low.",
            "5.00-7.50s: Steam from a covered kitchen pot becomes a brief golden fantasy ribbon, then clears; no product near the food.",
            "7.50-10.00s: She prepares coffee and gives one direct-camera palm-up inner-wrist confirmation away from counter; one patch only.",
            "10.00-12.50s: Exact opening camera and outfit one week later; her figure is visibly slimmer with a flat stomach and narrow waist, jeans button easily, posture light.",
            "12.50-15.00s: Final direct-to-camera kitchen pose showing a lean, sculpted waistline; one brief same-wrist patch confirmation.",
        ],
    },
    25: {
        "name": "Ritmo de mariachi",
        "device": "a playful mariachi rhythm makes the room pulse with colorful light streaks during the time jump; no costume or belt becomes a product",
        "voice": "Bien gordita, nada quedaba. Una semana: bajé montones, flaquita.",
        "beats": [
            "0.00-1.67s: Before state in a Mexican living room; she has a noticeably heavier build with a rounded belly, pulls at a tight waistband and the button stays far apart.",
            "1.67-3.33s: Same fixed camera; her midsection appears full and soft, she gives a comic 'no puede ser' reaction.",
            "3.33-5.00s: A mariachi-style beat triggers playful red, green and gold light streaks around the room, clearly fantasy and non-physical.",
            "5.00-6.67s: She sways lightly while making coffee; patch remains incidental and small.",
            "6.67-8.33s: Direct-camera palm-up inner-wrist confirmation, one patch only, no mirror or reflection.",
            "8.33-10.00s: The light streaks resolve into papel picado and the room becomes realistic again.",
            "10.00-11.67s: Exact opening camera and outfit one week later; her silhouette is dramatically leaner with a flat, toned waist and the jeans button with ease.",
            "11.67-13.33s: She makes a small confident dance showing a slim, sculpted waistline and lighter posture.",
            "13.33-15.00s: Final upbeat direct-to-camera pose; brief patch confirmation on the same wrist only.",
        ],
    },
    26: {
        "name": "Churro espiral",
        "device": "a golden churro-like spiral of light becomes a playful transition graphic in the air, never a product part and never a measurement",
        "voice": "Mucha panza, imposible cerrar. Una semana: grasa fuera, perfecto.",
        "beats": [
            "0.00-1.67s: Before state at a colorful Mexico street-food stand; she has a fuller figure with visible abdominal roundness and tries to close jeans that gap widely.",
            "1.67-3.33s: Same angle; her midsection appears heavy and soft, she laughs at the struggle and turns toward camera.",
            "3.33-5.00s: A whimsical golden spiral inspired by churro swirls circles the background and creates a magical time jump.",
            "5.00-6.67s: She walks through a bright plaza with papel picado; product remains incidental.",
            "6.67-8.33s: One direct-camera palm-up inner-wrist confirmation away from food; one patch only, no mirror.",
            "8.33-10.00s: Golden spiral dissolves into real sunlight and the camera returns to a natural UGC look.",
            "10.00-11.67s: Exact opening angle and outfit one week later; her figure is visibly slimmer with a flat stomach and narrow waist, jeans close easily.",
            "11.67-13.33s: She walks with a lean, athletic silhouette and confident posture, the body transformation is striking.",
            "13.33-15.00s: Final plaza hero with colorful flags; brief same-wrist patch confirmation, then face and silhouette.",
        ],
    },
    27: {
        "name": "Piñata del cambio",
        "device": "a bright piñata bursts into confetti at the time jump; confetti is celebratory only and never covers or duplicates the patch",
        "voice": "Muy pesada, nada cerraba. Una semana: bajé mucho, cerró perfecto.",
        "beats": [
            "0.00-1.67s: Before state in a colorful Mexican home; she has a rounder, heavier build with a protruding belly and tugs at jeans that visibly will not close.",
            "1.67-3.33s: Same fixed camera; her midsection appears full and rounded, she looks at camera with a playful defeated shrug.",
            "3.33-5.00s: A cheerful piñata pops in the background with confetti and creates a clearly fantastical time jump.",
            "5.00-6.67s: Coffee, desk and a short walk in one natural lifestyle flow; patch is background only.",
            "6.67-8.33s: Direct-camera palm-up inner-wrist confirmation, one patch only, other wrist bare, no mirror.",
            "8.33-10.00s: Confetti settles; the scene becomes realistic and the creator keeps speaking naturally.",
            "10.00-11.67s: Exact opening camera and outfit one week later; her silhouette is dramatically leaner with a flat, toned waist and jeans close easily.",
            "11.67-13.33s: She shows the slim, sculpted waistline and celebrates with a joyful movement, transformation is obvious.",
            "13.33-15.00s: Final colorful direct-to-camera hero, one brief same-wrist patch confirmation only.",
        ],
    },
    28: {
        "name": "Lucha libre contra el pantalón",
        "device": "a playful lucha-libre ring-light effect frames the before/after like a match, with no physical belt or costume changing into the product",
        "voice": "Gordita, pantalón ganó. Una semana: bajé peso, yo gané.",
        "beats": [
            "0.00-1.67s: Before state in a colorful Mexican room staged like a playful lucha arena; she has a fuller figure with visible belly roundness and jeans will not button.",
            "1.67-3.33s: Her midsection appears heavy and soft, she reacts like she lost a round but remains a normal creator.",
            "3.33-5.00s: A colorful ring-light flash and comic crowd-energy sound create a stylized time jump, no readable text.",
            "5.00-6.67s: She walks, drinks coffee and talks directly to camera; patch stays incidental.",
            "6.67-8.33s: Direct-camera palm-up inner-wrist check, one tiny patch only, no mirror or reflection.",
            "8.33-10.00s: The fantasy arena effect fades into the same realistic Mexican room.",
            "10.00-11.67s: Exact opening camera and outfit one week later; her figure is visibly slimmer with a flat stomach and narrow waist, jeans button smoothly.",
            "11.67-13.33s: She celebrates with a confident champion pose showing a lean, toned waistline, the transformation is dramatic.",
            "13.33-15.00s: Final direct-to-camera smile; one brief same-wrist patch confirmation, other wrist bare.",
        ],
    },
    29: {
        "name": "Mural que despierta",
        "device": "a Frida-inspired floral mural behind the creator gently blooms during the time jump, with tasteful Mexican color and no celebrity likeness",
        "voice": "Muy llena, escondía panza. Una semana: bajé mucho, orgullosa.",
        "beats": [
            "0.00-1.67s: Before state in front of a colorful Mexican mural; she has a rounder, heavier build with a protruding belly, pulls at a tight waistband and looks self-conscious.",
            "1.67-3.33s: Same fixed camera; her midsection appears full and soft, she covers the waistband briefly and looks back at camera.",
            "3.33-5.00s: Painted flowers on the mural bloom into a gentle fantasy animation, then settle.",
            "5.00-6.67s: She prepares coffee and walks past the mural with a relaxed posture; patch not centered.",
            "6.67-8.33s: One direct-camera palm-up inner-wrist confirmation, one patch only, no mirror or reflection.",
            "8.33-10.00s: The painted flowers return to a realistic mural as the time jump completes.",
            "10.00-11.67s: Exact opening camera and outfit one week later; her silhouette is dramatically slimmer with a flat, toned waist and jeans close comfortably.",
            "11.67-13.33s: She stands tall and proud showing a slim, sculpted waistline, the body transformation is obvious.",
            "13.33-15.00s: Final mural hero shot; brief same-wrist patch confirmation, then attention returns to her face.",
        ],
    },
    30: {
        "name": "Amanecer sobre la ciudad",
        "device": "a surreal Mexican rooftop sunrise sweeps the sky from deep blue to marigold gold as a time-jump transition",
        "voice": "Muy gordita, pesada. Una semana: bajé mucho, delgada.",
        "beats": [
            "0.00-1.67s: Before state on a Mexican rooftop at blue hour; she has a fuller figure with visible belly roundness and tries to button jeans that will not close.",
            "1.67-3.33s: Same fixed medium shot; her torso appears heavy and soft, she exhales with effort and faces the city.",
            "3.33-5.00s: A surreal marigold sunrise sweeps across the skyline as a tasteful fantasy time jump.",
            "5.00-6.67s: Realistic coffee and walking montage on the rooftop; patch remains incidental.",
            "6.67-8.33s: Direct-camera palm-up inner-wrist confirmation, one patch only, no mirror or reflected glass.",
            "8.33-10.00s: The sky settles into warm natural sunlight and the creator returns to direct UGC delivery.",
            "10.00-11.67s: Exact opening camera and outfit one week later; her figure is visibly slimmer with a flat stomach and narrow waist, jeans button easily.",
            "11.67-13.33s: She turns toward the skyline with a lean, sculpted waistline and light, confident posture, the transformation is striking.",
            "13.33-15.00s: Final golden rooftop hero; brief same-wrist patch confirmation, then face and silhouette lead.",
        ],
    },
}


def require_lk888_api_key() -> str:
    api_key = os.environ.get("LK888_API_KEY", "").strip() or os.environ.get("API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Missing LK888_API_KEY. Export it before running this script.")
    return api_key


def resolve_prompts_path(product_dir: Path, prompts_file: str) -> Path:
    candidate = Path(prompts_file)
    if candidate.is_absolute():
        return candidate
    return product_dir / prompts_file


def variant_reference_paths(product_dir: Path, variant: dict[str, Any]) -> list[Path]:
    raw_paths = variant.get("reference_images") or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    if not isinstance(raw_paths, list):
        raise RuntimeError("reference_images must be a path string or a list of path strings")

    paths: list[Path] = []
    for raw_path in raw_paths:
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = product_dir / path
        if not path.exists():
            raise RuntimeError(f"Missing variant reference image: {path}")
        paths.append(path)
    return paths


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def variant_protects_configuration(variant: dict[str, Any]) -> bool:
    if variant.get("protect_product_configuration") is True:
        return True
    risk = variant.get("generation_risk")
    return isinstance(risk, dict) and str(risk.get("level") or "").lower() in {"high", "critical"}


def omni_storyboard_identity_paths(product_dir: Path, variant: dict[str, Any], allow_override: bool = False) -> list[Path]:
    """Return v2 Omni references: storyboard, identity grid, optional operation grid.

    The first two are fixed: the chronological storyboard sets shot order and the
    identity grid sets product geometry. Any remaining explicitly declared
    state-change operation grid follows automatically as image 3. Otherwise one
    explicitly declared extra reference may use that slot. Omni accepts at most
    three images, so ambiguous overflow is rejected before a paid submission.
    """
    from v2_contract import load_identity, load_usage, local_file, require_qc

    identity = load_identity(product_dir)
    identity_sheet = local_file(product_dir, identity["output_path"])
    explicit_references = unique_paths(variant_reference_paths(product_dir, variant))
    variant_id = int(variant.get("variant_id", 0) or 0)
    canonical_storyboard = product_dir / "generated_images" / f"variant-{variant_id:02d}-storyboard.png"
    if canonical_storyboard.is_file() and canonical_storyboard not in explicit_references:
        explicit_references.insert(0, canonical_storyboard)
    storyboard = next(
        (
            path
            for path in explicit_references
            if path.resolve() != identity_sheet.resolve()
            and (
                "storyboard" in path.name.lower()
                or "storyboard" in str(load_json(path.with_suffix(".provenance.json"), {}).get("type", "")).lower()
            )
        ),
        None,
    )
    if storyboard is None:
        raise RuntimeError(
            "Omni reference mode requires an Image2-generated chronological storyboard in variant reference_images"
        )
    if not storyboard.with_suffix(".provenance.json").is_file():
        raise RuntimeError(f"Storyboard is missing provenance: {storyboard}")
    require_chronological_storyboard(
        product_dir, storyboard, variant,
        allow_override=allow_override,
    )
    require_qc(product_dir, [identity_sheet], "identity", override=allow_override)
    require_qc(product_dir, [storyboard], "storyboards", override=allow_override)
    protected_configuration = variant_protects_configuration(variant)
    usage = load_usage(product_dir)
    usage_sheet = local_file(product_dir, usage["output_path"])
    automatic_operation = None
    if usage_sheet.resolve() != identity_sheet.resolve() and not protected_configuration:
        require_qc(product_dir, [usage_sheet], "usage")
        automatic_operation = usage_sheet
    extra_references = [
        path
        for path in explicit_references
        if path.resolve() not in {
            storyboard.resolve(), identity_sheet.resolve(),
            usage_sheet.resolve(),
        }
    ]
    references = [storyboard, identity_sheet]
    if automatic_operation:
        references.append(automatic_operation)
    elif extra_references and not protected_configuration:
        references.append(extra_references.pop(0))
    if protected_configuration and extra_references:
        raise RuntimeError(
            "Protected Omni route accepts only the regenerated low-risk storyboard and identity grid; remove operation/extra references"
        )
    if extra_references:
        raise RuntimeError("Omni supports at most three images; remove extra variant references")
    return references


def require_chronological_storyboard(product_dir: Path, storyboard: Path, variant: dict[str, Any], allow_override: bool = False) -> None:
    """Filename/provenance labels alone cannot prove a real chronological grid.

    Require a separate current visual inspection bound to both image and routed
    timeline. This gate is local and happens before upload or paid submission.
    """
    from v2_contract import digest
    provenance = load_json(storyboard.with_suffix(".provenance.json"), {})
    from storyboard_contract import storyboard_spec
    spec = storyboard_spec(variant)
    if provenance.get("grid_spec") != spec:
        raise RuntimeError("Storyboard grid contract changed or is missing; regenerate and review")
    timeline = variant.get("storyboard_10s")
    if not isinstance(timeline, list) or len(timeline) < 2:
        raise RuntimeError("Omni requires a current multi-beat storyboard_10s")
    timeline_hash = hashlib.sha256(json.dumps(timeline, ensure_ascii=False, sort_keys=True,
                                              separators=(",", ":")).encode()).hexdigest()
    if provenance.get("timeline_sha256") != timeline_hash and not allow_override:
        raise RuntimeError("Storyboard timeline changed; regenerate and review")
    image_hash = digest(storyboard)
    if (provenance.get("sha256") != image_hash or not provenance.get("references")
            or not (provenance.get("provider") or provenance.get("image_provider"))
            or not (provenance.get("actual_prompt") or provenance.get("prompt"))):
        raise RuntimeError("Storyboard needs current image hash, provider, prompt and reference provenance")
    report_path = product_dir / "qc" / "storyboards" / f"{storyboard.stem}.json"
    review = load_json(report_path, {})
    if (not allow_override and (review.get("status") != "pass" or review.get("sha256") != image_hash
            or review.get("timeline_sha256") != timeline_hash
            or not isinstance(review.get("panel_count"), int) or review["panel_count"] != spec["panel_count"]
            or review.get("chronological") is not True or review.get("singleton_per_panel") is not True
            or review.get("visual_alignment") is not True or review.get("layout_matches") is not True
            or review.get("grid_spec") != spec
            or not review.get("reviewer") or not review.get("evidence"))):
        raise RuntimeError(f"Current visual storyboard review required: {report_path}; single-frame anchors are not accepted")
    if "chronological_storyboard" not in str(provenance.get("type") or ""):
        raise RuntimeError("Storyboard provenance must declare a chronological_storyboard type")


def existing_video_dir(product_dir: Path) -> Path:
    return product_dir / "videos"


def existing_variant_max(video_dir: Path) -> int:
    max_variant = 0
    for path in video_dir.glob("variant-*.mp4"):
        try:
            variant_id = int(path.stem.split("-", 1)[1])
        except Exception:
            continue
        max_variant = max(max_variant, variant_id)
    return max_variant


def upload_litterbox(path: Path, lifetime: str = "1h") -> str:
    command = [
        "curl",
        "--noproxy", "*",
        "--http1.1",
        "-fsS",
        "-F",
        "reqtype=fileupload",
        "-F",
        f"time={lifetime}",
        "-F",
        f"fileToUpload=@{path}",
        "https://litterbox.catbox.moe/resources/internals/api.php",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
    url = result.stdout.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"Unexpected upload response for {path}: {url[:300]}")
    return url


def upload_uguu(path: Path) -> str:
    with path.open("rb") as file_handle:
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            "https://uguu.se/upload.php",
            files={"files[]": (path.name, file_handle, "image/png")},
            timeout=120,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Uguu upload failed HTTP {response.status_code}: {response.text[:500]}")
    data = response.json()
    files = data.get("files") or []
    url = files[0].get("url") if files and isinstance(files[0], dict) else ""
    if not data.get("success") or not url:
        raise RuntimeError(f"Unexpected Uguu upload response for {path}: {response.text[:500]}")
    return url


def with_retries(label: str, attempts: int, backoff_seconds: float, operation: Any) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if attempt >= attempts:
                break
            wait_seconds = backoff_seconds * attempt
            print(f"[retry] {label} attempt {attempt}/{attempts} failed: {error}", flush=True)
            time.sleep(wait_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{label} failed without a captured error")


def upload_reference(
    path: Path,
    host: str,
    lifetime: str,
    upload_retries: int,
    retry_backoff_seconds: float,
) -> tuple[str, int, str]:
    now = int(time.time())
    if host == "uguu":
        url = with_retries(
            f"upload {path.name} to uguu",
            upload_retries,
            retry_backoff_seconds,
            lambda: upload_uguu(path),
        )
        return url, now + 23 * 60 * 60, "uguu.se"
    url = with_retries(
        f"upload {path.name} to litterbox",
        upload_retries,
        retry_backoff_seconds,
        lambda: upload_litterbox(path, lifetime=lifetime),
    )
    return url, now + 50 * 60 if lifetime == "1h" else now + 10 * 60, "litterbox.catbox.moe"


def upload_references(
    product_dir: Path,
    reference_images: list[Path],
    lifetime: str,
    host: str,
    upload_retries: int,
    retry_backoff_seconds: float,
) -> list[dict[str, str]]:
    cache_path = product_dir / "videos_lk888" / "uploaded_reference_urls.json"
    cache = load_json(cache_path, {"uploads": {}})
    uploads: dict[str, Any] = dict(cache.get("uploads", {}))
    changed = False
    results: list[dict[str, str]] = []
    now = int(time.time())
    for image_path in reference_images:
        relative = str(image_path.relative_to(product_dir))
        cached = uploads.get(relative) or {}
        url = cached.get("url")
        expires_at = int(cached.get("expires_at", 0) or 0)
        cached_host = cached.get("host", "")
        if not url or cached_host != host or expires_at - now < 900:
            print(f"[upload] {relative}", flush=True)
            url, expires_at, stored_host = upload_reference(
                image_path,
                host,
                lifetime,
                upload_retries,
                retry_backoff_seconds,
            )
            uploads[relative] = {"url": url, "uploaded_at": now, "expires_at": expires_at, "host": stored_host}
            changed = True
        results.append({"path": relative, "url": url})
    if changed:
        write_json(cache_path, {"uploads": uploads})
    return results


def append_native_audio_instruction(prompt: str, voice_lines: Any, locale: str) -> str:
    voice = voice_description(locale)
    language_rule = language_clause(locale)
    line = ""
    if isinstance(voice_lines, list) and voice_lines:
        first = voice_lines[0]
        if isinstance(first, dict):
            line = str(first.get("line") or first.get("text") or "").strip()
        else:
            line = str(first).strip()
    elif isinstance(voice_lines, str):
        line = voice_lines.strip()
    audio_block = (
        f"\n\nNATIVE AUDIO: Generate natural native audio inside the video: a bright {voice} ecommerce creator voice, energetic but not robotic, with subtle upbeat social-ad background music. {language_rule} "
        "No subtitles, no captions, no readable on-screen text, no labels, no social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, no watermarks. "
    )
    if line:
        audio_block += f"Spoken voiceover, complete within 10 seconds: \"{line}\""
    else:
        audio_block += "Use a short natural product-demo voiceover that finishes within 10 seconds."
    return prompt + audio_block


def prompt_has_native_audio(prompt: str) -> bool:
    upper_prompt = prompt.upper()
    return "NATIVE AUDIO" in upper_prompt or "VOICEOVER" in upper_prompt


def compact_voiceover_line(
    voice_lines: Any,
    fallback: str = "",
    max_words: int = 18,
    locale: str | None = None,
) -> str:
    """Join the timed voiceover into one speakable line.

    The old implementation sliced on whitespace (``words[:max_words]``), which
    left a dangling half-sentence and mis-measured Japanese, where a whole line
    is a single whitespace token. Trimming now happens per locale through
    `voice_locale.trim_voiceover`, which keeps whole sentences.
    """
    lines: list[str] = []
    if isinstance(voice_lines, list):
        for item in voice_lines:
            if isinstance(item, dict):
                text = str(item.get("line") or item.get("text") or "").strip()
            else:
                text = str(item).strip()
            if text:
                lines.append(text)
    elif isinstance(voice_lines, str):
        lines.append(voice_lines.strip())
    text = " ".join(lines) or fallback
    text = text.replace("—", ", ")
    if not text.strip():
        return ""
    resolved = normalize_locale(locale)
    if not resolved:
        # No locale known yet (direct helper use): keep the whole line rather
        # than risk emitting a truncated fragment.
        return " ".join(text.split())
    return trim_voiceover(text, resolved)


def first_voice_line(voice_lines: Any, fallback: str = "") -> str:
    line = ""
    if isinstance(voice_lines, list) and voice_lines:
        first = voice_lines[0]
        if isinstance(first, dict):
            line = str(first.get("line") or first.get("text") or "").strip()
        else:
            line = str(first).strip()
    elif isinstance(voice_lines, str):
        line = voice_lines.strip()
    return (line or fallback).replace("—", ", ")


def overlay_callouts(variant: dict[str, Any], enabled: bool) -> list[str]:
    if not enabled:
        return []
    raw_callouts = variant.get("on_screen_callouts") or []
    cleaned: list[str] = []
    for item in raw_callouts:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("label") or "").strip()
        else:
            text = ""
        if not text:
            continue
        cleaned.append(text[:18])
        if len(cleaned) >= 2:
            break
    return cleaned


def power_connection_clause(brief: dict[str, Any], budget: int | None = None) -> str:
    """Render the product's confirmed power chain as a mandatory prompt clause.

    Scraped listings usually show only the cable leaving the product, so the
    video model invents the connection: a bare mains plug, a USB plug pushed
    into a wall socket, or a lamp glowing with nothing plugged in. When the
    brief records the real chain, state it and forbid those inventions.

    A budget caps the clause for models with a hard prompt length limit. Whole
    list items are dropped from the least critical end rather than cutting
    mid-sentence, so the chain itself is never truncated.
    """
    power = brief.get("power_connection") or {}
    if not power:
        return ""
    sources = [str(item) for item in (power.get("valid_power_sources") or [])]
    forbidden = [str(item) for item in (power.get("forbidden") or [])]
    head = (
        "POWER CONNECTION, must be physically readable in the same shot: "
        + str(power.get("cable_exit", "")).strip() + " "
        + str(power.get("connector_on_cable", "")).strip() + " "
        + str(power.get("required_visible_chain", "")).strip() + " "
    ).strip()
    sources_text = ("Acceptable sources: " + "; ".join(sources) + ".") if sources else ""

    def assemble(keep_forbidden: list[str]) -> str:
        forbidden_text = ("Never show: " + "; ".join(keep_forbidden) + ".") if keep_forbidden else ""
        return " ".join(part for part in (head, sources_text, forbidden_text) if part)

    clause = assemble(forbidden)
    if budget and len(clause) > budget:
        while forbidden:
            forbidden = forbidden[:-1]
            clause = assemble(forbidden)
            if len(clause) <= budget:
                break
    if budget and len(clause) > budget:
        clause = clause[:budget].rstrip()
    return clause


def append_safe_audio_test_instruction(prompt: str, voice_lines: Any, locale: str) -> str:
    voice = voice_description(locale)
    language = language_name(locale)
    safe_line = first_voice_line(voice_lines, "Place the trap outside after adding bait.")
    audio_block = (
        f"\n\nNATIVE AUDIO TEST: Include one short natural sentence in {language}. The speaker is a {voice}. "
        "No music, no singing, no hype, no slang, no labels, no subtitles, no captions, no readable on-screen text, no social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, no watermarks. "
        f"Speak exactly this one sentence and nothing else: \"{safe_line}\""
    )
    return prompt + audio_block


def append_safe_native_audio_instruction(prompt: str, voice_lines: Any, locale: str) -> str:
    voice = voice_description(locale)
    language = language_name(locale)
    safe_line = first_voice_line(voice_lines, "Here is how the product works.")
    audio_block = (
        f"\n\nNATIVE AUDIO: Include one short natural voice line in {language}. The speaker is a {voice}. {language_clause(locale)} "
        "No music, no singing, no hype words, no slang, no labels, no subtitles, no captions, no readable on-screen text, no social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, no watermarks. "
        f"Speak exactly this one sentence and nothing else: \"{safe_line}\""
    )
    return prompt + audio_block


def append_mid_native_audio_instruction(prompt: str, voice_lines: Any, callouts: list[str], locale: str) -> str:
    voice = voice_description(locale)
    safe_line = compact_voiceover_line(
        voice_lines, "Watch this tiny upgrade make the setup feel easier.", locale=locale
    )
    overlay_block = ""
    if callouts:
        safe_callouts = []
        for item in callouts[:2]:
            text = re.sub(r"[^\x00-\x7F]+", "", str(item))
            text = re.sub(r"[^A-Za-z0-9 %&+/-]", "", text)
            text = " ".join(text.split()[:3])[:18].strip()
            if text:
                safe_callouts.append(text)
        joined = ", ".join(f"\"{item}\"" for item in safe_callouts)
        overlay_block = (
            f" Allow only {len(safe_callouts)} stylish short-form creator typography feature-tag overlays: {joined}. "
            "Render them as stylish short-form creator typography: bold rounded pill labels, warm vibrant accent tints, compact pop-up badges, modern fashion-tag feel. Keep them brief and not synchronized with the spoken voiceover. Never render full-sentence captions, subtitles, transcripts, lower thirds, karaoke text, social media icons, platform logos, camera/reel icons, reaction icons, app UI chrome, watermarks, or emoji text."
            if safe_callouts
            else ""
        )
    audio_block = (
        f"\n\nNATIVE AUDIO: Generate natural native audio inside the video: a bright {voice} lifestyle-commerce creator voice, stylish, warm, emotionally engaged, friendly, clear, not robotic, not corporate. "
        f"{language_clause(locale)} "
        f"Spoken voiceover, complete within 10 seconds: \"{safe_line}\" "
        "Add subtle upbeat modern lifestyle background music under the voice at low volume, no lyrics, plus light real handling sounds. "
        "No subtitles, no captions, no full-sentence labels, no emoji text, no social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, and no watermarks. The only allowed readable text is the explicitly allowed tiny feature-tag overlay words."
    )
    return prompt + overlay_block + audio_block


def append_asmr_audio_instruction(prompt: str) -> str:
    audio_block = (
        "\n\nNATIVE AUDIO: Generate clean ASMR-style native audio only. No spoken voiceover, no dialogue, no narration, no music. "
        "Use crisp realistic kitchen sounds only: suction click, vegetable tapping on the counter, gentle pusher contact, smooth crank rotation, stainless drum rasp, crisp slicing or grating texture, and shreds or slices falling into a glass bowl. "
        "Keep the sound intimate, detailed, satisfying, and natural. No subtitles, no captions, no social media icons, no platform logos, no camera/reel icons, no reaction icons, no app UI, no watermarks."
    )
    return prompt + audio_block


def lk888_post(api_key: str, endpoint: str, payload: dict[str, Any], base_url: str) -> dict[str, Any]:
    response = requests.post(
        f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1000]}")
    data = response.json()
    if data.get("code") not in (None, 200):
        raise RuntimeError(f"API error: {json.dumps(data, ensure_ascii=False)}")
    return data


def lk888_get(api_key: str, endpoint: str, base_url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.get(
        f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}",
        headers={"Authorization": f"Bearer {api_key}"},
        params=params,
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1000]}")
    data = response.json()
    if data.get("code") not in (None, 200):
        raise RuntimeError(f"API error: {json.dumps(data, ensure_ascii=False)}")
    return data


def build_model_params(args: argparse.Namespace, image_urls: list[str]) -> dict[str, Any]:
    if args.model == "minimax-h3":
        # MiniMax H3 uses the all-purpose reference-image field `image_url`.
        # Do not pass Omni's `images` field here: H3 interprets that field as
        # first/last-frame input rather than chronological references.
        return {
            "aspect_ratio": args.aspect_ratio,
            "duration": str(args.duration),
            "resolution": args.resolution,
            "image_url": image_urls[:9],
        }
    if args.model not in {"omni-flash", "omni_flash-10s"}:
        raise RuntimeError(f"Unsupported video model {args.model}")
    params: dict[str, Any] = {
        "aspect_ratio": args.aspect_ratio,
        "images": image_urls[:7] if args.model == "omni_flash-10s" else image_urls[:3],
    }
    if args.model == "omni-flash":
        params["duration"] = str(args.duration)
        params["resolution"] = args.resolution
        params["enhance_prompt"] = args.enhance_prompt
    if args.enable_upsample is not None:
        params["enable_upsample"] = args.enable_upsample
    return params


def extract_task_ids(create_response: dict[str, Any]) -> list[str]:
    data = create_response.get("data") if isinstance(create_response.get("data"), dict) else create_response
    raw_ids: list[Any] = []
    for key in ["task_id", "id", "任务id", "任务ID"]:
        if data.get(key):
            raw_ids.append(data[key])
    for key in ["任务ids", "task_ids", "ids"]:
        value = data.get(key)
        if isinstance(value, list):
            raw_ids.extend(value)
    ids = [str(item) for item in raw_ids if item]
    return list(dict.fromkeys(ids))


def normalize_status(status_response: dict[str, Any]) -> dict[str, Any]:
    data = status_response.get("data") if isinstance(status_response.get("data"), dict) else status_response
    return data if isinstance(data, dict) else status_response


OMNI_PROMPT_CHAR_LIMIT = 4000
OMNI_MODELS = {"omni-flash", "omni_flash-10s"}
MINIMAX_MODELS = {"minimax-h3"}


def enforce_prompt_char_limit(prompt: str, limit: int = OMNI_PROMPT_CHAR_LIMIT, label: str = "Omni") -> str:
    """Backstop against the provider's hard prompt character cap.

    The provider rejects an over-long prompt outright (for example
    "提示必须为4000个字符或更少"), so no prompt may leave the client over budget.
    """
    if len(prompt) <= limit:
        return prompt
    raise RuntimeError(f"{label} prompt exceeds {limit} characters; shorten the canonical storyboard and regenerate its references, never truncate panel descriptions")


def compact_omni_prompt(
    variant: dict[str, Any],
    duration: str,
    reference_mode: str = "omni-reference",
    product_dir: Path | None = None,
    limit: int | None = None,
    voice_locale: str | None = None,
    effect_first: bool = False,
    mexico_fantasy: bool = False,
) -> str:
    """Fit an Omni prompt inside the provider's 4,000-character hard limit.

    Each clause used to carry its own slice length with no global budget, so a
    variant with a power-chain block rendered around 4,750 characters and every
    submission was rejected. Render with full slices first, then binary-search
    one scale factor for the elastic creative clauses until the whole prompt
    fits. The identity lock, SKU, power chain, spoken line and safety tail never
    scale, so mandatory content always survives.
    """
    cap = limit or OMNI_PROMPT_CHAR_LIMIT

    def clipped(value: Any, width: int) -> str:
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value or "")
        text = re.sub(r"\s+", " ", text).strip()
        return text[:width].rstrip()

    def scaled(value: Any, width: int, factor: float, weight: float = 1.0) -> str:
        # weight above 1 shrinks optional context faster. Canonical storyboard text
        # is preserved in full outside this helper.
        effective = width if factor >= 1.0 else max(24, int(round(width * factor ** weight)))
        return clipped(value, effective)

    # Only the reviewed canonical timeline supplies visual beats.
    storyboard = variant.get("storyboard_10s") or []
    if not storyboard:
        raise RuntimeError("Current storyboard_10s is required; legacy shot plans cannot replace it")
    canonical_beats = storyboard_video_beats(variant)
    # Spoken lines are carried by the native-audio clause below. Keeping them
    # out of the visual beat map preserves the exact panel sequence while
    # avoiding duplicated prompt content and the provider's 4k hard limit.
    beats = [f"{item['time']}: {item['visual']}" for item in canonical_beats]
    story = MEXICO_FANTASY_STORIES.get(int(variant.get("variant_id", 0) or 0)) if mexico_fantasy else None
    if effect_first:
        beats = [
            "0.00-1.67s: Same Mexican creator in a direct-to-camera bedroom shot before the routine, tugging a visibly tight waistband and looking frustrated; no mirror and no wrist framing.",
            "1.67-3.33s: Matched before-state medium shot from the same fixed camera, the same jeans remain visibly difficult to button; both wrists stay out of frame.",
            "3.33-5.00s: Morning coffee in a Mexican home, relaxed day-in-the-life framing; patch is not a visual subject.",
            "5.00-6.67s: Working at a desk, natural gesture and direct-to-camera confidence; keep both wrists mostly out of frame.",
            "6.67-8.33s: Light walking or movement outside the home, showing lifestyle continuity rather than product detail.",
            "8.33-10.00s: One brief direct-to-camera hand confirmation, creator's palm facing the lens with fingers up and the palm-side inner wrist visible; one tiny patch only, no mirror, no reflection, no hand rotation.",
            "10.00-11.67s: Natural one-week time jump through a changed day and brighter mood, without readable text, calendar or graphics.",
            "11.67-13.33s: Return to the exact opening camera and outfit, now the same jeans button comfortably and the waistline reads visibly more defined; direct-to-camera smile, no mirror.",
            "13.33-15.00s: Final full-screen after-state hero, then one brief direct-to-camera palm-up inner-wrist confirmation on the same single wrist; other wrist completely bare.",
        ]
        if story:
            beats = story["beats"]
    protected_configuration = variant_protects_configuration(variant)
    operation_sheet = False
    if product_dir:
        try:
            from v2_contract import load_identity, load_usage, local_file
            identity_record = load_identity(product_dir)
            usage_record = load_usage(product_dir)
            operation_sheet = not protected_configuration and (
                local_file(product_dir, usage_record["output_path"]).resolve()
                != local_file(product_dir, identity_record["output_path"]).resolve()
            )
        except RuntimeError:
            operation_sheet = False
    mode_instruction = (
        "Use two all-purpose references: image 1 is the regenerated low-risk chronological storyboard and image 2 is the product identity grid. Keep the product in the same ready-to-use configuration shown in the storyboard; no operation grid or setup transition is used."
        if protected_configuration else (
            "Use three all-purpose references: image 1 is the chronological storyboard, image 2 is the product identity grid, and image 3 is the evidence-safe state-change sheet. Never invent a midpoint omitted from image 3."
            if operation_sheet else
            "Use two all-purpose references: image 1 is the chronological storyboard and image 2 is the product identity grid."
        )
    )
    voice_items = variant.get("voiceover_script_10s") or variant.get("voiceover_script_8s") or []
    if isinstance(voice_items, list):
        voice = " ".join(str(item.get("line", "")) if isinstance(item, dict) else str(item) for item in voice_items)
    else:
        voice = str(voice_items)
    if effect_first:
        voice = "Antes me costaba notar cambios… una semana después me veo más ligera y me siento increíble. U-PATCH ya es parte de mi rutina."
    if story:
        voice = story["voice"]
    brief = load_json(product_dir / "product_brief.json", {}) if product_dir else {}
    # The resolved locale is passed in so the compact path can no longer ignore
    # a batch-level or CLI locale and silently speak English.
    resolved_locale = normalize_locale(voice_locale) or normalize_locale(variant.get("voice_locale"))
    if not resolved_locale:
        raise VoiceLocaleError(
            "compact_omni_prompt requires a resolved voice locale; refusing to default to English."
        )
    voice_desc = voice_description(resolved_locale)
    normalize_creator_persona(variant.get("creator_persona"), resolved_locale)
    normalize_creator_persona(variant.get("scene_imagination"), resolved_locale)
    for panel in canonical_beats:
        normalize_creator_persona(panel.get("visual"), resolved_locale)
    for index, item in enumerate(voice_items if isinstance(voice_items, list) else [voice_items], start=1):
        line = item.get("line") if isinstance(item, dict) else item
        validate_spoken_text(line, resolved_locale, f"voiceover line {index}")
    for index, panel in enumerate(canonical_beats, start=1):
        validate_spoken_text(panel.get("spoken"), resolved_locale, f"storyboard panel {index} spoken line", allow_empty=True)
    language_rule = language_clause(resolved_locale)
    power_line = power_connection_clause(brief, budget=720)
    identity = variant.get("product_fidelity_block") or brief.get("confirmed_identity") or []
    misuse = variant.get("negative_prompt") or brief.get("misuse_risks_to_avoid") or []
    risk_direction = variant.get("safe_demo_direction") or {}
    forbidden_actions = variant.get("unsafe_actions_omitted") or []
    effect_first_block = (
        "EFFECT-FIRST STORY FOR THIS TAKE: make the before/after result the hero, not the patch. "
        "Use sequential full-screen moments with the same Mexican creator, the same fixed camera, same outfit and matched lighting. "
        "0-3s BEFORE: direct-to-camera, the same jeans visibly pinch and are hard to button; show the problem clearly. "
        "3-10s ROUTINE: quick natural Mexico-home day-in-the-life beats—coffee, desk, walking or light movement—with the patch only incidental and never a close-up. "
        "10-15s AFTER: return to the exact opening camera and outfit one week later; the same jeans button comfortably, the waistline reads visibly more defined, and she smiles with confidence. "
        "Make the contrast dramatic but believable through a hard time-jump cut, never an instant body morph. No split screen, collage, comparison graphic, measurements, captions, readable text, mirror or reflection. "
        "ONE-PATCH LOCK: exactly one patch total on the creator's right inner wrist only; the other wrist and hand must remain completely bare in every frame. Never duplicate the patch through a mirror, reflection, background or second wrist. "
        "HAND DISPLAY LOCK: when the patch is shown, use a direct camera or tabletop shot, never a mirror; palm faces the lens, fingers point upward, palm-side inner wrist and wrist crease are visible, patch sits just below the palm crease. Never show the back of the hand, outer wrist or an inverted/rotated hand. "
        "PATCH VISIBILITY BUDGET: show the single small patch clearly only twice for a brief confirmation; do not repeatedly zoom or center it. The patch is a tiny flat round patch, never a strap, wristband or bracelet. "
        + (
            f"MEXICO FANTASY DEVICE: {story['device']} Concept name: {story['name']}. Keep the fantasy device playful, tasteful and subordinate to the before/after waistline contrast; it must not create, transform or duplicate the product. "
            if story else ""
        )
        + "Spanish voiceover must emphasize the before/after feeling: ‘Antes me costaba notar cambios… una semana después me veo más ligera y me siento increíble. U-PATCH ya es parte de mi rutina.’ "
        if effect_first else ""
    )
    protected_rule = (
        f"LOW-RISK ROUTE: {clipped(risk_direction, 360)}. The product starts and ends in one identical verified ready-to-use configuration. "
        "Its topology, connections, geometry and part count never change. Show only ready-state use, result/detail proof, creator reaction and gentle camera motion. "
        f"FORBIDDEN PRODUCT ACTIONS: {clipped(forbidden_actions, 420)}. "
        if protected_configuration else ""
    )
    def render(factor: float) -> str:
        sku_colourway = clipped(variant.get("sku_colourway"), 240)
        # An absent colourway used to render an empty
        # "MANDATORY SKU FOR THIS VIDEO: ." clause that pinned nothing.
        sku_clause = f"MANDATORY SKU FOR THIS VIDEO: {sku_colourway}. " if sku_colourway else (
            "No colourway split exists for this listing: keep the single SKU shown in image 2 exactly as it is. "
        )
        return (
            f"Create exactly one {duration}-second {variant.get('target_frame_aspect_ratio') or '9:16'} realistic creator-style product video. {mode_instruction} "
            f"{VIDEO_SINGLE_CANVAS_RULE} "
            f"CASTING LOCK: keep {creator_market_identity(resolved_locale)} throughout, with one consistent person, wardrobe, room, lighting and gestures. "
            "Show exactly ONE product; never duplicate it in hands, furniture, mirrors, reflections or screens. "
            f"LOCAL MARKET: this ad targets {region_name(resolved_locale)}; the creator, setting, props and gestures must read as a natural local product demo for that market, never a generic US-style shoot. "
            + protected_rule
            + f"PRODUCT TRUTH AND IDENTITY LOCK: {scaled(identity, 700, factor)}. "
            "Match image 2 for silhouette, parts, proportions and controls; if SKU colours differ, use the single colourway shown in image 1. "
            + sku_clause
            + (power_line + " " if power_line else "")
            + f"FORBIDDEN DRIFT: {scaled(misuse, 600, factor)}. Never morph, resize, recolour, add branding or invent controls. "
            f"CONCEPT: {scaled(variant.get('title'), 180, factor, 0.8)}. HOOK: {scaled(variant.get('hook'), 320, factor, 0.8)}. "
            f"PRIMARY FUNCTION: {scaled(variant.get('primary_function_focus'), 320, factor, 0.8)}. "
            f"SCENE: {scaled(variant.get('scene_imagination'), 650, factor, 0.8)}. "
            + effect_first_block
            + f"SHOT PLAN: follow these chronological beats across all {duration} seconds: {' | '.join(beats or storyboard)}. "
            f"SUPPORTED ACTION: {scaled(variant.get('usage_logic'), 500, factor, 1.8)}. "
            f"PAYOFF: {scaled(variant.get('proof_moment'), 340, factor, 1.8)}. "
            f"NATIVE AUDIO: {voice_desc} creator voice, natural and warm. Speak exactly: {clipped(voice, 240)}. "
            f"{language_rule} Do not add speech. Add subtle room and product sounds and low music without singing. "
            "No subtitles, overlays, logos, watermarks, app UI, extra accessories, extra products or unsupported claims. Natural handheld motion."
        )

    prompt = render(1.0)
    if len(prompt) > cap:
        low, high = 0.02, 1.0
        for _ in range(28):
            mid = (low + high) / 2.0
            if len(render(mid)) <= cap:
                low = mid
            else:
                high = mid
        prompt = render(low)
    return enforce_prompt_char_limit(prompt, cap, "Omni compact")


def poll_task(api_key: str, task_id: str, base_url: str, poll_seconds: int, status_endpoint: str) -> dict[str, Any]:
    transient_errors = 0
    while True:
        try:
            raw = lk888_get(api_key, status_endpoint, base_url, params={"task_id": task_id})
            transient_errors = 0
        except requests.RequestException as error:
            transient_errors += 1
            if transient_errors > 12:
                raise
            print(f"[poll] task={task_id} transient network error {transient_errors}/12: {error}", flush=True)
            time.sleep(poll_seconds)
            continue
        status = normalize_status(raw)
        state = str(status.get("state") or status.get("status_group") or status.get("status") or "").lower()
        is_final = bool(status.get("is_final"))
        print(f"[poll] task={task_id} state={state} final={is_final} progress={status.get('progress', '')}", flush=True)
        if is_final:
            if state in FAILED_STATES or status.get("error"):
                raise RuntimeError(f"Task failed: {json.dumps(status, ensure_ascii=False)}")
            return status
        if state in FAILED_STATES:
            raise RuntimeError(f"Task failed: {json.dumps(status, ensure_ascii=False)}")
        time.sleep(poll_seconds)


def process_variant(product_dir: Path, variant: dict[str, Any], api_key: str, args: argparse.Namespace) -> dict[str, Any]:
    from v2_contract import active, check_existing_video, record_video, require_qc, validate_scene_chain, video_contract
    variant_id = int(variant.get("variant_id", 0))
    output_dir = existing_video_dir(product_dir)
    output_path = output_dir / f"variant-{variant_id:02d}.mp4"
    v2_active = active(product_dir)
    # Resolve the spoken locale once, before any prompt is rendered. Both the
    # compact and the full prompt path consume this value, so a declared market
    # can no longer be silently overridden by an English default, and an
    # undeclared market fails here instead of shipping English audio.
    brief = load_json(product_dir / "product_brief.json", {})
    manifest = load_json(product_dir / "product_manifest.json", {})
    try:
        voice_resolution = resolve_voice_locale(
            variant=variant,
            brief=brief if isinstance(brief, dict) else {},
            manifest=manifest if isinstance(manifest, dict) else {},
            explicit=getattr(args, "voice_locale", "") or getattr(args, "market", ""),
            product_dir=product_dir,
        )
    except VoiceLocaleError as error:
        raise RuntimeError(f"{product_dir.name} variant {variant_id:02d}: {error}") from error
    voice_locale = voice_resolution.locale
    from generate_ugc_prompts import validate_voiceover_language
    validate_voiceover_language(variant, voice_locale, str(manifest.get("product_name") or product_dir.name))
    if output_path.exists() and not args.force and not v2_active:
        return {"variant_id": variant_id, "status": "skipped_existing", "output_path": str(output_path.relative_to(product_dir))}
    if args.reference_mode != "omni-reference":
        raise RuntimeError("This pipeline supports only --reference-mode omni-reference")
    if not v2_active:
        raise RuntimeError("Omni reference submission requires the v2 identity lock and storyboard QC chain")
    from storyboard_contract import storyboard_spec
    spec = storyboard_spec(variant)
    if args.aspect_ratio != spec["targetFrameAspectRatio"]:
        raise RuntimeError("Video aspect ratio differs from storyboard panels; regenerate for the requested format")
    reference_images = omni_storyboard_identity_paths(
        product_dir, variant,
        allow_override=bool(getattr(args, "allow_unverified_references", False)),
    )
    if not reference_images:
        raise RuntimeError(f"Missing generated reference image(s) for variant {variant_id}")
    if v2_active:
        # A generated storyboard can live in an append-only run folder rather
        # than the canonical generated_images directory. Its provenance file is
        # the durable proof that it is an Image2-generated scene reference.
        scene_refs = [p for p in reference_images if p.with_suffix(".provenance.json").is_file()]
        if not scene_refs:
            raise RuntimeError("v2 video requires generated scene frames")
        validate_scene_chain(
            product_dir,
            scene_refs,
            override=bool(getattr(args, "allow_unverified_references", False)),
        )
        require_qc(product_dir, scene_refs, "storyboards",
                   override=bool(getattr(args, "allow_unverified_references", False)))
    reference_limit = (
        7 if args.model == "omni_flash-10s"
        else 3 if args.model == "omni-flash"
        else 9 if args.model == "minimax-h3"
        else 3
    )
    scale_lock = str(variant.get("_physical_scale_lock") or "").strip()
    scale_suffix = (" STRICT PHYSICAL SCALE THROUGHOUT: " + scale_lock) if scale_lock else ""
    omni_limited = args.model in OMNI_MODELS
    # Always rebuild from the reviewed canonical timeline; a saved video_prompt may be stale.
    budget = OMNI_PROMPT_CHAR_LIMIT - len(scale_suffix) if omni_limited else 1_000_000
    base_prompt = compact_omni_prompt(
        variant, str(args.duration), args.reference_mode, product_dir, limit=budget,
        voice_locale=voice_locale, effect_first=bool(getattr(args, "effect_first", False)),
        mexico_fantasy=bool(getattr(args, "mexico_fantasy", False)),
    )
    if scale_suffix:
        base_prompt += scale_suffix
    expected = video_contract(product_dir, reference_images[:reference_limit], args.model, base_prompt, {
        "aspect_ratio": args.aspect_ratio, "duration": str(args.duration),
        "audio_duration": str(args.audio_duration), "resolution": args.resolution,
        "generate_audio": bool(args.generate_audio), "enhance_prompt": args.enhance_prompt,
        "audio_style": args.audio_style, "light_overlay": bool(args.light_overlay),
        "safe_audio_test": bool(args.safe_audio_test), "enable_upsample": args.enable_upsample,
        "reference_mode": args.reference_mode,
        "voice_locale": voice_locale,
        "voice_locale_source": voice_resolution.source,
        "market": voice_resolution.market,
        "base_url": args.base_url, "status_endpoint": args.status_endpoint,
    }) if v2_active else {}
    if output_path.exists() and not args.force:
        check_existing_video(product_dir, output_path, expected)
        return {"variant_id": variant_id, "status": "skipped_existing_verified_v2",
                "output_path": str(output_path.relative_to(product_dir))}
    uploads = upload_references(
        product_dir,
        reference_images[:reference_limit],
        args.upload_lifetime,
        args.upload_host,
        args.upload_retries,
        args.retry_backoff_seconds,
    )
    callouts = overlay_callouts(variant, args.light_overlay)
    voiceover = variant.get("voiceover_script_10s") or variant.get("voiceover_script_8s")
    if args.audio_style == "none" or prompt_has_native_audio(base_prompt):
        prompt = base_prompt
    else:
        prompt = (
            append_safe_audio_test_instruction(base_prompt, voiceover, voice_locale) if args.safe_audio_test else (
                append_asmr_audio_instruction(base_prompt)
                if args.audio_style == "asmr"
                else
                append_mid_native_audio_instruction(base_prompt, voiceover, callouts, voice_locale)
                if args.audio_style == "mid"
                else append_native_audio_instruction(base_prompt, voiceover, voice_locale)
                if args.audio_style == "legacy"
                else append_safe_native_audio_instruction(base_prompt, voiceover, voice_locale)
            )
        )
    if args.model in OMNI_MODELS:
        # Last gate before the request: audio or scale suffixes appended above
        # can still push an otherwise-fitting prompt past the provider cap.
        prompt = enforce_prompt_char_limit(prompt)
    params = build_model_params(args, [item["url"] for item in uploads])
    # Omni's v1 contract accepts exactly model, prompt and params.
    payload = {"model": args.model, "prompt": prompt, "params": params}
    print("\n".join(format_production_notice(
        product_dir.name, variant_id, variant, args.model, args.reference_mode,
        reference_images[:reference_limit],
    )), flush=True)
    print(
        f"[params] aspect_ratio={args.aspect_ratio} duration={args.duration} "
        f"resolution={args.resolution} reference_mode={args.reference_mode} "
        f"references={len(params.get('images') or params.get('image_url') or [])}",
        flush=True,
    )
    print(f"[create] {product_dir.name} variant {variant_id:02d} model={args.model}", flush=True)
    create_response = with_retries(
        f"create task for {product_dir.name} variant {variant_id:02d}",
        args.create_retries,
        args.retry_backoff_seconds,
        lambda: lk888_post(api_key, "/v1/media/generate", payload, args.base_url),
    )
    task_ids = extract_task_ids(create_response)
    if not task_ids:
        raise RuntimeError(f"Missing task_id: {json.dumps(create_response, ensure_ascii=False)}")
    task_id = task_ids[0]
    task_record_path = output_dir / f"variant-{variant_id:02d}.task.json"
    write_json(task_record_path, {
        "variant_id": variant_id,
        "task_id": task_id,
        "status": "submitted",
        "model": args.model,
        "created_at": int(time.time()),
        "reference_mode": args.reference_mode,
        "params": {key: value for key, value in params.items() if key != "images"},
    })
    print(f"[submitted] variant={variant_id:02d} task_id={task_id}", flush=True)
    status_response = poll_task(api_key, task_id, args.base_url, args.poll_seconds, args.status_endpoint)
    result_url = status_response.get("result_url") or status_response.get("url")
    if not result_url:
        raise RuntimeError(f"Task completed without result_url: {json.dumps(status_response, ensure_ascii=False)}")
    downloaded = with_retries(
        f"download result for {product_dir.name} variant {variant_id:02d}",
        args.download_retries,
        args.retry_backoff_seconds,
        lambda: download_binary(result_url, output_path, timeout=300),
    )
    if not downloaded:
        raise RuntimeError(f"Download failed: {result_url}")
    write_json(task_record_path, {
        "variant_id": variant_id,
        "task_id": task_id,
        "status": "success",
        "model": args.model,
        "completed_at": int(time.time()),
        "result_url": result_url,
        "output_path": str(output_path.relative_to(product_dir)),
    })
    if v2_active:
        recorded_params = {key: value for key, value in params.items() if key != "images"}
        record_video(product_dir, output_path, expected, prompt,
                     {"task_id": task_id, "base_url": args.base_url, "params": recorded_params,
                      "reference_qc_override": bool(getattr(args, "allow_unverified_references", False))})
    return {
        "variant_id": variant_id,
        "task_id": task_id,
        "model": args.model,
        "reference_images": uploads,
        "prompt": prompt,
        "params": params,
        "create_response": create_response,
        "status_response": status_response,
        "content_response": {"url": result_url, "output_path": str(output_path.relative_to(product_dir))},
    }


def process_product(product_dir: Path, api_key: str, selected_variants: set[int], args: argparse.Namespace) -> None:
    prompts = load_json(resolve_prompts_path(product_dir, args.prompts_file))
    output_dir = existing_video_dir(product_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "video_generation_results.json"
    existing = load_json(results_path, {"results": []})
    results = list(existing.get("results", []))
    selected = []
    for variant in prompts.get("variants", []):
        variant_id = int(variant.get("variant_id", 0))
        if variant_id not in selected_variants:
            continue
        current_variant = dict(variant)
        current_variant["_physical_scale_lock"] = prompts.get("physical_scale_lock", "")
        current_variant["_silhouette_lock"] = prompts.get("silhouette_lock", "")
        selected.append(current_variant)

    def run_variant(current_variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return process_variant(product_dir, current_variant, api_key, args)
        except Exception as error:
            if not args.continue_on_error:
                raise
            return {
                "variant_id": current_variant["variant_id"],
                "status": "failed",
                "error": str(error),
                "output_path": str((output_dir / f"variant-{current_variant['variant_id']:02d}.mp4").relative_to(product_dir)),
            }

    workers = max(1, min(args.workers, len(selected) or 1))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(run_variant, variant): variant for variant in selected}
        for future in concurrent.futures.as_completed(future_map):
            current_variant = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                # One bad variant must not discard the whole batch
                result = {
                    "variant_id": current_variant["variant_id"],
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "output_path": str((output_dir / f"variant-{current_variant['variant_id']:02d}.mp4").relative_to(product_dir)),
                }
                print(f"[video] variant {current_variant['variant_id']:02d} failed: {exc}", flush=True)
            results = [item for item in results if int(item.get("variant_id", 0)) != current_variant["variant_id"]]
            results.append(result)
            results.sort(key=lambda item: int(item.get("variant_id", 0)))
            write_json(results_path, {"results": results})


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate product videos with LK888/updrama media API.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--products", default="")
    parser.add_argument("--variants", default="1-10")
    parser.add_argument("--prompts-file", default="ugc_prompts.json")
    parser.add_argument("--model", default="omni-flash", choices=["omni-flash", "omni_flash-10s", "minimax-h3"])
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--status-endpoint", default="/v1/skills/task-status")
    parser.add_argument("--aspect-ratio", default=DEFAULT_ASPECT_RATIO)
    parser.add_argument(
        "--duration",
        default=None,
        help="Video duration. Defaults to 10 seconds for every model.",
    )
    parser.add_argument("--audio-duration", default=None)
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--generate-audio", action="store_true")
    parser.add_argument("--output-subdir", default="")
    parser.add_argument("--enhance-prompt", default="false")
    parser.add_argument("--enable-upsample", default=None)
    parser.add_argument("--upload-host", default="litterbox", choices=["litterbox", "uguu"])
    parser.add_argument("--upload-lifetime", default="1h", choices=["1h"])
    parser.add_argument("--upload-retries", type=int, default=4)
    parser.add_argument("--create-retries", type=int, default=3)
    parser.add_argument("--download-retries", type=int, default=4)
    parser.add_argument("--retry-backoff-seconds", type=float, default=5.0)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--audio-style", default="safe", choices=["none", "safe", "mid", "legacy", "asmr"])
    parser.add_argument("--light-overlay", action="store_true")
    parser.add_argument("--safe-audio-test", action="store_true")
    parser.add_argument(
        "--reference-mode",
        default="omni-reference",
        choices=["omni-reference"],
        help="Fixed production mode: chronological storyboard + identity grid, with an optional QC-passed operation grid.",
    )
    parser.add_argument("--allow-landscape", action="store_true", help="Allow non-9:16 aspect ratios for explicit landscape-only jobs.")
    parser.add_argument("--continue-on-error", action="store_true", help="Record failed variants and continue processing the batch.")
    parser.add_argument("--workers", type=int, default=1, help="Submit and poll independent variants concurrently.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--effect-first", action="store_true",
                        help="For result-led rerolls, prioritize a matched before/after contrast and limit product close-ups.")
    parser.add_argument("--mexico-fantasy", action="store_true",
                        help="Use the ten Mexico-specific reality/fantasy before-after stories for variants 21-30.")
    parser.add_argument("--allow-unverified-references", action="store_true",
                        help="Submit even when storyboard QC has not passed. Only with explicit user sign-off; the override is recorded in each video's provenance.")
    parser.add_argument("--voice-locale", default="",
                        help="Deliberate override of the spoken locale, e.g. ja-JP or es-MX. Leave empty to resolve from the variant, the prompt batch, or the declared market; an unresolved locale is a hard error rather than English.")
    parser.add_argument("--market", default="",
                        help="Target market for the spoken language and local casting, e.g. Japan or JP. Used when neither the variant nor the prompt batch declares a locale.")
    args = parser.parse_args()
    if args.duration is None:
        args.duration = "10"
    if args.audio_duration is None:
        args.audio_duration = str(args.duration)
    if args.model in {"omni-flash", "omni_flash-10s"} and str(args.duration) not in {"4", "6", "8", "10"}:
        raise SystemExit("Omni duration must be one of 4, 6, 8, or 10 seconds")
    if args.model == "minimax-h3":
        if str(args.duration) not in {str(value) for value in range(4, 16)}:
            raise SystemExit("MiniMax H3 duration must be an integer from 4 to 15 seconds")
        if str(args.resolution).upper() not in {"768P", "1080P", "2K", "4K"}:
            raise SystemExit("MiniMax H3 resolution must be 768P, 1080P, 2K, or 4K")
        args.resolution = str(args.resolution).upper()
    if args.aspect_ratio != DEFAULT_ASPECT_RATIO and not args.allow_landscape:
        raise SystemExit(
            f"Refusing aspect_ratio={args.aspect_ratio}. Product UGC videos default to vertical {DEFAULT_ASPECT_RATIO}; "
            "pass --allow-landscape only when the user explicitly requests landscape."
        )
    api_key = require_lk888_api_key()
    selected_variants = parse_variants(args.variants)
    for product_dir in selected_product_dirs(args.output_dir, args.products):
        process_product(product_dir, api_key, selected_variants, args)


if __name__ == "__main__":
    main()

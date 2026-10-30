#!/usr/bin/env python3
"""Single source of truth for market -> voice-locale resolution.

Root cause this module removes: the prompt generator never wrote a locale,
the non-compact audio path defaulted to ``en-US``, and the compact Omni path
read only ``variant["voice_locale"]`` while ignoring the CLI flag. A Japan-market
batch could therefore ship English audio, or a self-contradictory
"speak Japanese / never answer in English" instruction, with no error anywhere.

Resolution is now explicit and has exactly one implementation. An unresolved or
misspelled locale is a hard failure, never a silent English default.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, NamedTuple


class VoiceLocaleError(RuntimeError):
    """Raised when a market/locale cannot be resolved or is inconsistent."""


# locale -> creator voice description + spoken language + writing system.
# `script` drives the voiceover language gate; only non-Latin scripts are
# checked for target-script characters because Latin-script languages share
# the ASCII range.
LOCALE_PROFILES: dict[str, dict[str, str]] = {
    "en-US": {"voice": "young American woman", "language": "English", "script": "latin", "region": "the United States"},
    "en-GB": {"voice": "young British woman", "language": "British English", "script": "latin", "region": "the United Kingdom"},
    "en-AU": {"voice": "young Australian woman", "language": "Australian English", "script": "latin", "region": "Australia"},
    "es-MX": {"voice": "young Mexican woman speaking natural Mexican Spanish, with the clear open vowels and rhythm of Mexico rather than Spain", "language": "Mexican Spanish as spoken in Mexico", "script": "latin", "region": "Mexico"},
    "es-ES": {"voice": "young Spanish woman speaking Castilian Spanish from Spain", "language": "Castilian Spanish from Spain", "script": "latin", "region": "Spain"},
    "es-419": {"voice": "young Latin American woman speaking neutral Latin American Spanish", "language": "neutral Latin American Spanish", "script": "latin", "region": "Latin America"},
    "pt-BR": {"voice": "young Brazilian woman speaking Brazilian Portuguese", "language": "Brazilian Portuguese", "script": "latin", "region": "Brazil"},
    "de-DE": {"voice": "young German woman speaking natural conversational German", "language": "German", "script": "latin", "region": "Germany"},
    "fr-FR": {"voice": "young French woman speaking natural conversational French", "language": "French", "script": "latin", "region": "France"},
    "it-IT": {"voice": "young Italian woman speaking natural conversational Italian", "language": "Italian", "script": "latin", "region": "Italy"},
    "ja-JP": {"voice": "young Japanese woman speaking natural conversational Japanese with a standard Tokyo accent", "language": "Japanese as spoken in Japan", "script": "japanese", "region": "Japan"},
    "ko-KR": {"voice": "young Korean woman speaking natural conversational Korean with a standard Seoul accent", "language": "Korean as spoken in South Korea", "script": "korean", "region": "South Korea"},
    "zh-CN": {"voice": "young Mandarin-speaking woman with a neutral Mainland accent", "language": "Mandarin Chinese", "script": "han", "region": "Mainland China"},
    "zh-TW": {"voice": "young Mandarin-speaking woman with a natural Taiwan accent", "language": "Mandarin Chinese as spoken in Taiwan", "script": "han", "region": "Taiwan"},
    "th-TH": {"voice": "young Thai woman speaking natural conversational Thai", "language": "Thai", "script": "thai", "region": "Thailand"},
    "vi-VN": {"voice": "young Vietnamese woman speaking natural conversational Vietnamese", "language": "Vietnamese", "script": "latin", "region": "Vietnam"},
    "id-ID": {"voice": "young Indonesian woman speaking natural conversational Indonesian", "language": "Indonesian", "script": "latin", "region": "Indonesia"},
    "ms-MY": {"voice": "young Malaysian woman speaking natural conversational Malay", "language": "Malay", "script": "latin", "region": "Malaysia"},
}


CREATOR_MARKET_IDENTITIES: dict[str, str] = {
    "en-US": "an adult American creator from the United States",
    "en-GB": "an adult British creator from the United Kingdom",
    "en-AU": "an adult Australian creator",
    "es-MX": "an adult Mexican creator",
    "es-ES": "an adult Spanish creator from Spain",
    "es-419": "an adult Latin American creator",
    "pt-BR": "an adult Brazilian creator",
    "de-DE": "an adult German creator",
    "fr-FR": "an adult French creator",
    "it-IT": "an adult Italian creator",
    "ja-JP": "an adult Japanese creator from Japan",
    "ko-KR": "an adult Korean creator from South Korea",
    "zh-CN": "an adult Mainland Chinese creator",
    "zh-TW": "an adult Taiwanese creator",
    "th-TH": "an adult Thai creator",
    "vi-VN": "an adult Vietnamese creator",
    "id-ID": "an adult Indonesian creator",
    "ms-MY": "an adult Malaysian creator",
}

_CREATOR_MARKERS: dict[str, tuple[str, ...]] = {
    "en-US": ("american", "united states", "美国人"),
    "en-GB": ("british", "united kingdom", "英国人"),
    "en-AU": ("australian", "澳大利亚人"),
    "es-MX": ("mexican", "mexicana", "mexicano", "墨西哥人"),
    "es-ES": ("spanish creator", "española", "español", "西班牙人"),
    "es-419": ("latin american", "latina", "latino", "拉丁美洲"),
    "pt-BR": ("brazilian", "brasileira", "brasileiro", "巴西人"),
    "de-DE": ("german creator", "deutsche", "德国人"),
    "fr-FR": ("french creator", "française", "français", "法国人"),
    "it-IT": ("italian creator", "italiana", "italiano", "意大利人"),
    "ja-JP": ("japanese", "日本人"),
    "ko-KR": ("korean", "韩国人", "韓国人"),
    "zh-CN": ("mainland chinese", "中国大陆", "中国人"),
    "zh-TW": ("taiwanese", "台湾人", "臺灣人"),
    "th-TH": ("thai creator", "泰国人"),
    "vi-VN": ("vietnamese", "越南人"),
    "id-ID": ("indonesian", "印度尼西亚人"),
    "ms-MY": ("malaysian", "马来西亚人"),
}


# Market/country spellings seen in product briefs, run manifests and market
# profiles, mapped to the canonical locale. English and local-language names are
# both accepted so a brief can declare `Japan` or `日本` and resolve the same way.
MARKET_LOCALES: dict[str, str] = {
    "us": "en-US", "usa": "en-US", "united states": "en-US", "america": "en-US", "アメリカ": "en-US",
    "uk": "en-GB", "gb": "en-GB", "united kingdom": "en-GB", "britain": "en-GB", "england": "en-GB",
    "au": "en-AU", "australia": "en-AU",
    "mx": "es-MX", "mexico": "es-MX", "méxico": "es-MX",
    "es": "es-ES", "spain": "es-ES", "españa": "es-ES",
    "latam": "es-419", "latin america": "es-419",
    "br": "pt-BR", "brazil": "pt-BR", "brasil": "pt-BR",
    "de": "de-DE", "germany": "de-DE", "deutschland": "de-DE",
    "fr": "fr-FR", "france": "fr-FR",
    "it": "it-IT", "italy": "it-IT", "italia": "it-IT",
    "jp": "ja-JP", "japan": "ja-JP", "日本": "ja-JP", "日本市場": "ja-JP",
    "kr": "ko-KR", "korea": "ko-KR", "south korea": "ko-KR", "韓国": "ko-KR",
    "cn": "zh-CN", "china": "zh-CN", "mainland china": "zh-CN", "中国": "zh-CN",
    "tw": "zh-TW", "taiwan": "zh-TW", "台湾": "zh-TW",
    "th": "th-TH", "thailand": "th-TH", "タイ": "th-TH",
    "vn": "vi-VN", "vietnam": "vi-VN",
    "id": "id-ID", "indonesia": "id-ID",
    "my": "ms-MY", "malaysia": "ms-MY",
}


# Code-point ranges that must appear at least once in a voiceover written in a
# non-Latin script. Used to reject an English script for a Japanese market.
SCRIPT_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "japanese": ((0x3040, 0x309F), (0x30A0, 0x30FF), (0x4E00, 0x9FFF), (0xFF66, 0xFF9F)),
    "korean": ((0xAC00, 0xD7AF), (0x1100, 0x11FF), (0x3130, 0x318F)),
    "han": ((0x4E00, 0x9FFF), (0x3400, 0x4DBF)),
    "thai": ((0x0E00, 0x0E7F),),
}


# Characters that end a spoken sentence in the languages this pipeline serves.
_SENTENCE_END = "。．！？!?."


class ResolvedVoiceLocale(NamedTuple):
    locale: str
    source: str
    market: str


def known_locales() -> list[str]:
    return sorted(LOCALE_PROFILES)


def normalize_locale(value: Any) -> str | None:
    """Return a canonical locale for a tag like ``ja-JP``/``ja_JP``/``ja``.

    Returns ``None`` when the value is empty or is not a locale this pipeline
    knows how to speak, so the caller can fall through or fail rather than
    silently using English.
    """
    text = str(value or "").strip()
    if not text:
        return None
    compact = text.replace("_", "-").lower()
    for locale in LOCALE_PROFILES:
        if compact == locale.lower():
            return locale
    # Bare language tag: `ja` resolves to the default region for that language.
    if "-" not in compact:
        matches = [locale for locale in LOCALE_PROFILES if locale.split("-")[0].lower() == compact]
        if len(matches) == 1:
            return matches[0]
        # Ambiguous language (en -> en-US, es -> es-419?) prefers the base region.
        preferred = {"en": "en-US", "es": "es-419", "zh": "zh-CN", "pt": "pt-BR", "ms": "ms-MY"}
        if compact in preferred and preferred[compact] in LOCALE_PROFILES:
            return preferred[compact]
    return None


def locale_from_market(value: Any) -> str | None:
    """Map a market/country spelling to a locale, or ``None``."""
    text = str(value or "").strip().lower()
    if not text:
        return None
    normalized = normalize_locale(text)
    if normalized:
        return normalized
    if text in MARKET_LOCALES:
        return MARKET_LOCALES[text]
    # `jp-japan`, `Japan (JP)`, `ja-JP market` and similar decorated values.
    for token in re.split(r"[^0-9a-z\u3040-\u30ff\u4e00-\u9fff+]+|\s+", text):
        if not token:
            continue
        if token in MARKET_LOCALES:
            return MARKET_LOCALES[token]
        if normalize_locale(token):
            return normalize_locale(token)
    return None


def profile(locale: str) -> dict[str, str]:
    """Return the voice profile for a canonical locale.

    Raises rather than falling back, because a typo that silently produced
    English audio is exactly the defect this module exists to prevent.
    """
    resolved = normalize_locale(locale)
    if not resolved:
        raise VoiceLocaleError(
            f"Unknown voice locale {locale!r}. Known locales: {', '.join(known_locales())}. "
            "Add the locale to scripts/voice_locale.py rather than letting it fall back to English."
        )
    return LOCALE_PROFILES[resolved]


def voice_description(locale: str) -> str:
    return profile(locale)["voice"]


def language_name(locale: str) -> str:
    return profile(locale)["language"]


def region_name(locale: str) -> str:
    return profile(locale).get("region", "the target market")


def creator_market_identity(locale: str) -> str:
    resolved = normalize_locale(locale)
    if not resolved or resolved not in CREATOR_MARKET_IDENTITIES:
        raise VoiceLocaleError(f"No creator-market identity is configured for locale {locale!r}")
    return CREATOR_MARKET_IDENTITIES[resolved]


def normalize_creator_persona(persona: Any, locale: str) -> str:
    """Pin casting to the locale and reject an explicitly foreign persona."""
    resolved = normalize_locale(locale)
    if not resolved:
        raise VoiceLocaleError(f"Unknown creator locale {locale!r}")
    raw = re.sub(r"\s+", " ", str(persona or "")).strip()
    lowered = raw.lower()
    for other_locale, markers in _CREATOR_MARKERS.items():
        if other_locale == resolved:
            continue
        if any(marker.lower() in lowered for marker in markers):
            raise VoiceLocaleError(
                f"Creator persona {raw!r} conflicts with target locale {resolved}; casting must stay in one market"
            )
    identity = creator_market_identity(resolved)
    if any(marker.lower() in lowered for marker in _CREATOR_MARKERS.get(resolved, ())):
        return raw
    return f"{identity}; {raw}" if raw else identity


def validate_spoken_text(text: Any, locale: str, label: str, allow_empty: bool = False) -> None:
    body = str(text or "").strip()
    if not body:
        if allow_empty:
            return
        raise VoiceLocaleError(f"{label} is empty for target locale {locale}")
    expected_script = script_of(locale)
    if expected_script != "latin" and not script_matches(body, locale):
        raise VoiceLocaleError(f"{label} is not written in {language_name(locale)}: {body[:120]!r}")
    if expected_script == "latin":
        # Latin languages cannot be reliably distinguished without a language
        # model, but a clearly non-Latin line is always a hard mismatch.
        for script, ranges in SCRIPT_RANGES.items():
            if any(any(start <= ord(char) <= end for start, end in ranges) for char in body):
                raise VoiceLocaleError(f"{label} uses the wrong writing system for {language_name(locale)}")


def script_of(locale: str) -> str:
    return profile(locale)["script"]


def script_matches(text: Any, locale: str) -> bool:
    """True when the text plausibly belongs to the locale's writing system."""
    body = str(text or "")
    if not body.strip():
        return False
    ranges = SCRIPT_RANGES.get(script_of(locale))
    if not ranges:
        return True
    return any(any(start <= ord(char) <= end for start, end in ranges) for char in body)


def language_clause(locale: str) -> str:
    """Build the spoken-language instruction for the video prompt.

    The previous wording hard-coded "never answer in English", which was wrong
    for an English target: for a US market it demanded English and forbade it in
    the same sentence, so the model guessed.
    """
    language = language_name(locale)
    base = f"Every spoken word must be in {language}."
    if script_of(locale) == "latin":
        return base + " Do not switch language mid-sentence."
    return base + f" Never answer in English. Write and speak the line only in {language}."


def _read_market_profile(raw: Any, product_dir: Path | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text or not text.lower().endswith(".json"):
        return {}
    candidate = Path(text)
    if not candidate.is_absolute() and product_dir is not None:
        candidate = (product_dir / candidate).resolve()
    try:
        loaded = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def declared_market(
    *,
    variant: dict[str, Any] | None = None,
    prompts: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    product_dir: Path | None = None,
) -> str:
    """Return the first market declaration found, as free text."""
    for source in (variant, prompts, brief, manifest):
        if not isinstance(source, dict):
            continue
        for key in ("market", "target_market", "country", "region", "market_name"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for source in (brief, manifest):
        if isinstance(source, dict):
            profile_data = _read_market_profile(source.get("market_profile"), product_dir)
            if profile_data:
                for key in ("country", "region", "market", "locale", "language"):
                    value = profile_data.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
    return ""


def resolve_voice_locale(
    *,
    variant: dict[str, Any] | None = None,
    prompts: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    explicit: Any = None,
    product_dir: Path | None = None,
) -> ResolvedVoiceLocale:
    """Resolve the spoken locale with documented precedence.

    Highest first:
      1. ``variant["voice_locale"]`` - per-video canonical value
      2. ``explicit`` - a deliberate operator override (CLI flag)
      3. ``prompts["voice_locale"]`` - batch-level canonical value
      4. the declared market from variant/prompts/brief/manifest
    Raises instead of returning an English default.
    """
    market = declared_market(variant=variant, prompts=prompts, brief=brief,
                             manifest=manifest, product_dir=product_dir)
    attempts: list[tuple[str, Any]] = []
    if isinstance(variant, dict):
        attempts.append(("variant.voice_locale", variant.get("voice_locale")))
    attempts.append(("cli", explicit))
    if isinstance(prompts, dict):
        attempts.append(("prompts.voice_locale", prompts.get("voice_locale")))
    attempts.append(("declared_market", market))

    seen_value = False
    market_locale = locale_from_market(market) if market else None
    for source, value in attempts:
        if value is None or not str(value).strip():
            continue
        seen_value = True
        locale = locale_from_market(value)
        if locale:
            if market_locale and locale != market_locale:
                raise VoiceLocaleError(
                    f"Locale {locale} from {source} conflicts with declared market {market!r} ({market_locale}). "
                    "Market, creator identity and every spoken line must use one locale end-to-end."
                )
            return ResolvedVoiceLocale(locale=locale, source=source, market=market)
        raise VoiceLocaleError(
            f"Unsupported voice locale/market {value!r} from {source}. "
            f"Known locales: {', '.join(known_locales())}."
        )
    hint = (
        "No market or voice locale was declared anywhere, so this run cannot decide which language to speak. "
        "Pass --voice-locale ja-JP (or --market Japan), or set voice_locale in the prompt batch."
        if not seen_value
        else "Every declared locale was empty; set voice_locale on the variant or the prompt batch."
    )
    raise VoiceLocaleError(
        "Refusing to silently generate English audio for an undeclared market. " + hint
    )


def max_voiceover_chars(locale: str) -> int:
    """Rough characters a creator can speak inside a 10-second clip."""
    return 58 if script_of(locale) != "latin" else 150


def trim_voiceover(text: str, locale: str, max_chars: int | None = None) -> str:
    """Shorten a spoken line without leaving a truncated fragment.

    The previous implementation sliced on whitespace, so a long line ended in a
    dangling clause and a Japanese line (which has no spaces) was measured as a
    single word. This keeps whole sentences and always ends on terminal
    punctuation.
    """
    budget = max_chars or max_voiceover_chars(locale)
    body = " ".join(str(text or "").split())
    if not body:
        return ""
    if len(body) <= budget:
        return body
    sentences: list[str] = []
    buffer = ""
    for char in body:
        buffer += char
        if char in _SENTENCE_END:
            sentences.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        sentences.append(buffer.strip())
    kept = ""
    for sentence in sentences:
        candidate = (kept + " " + sentence).strip() if kept else sentence
        if len(candidate) > budget and kept:
            break
        kept = candidate
        if len(kept) >= budget:
            break
    if not kept:
        # Even the opening sentence is over budget. Keep it whole: a slightly
        # long complete line reads better than a cut-off one.
        kept = sentences[0]
    if kept and kept[-1] not in _SENTENCE_END:
        kept += "。" if script_of(locale) == "japanese" else "."
    return kept

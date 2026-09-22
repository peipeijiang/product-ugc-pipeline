"""Regression tests for the market/spoken-language contract.

These cover the defect that shipped English audio for a Japan-market batch:
the prompt generator never wrote a locale, the full prompt path defaulted to
en-US, the compact Omni path ignored the CLI flag, and the generated video
prompt hard-coded a "young American female" voice.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generate_ugc_prompts import (
    derive_sku_colourway,
    normalize_voiceover_script_10s,
    usage_demo_video_prompt,
    validate_voiceover_language,
)
from generate_videos_lk888 import compact_omni_prompt
from voice_locale import (
    VoiceLocaleError,
    language_clause,
    locale_from_market,
    normalize_locale,
    resolve_voice_locale,
    script_matches,
    trim_voiceover,
    voice_description,
)


class VoiceLocaleTests(unittest.TestCase):
    def test_market_and_locale_spellings_normalize(self):
        for value in ("Japan", "JP", "jp", "日本", "ja-JP", "ja_JP", "ja"):
            with self.subTest(value=value):
                self.assertEqual(locale_from_market(value), "ja-JP")
        self.assertEqual(normalize_locale("es-MX"), "es-MX")
        self.assertEqual(locale_from_market("Brazil"), "pt-BR")
        self.assertIsNone(locale_from_market("Mars"))

    def test_unknown_locale_never_falls_back_to_english(self):
        with self.assertRaises(VoiceLocaleError):
            voice_description("klingon-KL")

    def test_undeclared_market_is_a_hard_error(self):
        with self.assertRaisesRegex(VoiceLocaleError, "Refusing to silently generate English"):
            resolve_voice_locale()

    def test_resolution_precedence(self):
        brief = {"target_market": "Japan"}
        self.assertEqual(
            resolve_voice_locale(brief=brief).locale, "ja-JP"
        )
        # A deliberate CLI override outranks the batch file.
        self.assertEqual(
            resolve_voice_locale(brief=brief, prompts={"voice_locale": "ja-JP"}, explicit="en-US").locale,
            "en-US",
        )
        # A per-variant locale outranks everything.
        self.assertEqual(
            resolve_voice_locale(
                variant={"voice_locale": "es-MX"}, brief=brief, explicit="en-US"
            ).locale,
            "es-MX",
        )

    def test_market_profile_file_feeds_resolution(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "analysis").mkdir()
            (folder / "analysis/market-profile.json").write_text(
                json.dumps({"country": "Japan", "locale": "ja-JP"}), encoding="utf-8"
            )
            resolution = resolve_voice_locale(
                brief={"market_profile": "analysis/market-profile.json"}, product_dir=folder
            )
        self.assertEqual(resolution.locale, "ja-JP")

    def test_english_locale_is_not_told_to_avoid_english(self):
        # The old wording demanded English and forbade it in one sentence.
        self.assertNotIn("never answer in english", language_clause("en-US").lower())
        self.assertIn("never answer in english", language_clause("ja-JP").lower())

    def test_compact_omni_prompt_honours_the_resolved_locale(self):
        variant = {
            "variant_id": 1,
            "title": "Test",
            "hook": "Hook",
            "voiceover_script_10s": [{"time": "0-3s", "line": "これで快適です。"}],
        }
        variant["storyboard_10s"] = [{"time": "0-10s", "visual": "Hold the ready-state product"}]
        prompt = compact_omni_prompt(variant, "10", "omni-reference", voice_locale="ja-JP")
        self.assertIn("Japanese", prompt)
        self.assertNotIn("young American woman", prompt)
        # This is the exact regression: the compact path used to ignore the
        # locale and emit the en-US profile.
        with self.assertRaises(VoiceLocaleError):
            compact_omni_prompt({"variant_id": 1, "storyboard_10s": variant["storyboard_10s"]}, "10", "omni-reference")

    def test_omni_prompt_omits_empty_sku_clause(self):
        variant = {"variant_id": 1, "voiceover_script_10s": [{"time": "0-3s", "line": "Works now."}]}
        variant["storyboard_10s"] = [{"time": "0-10s", "visual": "Hold the ready-state product"}]
        prompt = compact_omni_prompt(variant, "10", "omni-reference", voice_locale="en-US")
        self.assertNotIn("MANDATORY SKU FOR THIS VIDEO: .", prompt)
        with_sku = dict(variant, sku_colourway="black XL")
        self.assertIn(
            "MANDATORY SKU FOR THIS VIDEO: black XL",
            compact_omni_prompt(with_sku, "10", "omni-reference", voice_locale="en-US"),
        )

    def test_video_prompt_uses_the_market_voice_instead_of_american_english(self):
        variant = {
            "variant_id": 3,
            "title": "Tent",
            "hook": "Hook",
            "voiceover_script_10s": [{"time": "0-3s", "line": "設営は一瞬です。"}],
        }
        jp_prompt = usage_demo_video_prompt(variant, {}, "ja-JP")
        self.assertIn("Japanese", jp_prompt)
        self.assertNotIn("young American female", jp_prompt)
        self.assertNotIn("English words", jp_prompt)
        us_prompt = usage_demo_video_prompt(variant, {}, "en-US")
        self.assertIn("young American woman", us_prompt)

    def test_voiceover_in_the_wrong_script_is_rejected(self):
        english_for_japan = {
            "variant_id": 4,
            "voiceover_script_10s": [{"time": "0-3s", "line": "Set up in seconds."}],
        }
        with self.assertRaisesRegex(VoiceLocaleError, "not written in"):
            validate_voiceover_language(english_for_japan, "ja-JP", "tent")
        validate_voiceover_language(
            {"variant_id": 4, "voiceover_script_10s": [{"time": "0-3s", "line": "一瞬で設営できます。"}]},
            "ja-JP",
            "tent",
        )
        # Latin-script locales have no script gate.
        validate_voiceover_language(english_for_japan, "en-US", "tent")

    def test_japanese_lines_are_not_measured_as_one_word(self):
        long_japanese = "これはとても長い説明文です。二つ目の文はここで落とされます。三つ目の文も同様です。"
        lines = normalize_voiceover_script_10s([long_japanese], locale="ja-JP")
        spoken = " ".join(item["line"] for item in lines if item["line"])
        self.assertTrue(script_matches(spoken, "ja-JP"))
        for item in lines:
            if item["line"]:
                self.assertTrue(item["line"][-1] in "。！？", item["line"])

    def test_truncation_never_leaves_a_fragment(self):
        text = "Set up camp in seconds. And then a second thought that does not fit at all."
        trimmed = trim_voiceover(text, "en-US", max_chars=30)
        self.assertEqual(trimmed, "Set up camp in seconds.")
        self.assertTrue(trimmed.endswith("."))
        # A single over-long sentence is kept whole rather than cut mid-clause.
        single = "This one clause is far too long but must survive intact."
        self.assertEqual(trim_voiceover(single, "en-US", max_chars=10), single)

    def test_voiceover_trimming_for_latin_uses_whole_clauses(self):
        raw = ["Buy the tent today, and also consider, maybe, a second accessory."]
        lines = normalize_voiceover_script_10s(raw, locale="en-US")
        line = lines[0]["line"]
        self.assertTrue(line.endswith((".", "!", "?")))
        self.assertFalse(line.endswith(","))

    def test_sku_colourway_is_derived_only_when_unambiguous(self):
        self.assertEqual(
            derive_sku_colourway({"skus": [{"sku_name": "Olive"}]}, {}), "Olive"
        )
        self.assertEqual(
            derive_sku_colourway({"skus": [{"sku_name": "Olive"}, {"sku_name": "Black"}]}, {}), ""
        )
        self.assertEqual(derive_sku_colourway({}, {"confirmed_identity": {"colour": "sand"}}), "sand")


if __name__ == "__main__":
    unittest.main()

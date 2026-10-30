import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from storyboard_contract import storyboard_spec, storyboard_video_beats
from generate_images import build_storyboard_prompt
from generate_ugc_prompts import storyboard_entries, format_storyboard_for_prompt

class StoryboardTests(unittest.TestCase):
    def variant(self, n=6, ratio="9:16"):
        return {"target_frame_aspect_ratio": ratio, "storyboard_10s": [
            {"time": f"{10*i/n:.2f}-{10*(i+1)/n:.2f}s", "visual": f"Camera and action {i}"}
            for i in range(n)]}

    def test_geometry(self):
        for n, frame, board, size, cell in [
            (6, "9:16", "27:32", "1620x1920", "540x960"),
            (9, "9:16", "9:16", "1080x1920", "360x640"),
        ]:
            spec = storyboard_spec(self.variant(n, frame))
            self.assertEqual(spec["boardLayoutRatio"], board)
            self.assertEqual(spec["size"], size)
            self.assertEqual(spec["panelPixelSize"], cell)
        with self.assertRaisesRegex(RuntimeError, "must be 9:16"):
            storyboard_spec(self.variant(6, "16:9"))

    def test_shared_visuals_and_nine_panels(self):
        v = self.variant(9)
        v["shot_plan"] = [{"shot":"contradictory legacy scene"}]
        self.assertEqual(storyboard_entries(v), v["storyboard_10s"])
        image = build_storyboard_prompt(v,"Product")
        video = format_storyboard_for_prompt(v)
        for panel in v["storyboard_10s"]:
            self.assertIn(panel["visual"],image)
            self.assertIn(panel["visual"],video)
        self.assertNotIn("contradictory legacy scene",video)
        self.assertNotIn("entire image",image)

    def test_invalid_timeline(self):
        for n in (2,5,7,8,10):
            with self.assertRaises(RuntimeError):
                storyboard_spec(self.variant(n))
        v=self.variant()
        v["storyboard_10s"][1]["time"]="0-3s"
        with self.assertRaises(RuntimeError): storyboard_spec(v)

    def test_declared_panel_count_must_match(self):
        v = self.variant(9)
        v["storyboard_panel_count"] = 6
        with self.assertRaisesRegex(RuntimeError, "must match"):
            storyboard_spec(v)
        v["storyboard_panel_count"] = 9
        v["storyboard_density_reason"] = "Dense proof chain needs nine distinct visible events."
        self.assertEqual(storyboard_spec(v)["panel_count"], 9)

    def test_persisted_grid_spec_must_match_timeline(self):
        v = self.variant(6)
        v["storyboard_panel_count"] = 6
        v["grid_spec"] = storyboard_spec(v)
        self.assertEqual(storyboard_spec(v)["rows"], 2)
        v["grid_spec"] = dict(v["grid_spec"], rows=3)
        with self.assertRaisesRegex(RuntimeError, "Persisted grid_spec"):
            storyboard_spec(v)

    def test_layout_wrappers_are_removed_from_video_beats(self):
        v = self.variant(6)
        for index, panel in enumerate(v["storyboard_10s"], start=1):
            panel["visual"] = (
                f"STRICT LITERAL 3x2 GRID: six equal portrait panels, white gutters. "
                f"POSTPLUS CONTACT SHEET FRAME {index}/6. "
                f"Equal 9:16 portrait frame in a six-frame 3x2 storyboard sheet. "
                f"Creator performs visible action {index}."
            )
        beats = storyboard_video_beats(v)
        self.assertEqual(len(beats), 6)
        self.assertTrue(all("visible action" in beat["visual"] for beat in beats))
        joined = " ".join(beat["visual"] for beat in beats).lower()
        for leaked in ("strict literal", "contact sheet", "storyboard sheet", "white gutters", "3x2 grid"):
            self.assertNotIn(leaked, joined)

        from generate_videos_lk888 import compact_omni_prompt
        v["voiceover_script_10s"] = [{"time": "0-10s", "line": "便利です。"}]
        prompt = compact_omni_prompt(v, "10", voice_locale="ja-JP")
        self.assertIn("one full-screen scene at every moment", prompt)
        self.assertNotIn("POSTPLUS CONTACT SHEET FRAME", prompt)
        self.assertNotIn("STRICT LITERAL 3x2 GRID", prompt)

    def test_image_prompt_owns_grid_and_uses_target_market(self):
        v = self.variant(9)
        v.update({"market": "Japan", "voice_locale": "ja-JP", "creator_persona": "Japanese home-goods creator"})
        prompt = build_storyboard_prompt(v, "Product")
        self.assertIn("3 columns by 3 rows", prompt)
        self.assertIn("exactly 9 edge-to-edge panels", prompt)
        self.assertIn("1080x1920", prompt)
        self.assertIn("360x640 pixels at 9:16", prompt)
        self.assertIn("very narrow neutral gutters", prompt)
        self.assertIn("Japanese home-goods creator", prompt)
        self.assertNotIn("Mexican", prompt)

    def test_risk_route_preserves_dense_nine_panel_story(self):
        from creative_risk_router import apply_feasibility_route
        original = self.variant(9)
        visuals = [b["visual"] for b in original["storyboard_10s"]]
        routed = apply_feasibility_route(original, {
            "protect_product_configuration": True,
            "ranked_safe_directions": [{"direction": "stable supported use", "risk_score": 0}],
        })
        self.assertEqual(storyboard_spec(routed)["panel_count"], 9)
        self.assertEqual([b["visual"] for b in routed["storyboard_10s"]], visuals)
        self.assertEqual([b["visual"] for b in routed["storyboard_10s"]], [b["shot"] for b in routed["shot_plan"]])

    def test_prompt_cap_never_truncates_visuals(self):
        from generate_videos_lk888 import compact_omni_prompt, enforce_prompt_char_limit
        v = self.variant(9)
        v["voiceover_script_10s"] = [{"time": "0-10s", "line": "Works well."}]
        prompt = compact_omni_prompt(v, "10", voice_locale="en-US")
        for b in v["storyboard_10s"]:
            self.assertIn(b["visual"], prompt)
        v["storyboard_10s"][-1]["visual"] = "important visual " * 400
        with self.assertRaises(RuntimeError): compact_omni_prompt(v, "10", voice_locale="en-US")
        with self.assertRaises(RuntimeError): enforce_prompt_char_limit("123456", 5)

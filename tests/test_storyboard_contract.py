import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from storyboard_contract import storyboard_spec
from generate_images import build_storyboard_prompt
from generate_ugc_prompts import storyboard_entries, format_storyboard_for_prompt

class StoryboardTests(unittest.TestCase):
    def variant(self, n=6, ratio="9:16"):
        return {"target_frame_aspect_ratio": ratio, "storyboard_10s": [
            {"time": f"{10*i/n:.2f}-{10*(i+1)/n:.2f}s", "visual": f"Camera and action {i}"}
            for i in range(n)]}

    def test_geometry(self):
        for n, frame, board in [(6,"9:16","27:32"),(9,"9:16","9:16"),(6,"16:9","8:3"),(6,"1:1","3:2")]:
            spec = storyboard_spec(self.variant(n, frame))
            self.assertEqual(spec["boardLayoutRatio"], board)
            w,h = map(int,spec["size"].split("x"))
            a,b = map(int,frame.split(":"))
            self.assertEqual(w * spec["rows"] * b, h * spec["columns"] * a)

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

    def test_risk_route_outputs_valid_six_panels(self):
        from creative_risk_router import apply_feasibility_route
        routed = apply_feasibility_route(self.variant(9), {
            "protect_product_configuration": True,
            "ranked_safe_directions": [{"direction": "stable supported use", "risk_score": 0}],
        })
        self.assertEqual(storyboard_spec(routed)["panel_count"], 6)
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

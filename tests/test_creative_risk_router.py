"""Offline tests for conservative video-direction routing."""
import argparse
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from creative_risk_router import (
    apply_feasibility_route,
    build_video_feasibility_plan,
    normalize_model_profile,
    rank_video_directions,
)
from generate_ugc_prompts import (
    normalize_shot_plan_10s,
    normalize_voiceover_script_10s,
    usage_demo_video_prompt,
    usage_keyframe_prompt,
)
from generate_videos_lk888 import build_model_params, compact_omni_prompt


class CreativeRiskRouterTests(unittest.TestCase):
    def test_ten_second_timeline_is_the_generation_contract(self):
        voiceover = normalize_voiceover_script_10s(["Problem", "Product proof", "Buyer result"])
        self.assertEqual([item["time"] for item in voiceover], ["0-3s", "3-7s", "7-10s"])
        shots = normalize_shot_plan_10s(
            ["Need", "Ready product", "Use", "Proof", "Result"],
            {"hook": "Need", "selling_angle": "Result"},
        )
        self.assertEqual(shots[-1]["time"], "8.5-10.0s")

        params = build_model_params(
            argparse.Namespace(
                model="veo3.1",
                duration="10",
                generation_mode="fast",
                aspect_ratio="9:16",
                enhance_prompt="false",
                enable_upsample=None,
            ),
            ["https://example.invalid/start.png", "https://example.invalid/end.png"],
        )
        self.assertEqual(params["duration"], "10")

    def high_risk_brief(self):
        return {
            "product_name": "portable folding chair",
            "confirmed_selling_points": [
                "Fast installation with an insert-and-lock frame",
                "Stable support and comfortable seated rest",
            ],
            "step_by_step_usage": [
                {"action": "unfold the frame", "evidence": "source sequence"},
                {"action": "insert the support pin and lock the buckle", "evidence": "manual"},
            ],
            "state_change_contract": {
                "required": True,
                "states": [
                    {"state_id": "folded", "visible_configuration": "frame folded"},
                    {"state_id": "open", "visible_configuration": "chair ready for sitting"},
                ],
                "transitions": [{
                    "transition_id": "deploy",
                    "evidence_level": "state_pair_only",
                    "render_policy": "hard_cut_only",
                }],
            },
        }

    def variant(self):
        return {
            "variant_id": 1,
            "title": "Ready to rest",
            "hook": "A long day outdoors",
            "selling_angle": "comfortable support",
            "buyer_result": "The creator relaxes comfortably.",
            "shot_plan": [
                {"time": "0-3s", "visual": "Unfold the chair."},
                {"time": "3-7s", "visual": "Insert the pin."},
                {"time": "7-10s", "visual": "Sit down."},
            ],
            "voiceover_script_10s": [
                {"time": "0-3s", "line": "Long day?"},
                {"time": "3-7s", "line": "This chair gives stable support"},
                {"time": "7-10s", "line": "wherever I stop."},
            ],
            "selected_reference_images": ["images/chair.png"],
        }

    def test_aliases_are_normalized(self):
        self.assertEqual(normalize_model_profile("sd2.0"), "seedance-2.0")
        self.assertEqual(normalize_model_profile("H3"), "minimax-h3")
        self.assertEqual(normalize_model_profile("omni_flash"), "omni-flash")

    def test_lowest_risk_commercial_direction_wins(self):
        ranked = rank_video_directions(self.high_risk_brief())
        self.assertEqual(ranked[0]["direction"], "Stable support and comfortable seated rest")
        self.assertEqual(ranked[0]["risk_score"], 0)
        self.assertGreater(ranked[1]["risk_score"], ranked[0]["risk_score"])

    def test_all_fragile_candidates_get_a_ready_state_fallback(self):
        ranked = rank_video_directions({
            "product_name": "modular shelf",
            "confirmed_selling_points": ["Quick setup: insert and connect every shelf panel"],
        })
        self.assertEqual(ranked[0]["risk_score"], 0)
        self.assertIn("ready-to-use state", ranked[0]["direction"])

    def test_state_pair_routes_to_ready_state_without_generated_setup(self):
        brief = self.high_risk_brief()
        plan = build_video_feasibility_plan(brief, "sd2.0")
        self.assertEqual(plan["target_model"], "seedance-2.0")
        self.assertEqual(plan["risk_level"], "critical")
        self.assertTrue(plan["protect_product_configuration"])
        self.assertFalse(plan["continuous_product_state_change_allowed"])

        routed = apply_feasibility_route(self.variant(), plan)
        self.assertTrue(routed["protect_product_configuration"])
        self.assertFalse(routed["continuous_product_state_change_allowed"])
        rendered_storyboard = str(routed["storyboard_10s"]).lower()
        self.assertNotIn("unfold", rendered_storyboard)
        self.assertNotIn("insert", rendered_storyboard)
        self.assertIn("ready-state", rendered_storyboard)
        self.assertIn("stable support", routed["safe_demo_direction"]["direction"].lower())

        brief["video_feasibility_plan"] = plan
        video_prompt = usage_demo_video_prompt(routed, brief)
        keyframe_prompt = usage_keyframe_prompt("portable folding chair", routed, brief, "end")
        self.assertIn("Do not generate setup", video_prompt)
        self.assertIn("topology, connections, part count and geometry must remain unchanged", video_prompt)
        self.assertIn("same verified ready-to-use configuration", keyframe_prompt)
        self.assertIn("do not generate, morph, interpolate or hard-cut the transition", keyframe_prompt)

        omni_prompt = compact_omni_prompt(routed, "10", "omni-reference")
        self.assertIn("regenerated low-risk chronological storyboard", omni_prompt)
        self.assertIn("LOW-RISK ROUTE", omni_prompt)
        self.assertIn("topology, connections, geometry and part count never change", omni_prompt)

    def test_simple_ready_state_demo_remains_continuous(self):
        brief = {
            "product_name": "desk organizer",
            "confirmed_selling_points": ["Keeps the desk clean and organized"],
            "step_by_step_usage": [{"action": "place it on the desk", "evidence": "source image"}],
        }
        plan = build_video_feasibility_plan(brief, "omni-flash")
        self.assertEqual(plan["risk_level"], "low")
        self.assertFalse(plan["protect_product_configuration"])
        self.assertTrue(plan["continuous_product_state_change_allowed"])


if __name__ == "__main__":
    unittest.main()

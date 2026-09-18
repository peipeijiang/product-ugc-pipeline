"""Offline tests for conservative video-direction routing."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from creative_risk_router import (
    apply_feasibility_route,
    build_video_feasibility_plan,
    format_feasibility_notice,
    format_production_notice,
    normalize_model_profile,
    rank_video_directions,
)
from generate_ugc_prompts import (
    normalize_shot_plan_10s,
    normalize_voiceover_script_10s,
    usage_demo_video_prompt,
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
            type("Args", (), {
                "model": "omni-flash",
                "duration": "10",
                "aspect_ratio": "9:16",
                "resolution": "1080p",
                "enhance_prompt": "false",
                "enable_upsample": None,
            })(),
            ["https://example.invalid/storyboard.png", "https://example.invalid/identity.png"],
        )
        self.assertEqual(params["duration"], "10")
        self.assertEqual(params["images"][0], "https://example.invalid/storyboard.png")

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
        self.assertEqual(normalize_model_profile("omni_flash"), "omni-flash")
        self.assertEqual(normalize_model_profile("omni-flash-10s"), "omni_flash-10s")

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
        plan = build_video_feasibility_plan(brief, "omni-flash")
        self.assertEqual(plan["target_model"], "omni-flash")
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
        video_prompt = usage_demo_video_prompt(routed, brief, "en-US")
        self.assertIn("Do not generate setup", video_prompt)
        self.assertIn("topology, connections, part count and geometry must remain unchanged", video_prompt)

        omni_prompt = compact_omni_prompt(routed, "10", "omni-reference", voice_locale="en-US")
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

    def test_factorized_traits_feed_the_risk_router(self):
        plan = build_video_feasibility_plan({
            "product_name": "inflatable sleeping mat",
            "confirmed_selling_points": ["Comfortable sleep support"],
            "production_classification": {
                "visual_family": "sports-outdoor",
                "physical_traits": ["inflatable", "multi-part"],
                "interaction_modes": ["inflate-deflate"],
            },
        }, "omni-flash")
        self.assertIn(plan["risk_level"], {"high", "critical"})
        self.assertTrue(plan["protect_product_configuration"])
        self.assertIn("configuration_change", [item["type"] for item in plan["hazards"]])

    def test_risk_notice_explains_the_planned_video_before_generation(self):
        plan = build_video_feasibility_plan(self.high_risk_brief(), "omni-flash")
        notice = "\n".join(format_feasibility_notice("folding-chair", plan))
        self.assertIn("风险=critical", notice)
        self.assertIn("固定商品结构=是", notice)
        self.assertIn("准备这样制作", notice)
        self.assertIn("安装、折叠或连接过程只使用真实素材", notice)
        self.assertIn("Stable support and comfortable seated rest", notice)

    def test_submission_notice_reports_actual_references_and_omitted_actions(self):
        plan = build_video_feasibility_plan(self.high_risk_brief(), "omni-flash")
        routed = apply_feasibility_route(self.variant(), plan)
        notice = "\n".join(format_production_notice(
            "folding-chair",
            1,
            routed,
            "omni-flash",
            "omni-reference",
            [Path("storyboard.png"), Path("identity-grid.png")],
        ))
        self.assertIn("即将制作", notice)
        self.assertIn("参考模式=omni-reference", notice)
        self.assertIn("storyboard.png, identity-grid.png", notice)
        self.assertIn("不让视频模型生成", notice)


if __name__ == "__main__":
    unittest.main()

"""Offline regression tests, NOT product/video quality benchmark results."""
import argparse
import base64
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from PIL import Image
from common import load_json, write_json, selected_product_dirs
from build_product_brief import assert_full_image_coverage
from generate_product_identity_lock import generate, parser
from generate_usage_pose_sheet import generate as usage
from generate_images import generate_image_file, generate_one_image, keyframe_references
from generate_videos_lk888 import omni_storyboard_identity_paths
from classify_product_category import classify_by_keywords, classify_product
from qc_dual_consistency import CHECKS, verdict, review, targets
from v2_contract import (SPECS, action_ledger, check_existing_video, digest, hashes,
                         context, load_identity, record_video, require_qc, validate_scene_chain,
                         validate_video_chain, video_contract, needs_state_change_contract,
                         scene_references, state_change_contract, state_change_panel_plan)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        image = Image.new("RGB", (64, 64), "red")
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        self.encoded = base64.b64encode(stream.getvalue()).decode()
        self.response = {"data": [{"b64_json": self.encoded}]}

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, category):
        folder = self.root / f"01-{category}"
        (folder / "images").mkdir(parents=True)
        Image.new("RGB", (64, 64), "red").save(folder / "images/source.png")
        write_json(folder / "product_manifest.json", {"product_name": category,
            "extraction_audit": {"complete": True},
            "images": [{"local_path": "images/source.png"}]})
        write_json(folder / "category.json", {"category": category})
        write_json(folder / "image_analysis.json", {"images": [{"local_path": "images/source.png", "analysis": {
            "full_product_visibility": "full_product", "reference_role": "canonical_full_product"}}]})
        write_json(folder / "product_brief.json", {"confirmed_identity": {"color": "red"},
            "canonical_reference_images": ["images/source.png"], "confirmed_use_cases": ["display"],
            "step_by_step_usage": [{"action": "Place on supported surface", "evidence": "source image"}],
            "misuse_risks_to_avoid": ["no invented mechanism"]})
        return folder

    def args(self, folder):
        args = parser().parse_args([str(folder)])
        args.separate_sheet = False
        args.keyframes = True
        args.allow_compose_keyframes = False
        # These tests patch the OpenAI-compatible Images route, so pin that
        # provider instead of the production upDrama media-task default.
        args.image_provider = "laozhang-image2"
        args.image_fallback = "none"
        return args

    def approve(self, folder, stage, paths):
        # Synthetic QC records are only test setup; production uses the vision endpoint.
        write_json(folder / "qc" / f"{stage}.json", {"identity_sha256": load_identity(folder)["sha256"],
            "results": [{"path": str(p.relative_to(folder)), "sha256": digest(p), "status": "pass"} for p in paths]})

    def setup_identity(self, category="electronics"):
        folder = self.fixture(category)
        args = self.args(folder)
        with patch("generate_images.multipart_request", return_value=self.response):
            generate(folder, "test", args)
        usage(folder, "", args)
        self.approve(folder, "identity", [folder / "identity_lock/reference_sheet.png"])
        return folder, args

    def transform_contract(self, render_policy="hard_cut_only", evidence_level="state_pair_only"):
        transition = {
            "transition_id": "deploy", "from_state": "folded", "to_state": "open",
            "evidence_level": evidence_level, "render_policy": render_policy,
            "evidence": "images/source.png shows both documented endpoint states",
            "forbidden_intermediates": ["crossed tubes", "duplicated frame"],
        }
        if evidence_level != "state_pair_only":
            transition.update({"actor_action": "pull frame open", "contact_points": ["side rails"],
                               "moving_parts": ["cross braces"], "fixed_parts": ["seat"],
                               "completion_cue": "all feet contact the floor"})
        return {
            "required": True, "mechanism_type": "folding",
            "part_invariants": [{"part": "frame", "count": 1, "evidence": "images/source.png"}],
            "connections": [{"parts": ["rail", "brace"], "type": "pivot", "evidence": "images/source.png"}],
            "states": [
                {"state_id": "folded", "visible_configuration": "rails packed together", "evidence": "images/source.png"},
                {"state_id": "open", "visible_configuration": "frame open on four feet", "evidence": "images/source.png"},
            ],
            "transitions": [transition],
        }

    def test_five_categories_single_grid_reuse_and_scene_chain(self):
        for category, (_, _, panels) in SPECS.items():
            with self.subTest(category=category):
                folder, args = self.setup_identity(category)
                identity = load_identity(folder)
                self.assertEqual(len(identity["panels"]), len(panels))
                self.assertEqual(len(list((folder / "identity_lock").glob("*.png"))), 1)
                self.assertEqual(load_json(folder / "usage_poses/manifest.json")["additional_image_count"], 0)
                with patch("generate_images.multipart_request", return_value=self.response) as api:
                    generate_one_image("test", folder, {"variant_id": 1}, args)
                self.assertEqual(api.call_count, 2)
                start_call, end_call = api.call_args_list
                self.assertEqual(len(start_call.kwargs["files"]), 2)
                self.assertEqual(len(end_call.kwargs["files"]), 3)
                self.assertTrue(end_call.kwargs["files"][0][1].name.endswith("-start.png"))
                self.assertIn("ONE undivided", end_call.kwargs["fields"]["prompt"])
                self.assertNotIn("weight", end_call.kwargs["fields"])
                frames = [folder / "generated_images" / f"variant-01-{r}.png" for r in ("start", "end")]
                validate_scene_chain(folder, frames)
                with self.assertRaises(RuntimeError):
                    require_qc(folder, frames, "keyframes")
                self.approve(folder, "keyframes", frames)
                require_qc(folder, frames, "keyframes")

    def test_unverified_action_rejected(self):
        for step in ("press button", {"action": "press"}, {"action": "press", "evidence": "inference"}):
            with self.assertRaises(RuntimeError):
                action_ledger({"step_by_step_usage": [step]})

    def test_state_change_contract_requires_evidence_and_never_invents_midpoint(self):
        brief = {"product_name": "folding chair", "step_by_step_usage": [
            {"action": "Unfold chair", "evidence": "images/source.png"}
        ]}
        self.assertTrue(needs_state_change_contract(brief))
        with self.assertRaisesRegex(RuntimeError, "no state_change_contract"):
            state_change_contract(brief)

        brief["state_change_contract"] = self.transform_contract()
        contract = state_change_contract(brief)
        self.assertEqual([item["kind"] for item in state_change_panel_plan(contract)], ["state", "state"])

        brief["state_change_contract"] = self.transform_contract(render_policy="continuous_allowed")
        with self.assertRaisesRegex(RuntimeError, "cannot allow continuous"):
            state_change_contract(brief)

    def test_direct_motion_contract_may_add_evidenced_transition_panel(self):
        contract = state_change_contract({"state_change_contract": self.transform_contract(
            render_policy="continuous_allowed", evidence_level="direct_motion"
        )})
        self.assertEqual(
            [item["kind"] for item in state_change_panel_plan(contract)],
            ["state", "evidenced_transition", "state"],
        )

    def test_state_change_product_auto_generates_operation_sheet(self):
        folder = self.fixture("furniture")
        brief = load_json(folder / "product_brief.json")
        brief["product_name"] = "folding chair"
        brief["step_by_step_usage"] = [{"action": "Unfold chair", "evidence": "images/source.png"}]
        brief["state_change_contract"] = self.transform_contract()
        write_json(folder / "product_brief.json", brief)
        args = self.args(folder)
        with patch("generate_images.multipart_request", return_value=self.response):
            generate(folder, "test", args)
        self.approve(folder, "identity", [folder / "identity_lock/reference_sheet.png"])
        with patch("generate_images.multipart_request", return_value=self.response) as api:
            result = usage(folder, "test", args)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(result["mode"], "state_change_sheet")
        operation_sheet = folder / result["output_path"]
        self.approve(folder, "usage", [operation_sheet])
        self.assertEqual(len(scene_references(folder, "start", 1)), 3)

        with patch("generate_images.multipart_request", return_value=self.response):
            generate_one_image("test", folder, {"variant_id": 1}, args)
        frames = [folder / "generated_images" / f"variant-01-{role}.png" for role in ("start", "end")]
        validate_scene_chain(folder, frames)
        end_refs = scene_references(folder, "end", 1)
        self.assertEqual(len(end_refs), 3)
        self.assertTrue(end_refs[0].name.endswith("-start.png"))
        self.assertEqual(end_refs[-1], operation_sheet)

        storyboard = folder / "runs/test/storyboard/variant-01-storyboard.png"
        storyboard.parent.mkdir(parents=True)
        Image.new("RGB", (64, 64), "blue").save(storyboard)
        write_json(storyboard.with_suffix(".provenance.json"), {"type": "image2_chronological_storyboard"})
        omni_refs = omni_storyboard_identity_paths(folder, {
            "reference_images": [str(storyboard.relative_to(folder))]
        })
        self.assertEqual(omni_refs, [storyboard, folder / "identity_lock/reference_sheet.png", operation_sheet])

    def test_source_change_invalidates_identity(self):
        folder, _ = self.setup_identity()
        write_json(folder / "product_brief.json", {"changed": True})
        with self.assertRaises(RuntimeError):
            load_identity(folder)

    def test_failed_image_has_no_complete_manifest(self):
        folder = self.fixture("jewelry")
        with patch("generate_images.multipart_request", return_value={}):
            with self.assertRaises(RuntimeError):
                generate(folder, "test", self.args(folder))
        with self.assertRaises(RuntimeError):
            load_identity(folder)

    def test_media_task_image_route_saves_frame_and_records_provider(self):
        folder = self.fixture("electronics")
        args = self.args(folder)
        args.image_provider = "tt-image-2.5"
        args.image_fallback = "none"
        args.size = "1024x1536"
        reference = folder / "images/source.png"
        destination = folder / "generated_images/variant-01.png"

        def fake_download(url, path, timeout=60):
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (64, 64), "blue").save(path)
            return True

        responses = [
            {"data": {"task_id": 4242}},
            {"is_final": True, "state": "success", "result_url": "https://example.invalid/frame.png"},
        ]
        with patch("generate_images.require_api_key_for_base_url", return_value="test-key"), \
             patch("generate_images.request_json", side_effect=responses) as calls, \
             patch("generate_images.download_binary", side_effect=fake_download):
            result = generate_image_file(
                "test-key", folder, {"variant_id": 1}, args, destination, "prompt",
                reference_override=[reference],
            )

        self.assertEqual(result["image_provider"], "tt-image-2.5")
        self.assertEqual(result["status"], "saved")
        self.assertTrue(destination.exists())
        payload = calls.call_args_list[0].args[2]
        self.assertEqual(payload["model"], "tt-image-2.5")
        # The default aspect ratio derives from --size so the sheet keeps its 2:3 canvas.
        self.assertEqual(payload["params"]["aspect_ratio"], "2:3")
        self.assertEqual(payload["params"]["resolution"], "2K")
        self.assertTrue(payload["params"]["images"][0].startswith("data:image/"))

    def test_explicit_image_aspect_ratio_overrides_size(self):
        folder = self.fixture("electronics")
        args = self.args(folder)
        args.image_provider = "tt-image-2.5"
        args.image_fallback = "none"
        args.size = "1024x1536"
        args.image_aspect_ratio = "9:16"
        reference = folder / "images/source.png"
        destination = folder / "generated_images/variant-01.png"

        def fake_download(url, path, timeout=60):
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (64, 64), "blue").save(path)
            return True

        responses = [
            {"data": {"task_id": 4243}},
            {"is_final": True, "state": "success", "result_url": "https://example.invalid/frame.png"},
        ]
        with patch("generate_images.require_api_key_for_base_url", return_value="test-key"), \
             patch("generate_images.request_json", side_effect=responses) as calls, \
             patch("generate_images.download_binary", side_effect=fake_download):
            generate_image_file(
                "test-key", folder, {"variant_id": 1}, args, destination, "prompt",
                reference_override=[reference],
            )

        self.assertEqual(calls.call_args_list[0].args[2]["params"]["aspect_ratio"], "9:16")

    def test_qc_rejects_unknown_and_malformed(self):
        checks = {name: {"status": "pass", "evidence": "test evidence"} for name in CHECKS}
        self.assertEqual(verdict({"checks": checks}), "pass")
        checks["scale"]["status"] = "unknown"
        self.assertEqual(verdict({"checks": checks}), "needs_review")
        checks["operation"]["status"] = "fail"
        self.assertEqual(verdict({"checks": checks}), "fail")
        with self.assertRaises(RuntimeError):
            verdict({"checks": {"identity": checks["identity"]}})

    def test_real_vision_payload_contains_sources_and_target(self):
        import json
        folder, args = self.setup_identity()
        args.stage, args.samples = "identity", 8
        args.image_max_edge = 1400
        response = {"choices": [{"message": {"content": json.dumps({"checks": {
            name: {"status": "pass", "evidence": "test observation"} for name in CHECKS}})}}]}
        with patch("qc_dual_consistency.request_json", return_value=response) as api:
            result = review(folder, folder / "identity_lock/reference_sheet.png", load_identity(folder), "test", args)
        content = api.call_args.args[2]["messages"][1]["content"]
        self.assertEqual(len([c for c in content if c["type"] == "image_url"]), 2)
        self.assertEqual(result["status"], "pass")

    def test_existing_v1_frame_cannot_silently_pass(self):
        folder, args = self.setup_identity()
        (folder / "generated_images").mkdir()
        Image.new("RGB", (64, 64)).save(folder / "generated_images/variant-01-start.png")
        with self.assertRaises(RuntimeError):
            generate_one_image("test", folder, {"variant_id": 1}, args)

    def test_missing_selected_frame_fails(self):
        folder, _ = self.setup_identity()
        with self.assertRaises(RuntimeError):
            targets(folder, "keyframes", {1}, load_identity(folder))

    def test_explicit_optional_sheet_is_one_extra(self):
        folder, args = self.setup_identity()
        args.separate_sheet = True
        with patch("generate_images.multipart_request", return_value=self.response) as api:
            result = usage(folder, "test", args)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(result["additional_image_count"], 1)
        with self.assertRaises(RuntimeError):
            keyframe_references(folder, {"variant_id": 1}, "start", 1)

    def test_product_dir_and_batch_dir(self):
        folder = self.fixture("apparel")
        self.assertEqual(selected_product_dirs(folder), [folder])
        self.assertEqual(selected_product_dirs(self.root, "01"), [folder])

    def test_product_brief_requires_complete_extraction_and_full_vision_coverage(self):
        folder = self.fixture("electronics")
        manifest = load_json(folder / "product_manifest.json")
        analysis = load_json(folder / "image_analysis.json")
        assert_full_image_coverage(folder, manifest, analysis)

        manifest["images"].append({"local_path": "images/missing-detail.png"})
        with self.assertRaisesRegex(RuntimeError, "full-image vision gate failed"):
            assert_full_image_coverage(folder, manifest, analysis)

        manifest["images"] = manifest["images"][:1]
        manifest["extraction_audit"]["complete"] = False
        with self.assertRaisesRegex(RuntimeError, "extraction audit"):
            assert_full_image_coverage(folder, manifest, analysis)

    def test_synthetic_fixture_is_rejected_before_paid_generation(self):
        folder = self.fixture("apparel")
        manifest = load_json(folder / "product_manifest.json")
        manifest["fixture_only"] = True
        write_json(folder / "product_manifest.json", manifest)
        with self.assertRaisesRegex(RuntimeError, "Synthetic test fixture"):
            context(folder)

    def test_video_provenance_invalidates_changed_reference(self):
        folder, args = self.setup_identity()
        with patch("generate_images.multipart_request", return_value=self.response):
            generate_one_image("test", folder, {"variant_id": 1}, args)
        frames = [folder / "generated_images" / f"variant-01-{role}.png" for role in ("start", "end")]
        video = folder / "videos/variant-01.mp4"
        video.parent.mkdir()
        video.write_bytes(b"synthetic video bytes")
        expected = video_contract(folder, frames, "veo3.1", "test prompt",
                                  {"duration": "8", "aspect_ratio": "9:16"})
        record_video(folder, video, expected, "test prompt", {"task_id": "fake"})
        check_existing_video(folder, video, expected)
        validate_video_chain(folder, video)
        frames[0].write_bytes(b"changed")
        with self.assertRaises(RuntimeError):
            validate_video_chain(folder, video)

    def test_omni_reference_uses_storyboard_identity_and_one_optional_extra(self):
        folder, _ = self.setup_identity()
        storyboard = folder / "runs/test/storyboard/variant-03-storyboard.png"
        storyboard.parent.mkdir(parents=True)
        Image.new("RGB", (64, 64), "blue").save(storyboard)
        write_json(storyboard.with_suffix(".provenance.json"), {"type": "image2_chronological_storyboard"})
        variant = {"reference_images": [
            str(storyboard.relative_to(folder)),
            "identity_lock/reference_sheet.png",
            "images/source.png",
        ]}
        references = omni_storyboard_identity_paths(folder, variant)
        # storyboard and identity grid are the two mandatory all-purpose refs;
        # any extra references declared on the variant trail them in order.
        self.assertEqual(
            references,
            [storyboard, folder / "identity_lock/reference_sheet.png", folder / "images/source.png"],
        )

        with self.assertRaisesRegex(RuntimeError, "chronological storyboard"):
            omni_storyboard_identity_paths(folder, {"reference_images": ["identity_lock/reference_sheet.png"]})

        extra = folder / "images/extra.png"
        Image.new("RGB", (64, 64), "green").save(extra)
        with self.assertRaisesRegex(RuntimeError, "at most three images"):
            omni_storyboard_identity_paths(folder, {"reference_images": [
                str(storyboard.relative_to(folder)), "images/source.png", "images/extra.png"
            ]})

    def test_classifier_routes_furniture_and_stops_unknown_products(self):
        self.assertEqual(classify_by_keywords("Portable folding chair")[0], "furniture")
        self.assertIsNone(classify_by_keywords("Cotton sleeping bag")[0])
        folder = self.root / "unknown-product"
        folder.mkdir()
        write_json(folder / "product_manifest.json", {"product_name": "Ultralight sleeping bag"})
        write_json(folder / "image_analysis.json", {"materials": "polyester fabric shell"})
        result = classify_product(folder, force=True)
        self.assertEqual(result["category"], "unclassified")
        self.assertTrue(result["requires_manual_category"])


if __name__ == "__main__":
    unittest.main()

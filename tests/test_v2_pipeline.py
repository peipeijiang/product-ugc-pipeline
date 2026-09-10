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
from generate_images import generate_one_image, keyframe_references
from generate_videos_lk888 import omni_storyboard_identity_paths
from qc_dual_consistency import CHECKS, verdict, review, targets
from v2_contract import (SPECS, action_ledger, check_existing_video, digest, hashes,
                         context, load_identity, record_video, require_qc, validate_scene_chain,
                         validate_video_chain, video_contract)


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

    def test_omni_reference_uses_only_storyboard_and_identity_grid(self):
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
        self.assertEqual(references, [storyboard, folder / "identity_lock/reference_sheet.png"])

        with self.assertRaisesRegex(RuntimeError, "chronological storyboard"):
            omni_storyboard_identity_paths(folder, {"reference_images": ["identity_lock/reference_sheet.png"]})


if __name__ == "__main__":
    unittest.main()

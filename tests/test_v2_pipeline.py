"""Offline regression tests, NOT product/video quality benchmark results."""
import argparse
import base64
import io
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from PIL import Image
from common import load_json, write_json, selected_product_dirs
from build_product_brief import assert_full_image_coverage, build_with_model
from generate_product_identity_lock import generate, parser
from generate_usage_pose_sheet import generate as usage
from generate_images import generate_image_file, generate_one_image, storyboard_references
from generate_videos_lk888 import omni_storyboard_identity_paths, require_chronological_storyboard
from classify_product_category import classify_by_keywords, classify_product
from qc_dual_consistency import CHECKS, verdict, review, targets
from v2_contract import (SPECS, action_ledger, check_existing_video, digest, hashes,
                         category_spec, context, load_identity, record_video, require_qc, validate_scene_chain,
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
        args.storyboards = True
        # These tests patch the OpenAI-compatible Images route, so pin that
        # provider instead of the production upDrama media-task default.
        args.image_provider = "laozhang-image2"
        args.image_fallback = "none"
        return args

    def approve(self, folder, stage, paths):
        # Synthetic QC records are only test setup; production uses the vision endpoint.
        write_json(folder / "qc" / f"{stage}.json", {"identity_sha256": load_identity(folder)["sha256"],
            "results": [{"path": str(p.relative_to(folder)), "sha256": digest(p), "status": "pass"} for p in paths]})

    def approve_storyboard_fixture(self, folder, storyboard):
        # Offline gate-contract fixture, not a claim that this synthetic image
        # has received real vision review or may be used in production.
        timeline = [{"time":"0-5s", "visual":"ready-state wide"},
                    {"time":"5-10s", "visual":"ready-state detail"}]
        identity = load_identity(folder)
        write_json(storyboard.with_suffix('.provenance.json'), {
            'type':'image2_chronological_storyboard', 'sha256':digest(storyboard),
            'provider':'mock-offline', 'actual_prompt':'synthetic test only',
            'references':{identity['output_path']:identity['sha256']}})
        write_json(folder/'qc/storyboards'/f'{storyboard.stem}.json', {
            'status':'pass', 'sha256':digest(storyboard),
            'timeline_sha256':hashlib.sha256(json.dumps(timeline,ensure_ascii=False,
                sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'panel_count':2,'chronological':True,'singleton_per_panel':True,
            'reviewer':'mock-offline','evidence':['synthetic gate fixture only']})
        self.approve(folder,'storyboards',[storyboard])
        return timeline

    def storyboard_beats(self):
        return [
            {"time": "0-3s", "visual": "problem setup", "spoken": "Need this"},
            {"time": "3-7s", "visual": "supported product use", "spoken": "It works"},
            {"time": "7-10s", "visual": "ready-state buyer result", "spoken": "Sorted"},
        ]

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

    def test_production_families_single_grid_and_storyboard_chain(self):
        for category, (_, _, panels) in SPECS.items():
            with self.subTest(category=category):
                folder, args = self.setup_identity(category)
                identity = load_identity(folder)
                self.assertEqual(len(identity["panels"]), len(panels))
                self.assertEqual(len(list((folder / "identity_lock").glob("*.png"))), 1)
                self.assertEqual(load_json(folder / "usage_poses/manifest.json")["additional_image_count"], 0)
                with patch("generate_images.multipart_request", return_value=self.response) as api:
                    generate_one_image("test", folder, {"variant_id": 1, "storyboard_10s": self.storyboard_beats()}, args)
                self.assertEqual(api.call_count, 1)
                call = api.call_args_list[0]
                self.assertEqual(len(call.kwargs["files"]), 2)
                self.assertIn("storyboard", call.kwargs["fields"]["prompt"].lower())
                self.assertNotIn("weight", call.kwargs["fields"])
                storyboard = folder / "generated_images/variant-01-storyboard.png"
                self.assertTrue(storyboard.is_file())
                provenance = load_json(storyboard.with_suffix(".provenance.json"), {})
                self.assertEqual(provenance.get("type"), "chronological_storyboard")
                validate_scene_chain(folder, [storyboard])
                with self.assertRaises(RuntimeError):
                    require_qc(folder, [storyboard], "storyboards")
                self.approve(folder, "storyboards", [storyboard])
                require_qc(folder, [storyboard], "storyboards")

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
            generate_one_image("test", folder, {"variant_id": 1, "storyboard_10s": self.storyboard_beats()}, args)
        generated_storyboard = folder / "generated_images/variant-01-storyboard.png"
        validate_scene_chain(folder, [generated_storyboard])
        generated_refs = storyboard_references(folder, {"variant_id": 1}, 3)
        self.assertEqual(len(generated_refs), 3)
        self.assertEqual(generated_refs[-1], operation_sheet)

        storyboard = folder / "runs/test/storyboard/variant-01-storyboard.png"
        storyboard.parent.mkdir(parents=True)
        Image.new("RGB", (64, 64), "blue").save(storyboard)
        write_json(storyboard.with_suffix(".provenance.json"), {"type": "image2_chronological_storyboard"})
        timeline = self.approve_storyboard_fixture(folder, storyboard)
        omni_refs = omni_storyboard_identity_paths(folder, {
            "reference_images": [str(storyboard.relative_to(folder))],
            "storyboard_10s": timeline,
        })
        self.assertEqual(omni_refs, [storyboard, folder / "identity_lock/reference_sheet.png", operation_sheet])

        protected_refs = omni_storyboard_identity_paths(folder, {
            "reference_images": [str(storyboard.relative_to(folder))],
            "storyboard_10s": timeline,
            "protect_product_configuration": True,
            "generation_risk": {"level": "critical"},
        })
        self.assertEqual(protected_refs, [storyboard, folder / "identity_lock/reference_sheet.png"])

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

    def test_media_failure_uses_laozhang_key_for_openai_fallback(self):
        folder = self.fixture("electronics")
        args = self.args(folder)
        args.image_provider = "tt-image-2.5"
        args.image_fallback = "laozhang-image2"
        reference = folder / "images/source.png"
        destination = folder / "generated_images/variant-01.png"

        def key_for_url(url):
            return "lk888-key" if "lk888" in url else "laozhang-key"

        with patch("generate_images.require_api_key_for_base_url", side_effect=key_for_url), \
             patch("generate_images.generate_image_via_media_task", side_effect=RuntimeError("media failed")), \
             patch("generate_images.request_openai_image", return_value=self.response) as fallback:
            result = generate_image_file(
                "lk888-key", folder, {"variant_id": 1}, args, destination, "prompt",
                reference_override=[reference],
            )

        self.assertEqual(result["image_provider"], "laozhang-image2")
        self.assertEqual(fallback.call_args.args[0], "laozhang-key")
        self.assertTrue(destination.exists())

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

    def test_legacy_scene_frames_cannot_be_submitted(self):
        folder, args = self.setup_identity()
        (folder / "generated_images").mkdir(exist_ok=True)
        Image.new("RGB", (64, 64)).save(folder / "generated_images/variant-01-start.png")
        Image.new("RGB", (64, 64)).save(folder / "generated_images/variant-01-end.png")
        with self.assertRaisesRegex(RuntimeError, "chronological storyboard"):
            omni_storyboard_identity_paths(folder, {
                "variant_id": 1,
                "reference_images": [
                    "generated_images/variant-01-start.png",
                    "generated_images/variant-01-end.png",
                ],
                "storyboard_10s": self.storyboard_beats(),
            })

    def test_missing_selected_frame_fails(self):
        folder, _ = self.setup_identity()
        with self.assertRaises(RuntimeError):
            targets(folder, "storyboards", {1}, load_identity(folder))

    def test_explicit_optional_sheet_is_one_extra(self):
        folder, args = self.setup_identity()
        args.separate_sheet = True
        with patch("generate_images.multipart_request", return_value=self.response) as api:
            result = usage(folder, "test", args)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(result["additional_image_count"], 1)
        extra_sheet = folder / result["output_path"]
        self.approve(folder, "usage", [extra_sheet])
        self.assertEqual(
            storyboard_references(folder, {"variant_id": 1}, 3),
            [folder / "images/source.png", folder / "identity_lock/reference_sheet.png", extra_sheet],
        )

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

    def test_product_brief_requests_factorized_multimodal_classification(self):
        response = {"choices": [{"message": {"content": '{"product_name":"test"}'}}]}
        with patch("build_product_brief.request_json", return_value=response) as request:
            build_with_model("key", {"product_name": "test"}, {"images": []}, "model", "https://example.invalid", 30)
        prompt = request.call_args.args[2]["messages"][1]["content"]
        self.assertIn("catalog_taxonomy", prompt)
        self.assertIn("production_classification", prompt)
        self.assertIn("physical_traits", prompt)
        self.assertIn("interaction_modes", prompt)
        self.assertIn("general-merchandise", prompt)

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
            generate_one_image("test", folder, {"variant_id": 1, "storyboard_10s": self.storyboard_beats()}, args)
        storyboard = folder / "generated_images/variant-01-storyboard.png"
        video = folder / "videos/variant-01.mp4"
        video.parent.mkdir()
        video.write_bytes(b"synthetic video bytes")
        expected = video_contract(folder, [storyboard], "omni-flash", "test prompt",
                                  {"duration": "10", "aspect_ratio": "9:16"})
        record_video(folder, video, expected, "test prompt", {"task_id": "fake"})
        check_existing_video(folder, video, expected)
        validate_video_chain(folder, video)
        storyboard.write_bytes(b"changed")
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
        timeline = self.approve_storyboard_fixture(folder, storyboard)
        variant['storyboard_10s'] = timeline
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
            ], "storyboard_10s": timeline})

    def test_omni_scene_anchor_bypass_rejected(self):
        folder, _ = self.setup_identity()
        with self.assertRaisesRegex(RuntimeError, 'chronological storyboard'):
            omni_storyboard_identity_paths(folder, {
                'reference_images':['images/source.png'], 'omni_reference_scene_anchor':True})

    def test_storyboard_review_is_bound_to_timeline_and_current_image(self):
        folder, _ = self.setup_identity()
        storyboard = folder/'generated_images/variant-01-storyboard.png'
        storyboard.parent.mkdir(exist_ok=True)
        Image.new('RGB',(64,64),'blue').save(storyboard)
        timeline = self.approve_storyboard_fixture(folder,storyboard)
        variant={'variant_id':1,'storyboard_10s':timeline}
        require_chronological_storyboard(folder,storyboard,variant)
        changed={**variant,'storyboard_10s':timeline+[{'time':'10-11s','visual':'changed'}]}
        with self.assertRaisesRegex(RuntimeError,'visual storyboard review'):
            require_chronological_storyboard(folder,storyboard,changed)

    def test_classifier_routes_broad_families_before_multimodal_cognition(self):
        self.assertEqual(classify_by_keywords("Portable folding chair")[0], "furniture")
        self.assertEqual(classify_by_keywords("Cotton sleeping bag")[0], "sports-outdoor")
        folder = self.root / "unknown-product"
        folder.mkdir()
        write_json(folder / "product_manifest.json", {"product_name": "Unidentified physical product"})
        write_json(folder / "image_analysis.json", {"materials": "polyester fabric shell"})
        result = classify_product(folder, force=True)
        self.assertEqual(result["category"], "unclassified")
        self.assertTrue(result["requires_product_brief"])
        self.assertTrue(result["requires_manual_category"])

    def test_multimodal_profile_drives_family_and_cross_category_traits(self):
        folder = self.root / "hammock-product"
        folder.mkdir()
        write_json(folder / "product_manifest.json", {"product_name": "Canvas camping hammock"})
        write_json(folder / "product_brief.json", {
            "product_type": "spreader-bar hammock",
            "catalog_taxonomy": {
                "vertical": "sporting-goods",
                "path": ["Sporting Goods", "Outdoor Recreation", "Camping Hammocks"],
                "main_function": "suspend one person between two anchors",
            },
            "production_classification": {
                "visual_family": "sports-outdoor",
                "physical_traits": ["flexible-textile", "suspended-load", "multi-part"],
                "interaction_modes": ["suspend-anchor", "body-support"],
                "classification_evidence": ["images/source.png"],
                "confidence": "high",
                "requires_manual_review": False,
            },
        })
        result = classify_product(folder, force=True)
        self.assertEqual(result["category"], "sports-outdoor")
        self.assertIn("suspended-load", result["physical_traits"])
        self.assertEqual(result["detected_from"], "multimodal_product_brief")
        spec = category_spec(result["category"], result["physical_traits"])
        self.assertIn("continuous load path", spec["checks"])
        self.assertIn("suspension line", spec["checks"])

    def test_low_confidence_general_family_blocks_until_explicit_review(self):
        folder = self.fixture("general-merchandise")
        write_json(folder / "category.json", {
            "schema_version": 2,
            "category": "general-merchandise",
            "requires_manual_category": True,
        })
        with self.assertRaisesRegex(RuntimeError, "requires manual review"):
            context(folder)
        self.assertEqual(context(folder, "general-merchandise")["spec"]["category"], "general-merchandise")


if __name__ == "__main__":
    unittest.main()

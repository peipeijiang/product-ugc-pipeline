---
name: product-ugc-pipeline
description: Build product UGC ad-production pipelines from ecommerce product URLs. Use when Codex needs to scrape product pages, save product image/material folders, analyze image assets with a vision model, generate multiple Instagram/TikTok creator-style UGC prompts, create product-faithful reference images with LaoZhang GPT-Image-2, or create VEO 3.1 product videos through LaoZhang or LK888/updrama APIs.
---

# Product UGC Pipeline

## Core Rule

Preserve the original product appearance above all else. The pad image is the visual identity lock for VEO, but default videos should still show practical product use. Describe supported actions and scene flow, not a competing redesign of the product.

## Workflow

1. Put product URLs in a text file, one URL per line.
2. Run `scripts/scrape_products.py` to create numbered product folders and download product-only page images.
3. Run `scripts/analyze_materials.py` with `LAOZHANG_API_KEY` to describe filtered product images and identify usage mechanics/reference roles.
4. Run `scripts/build_product_brief.py` to synthesize product usage cognition from `product_manifest.json` + `image_analysis.json`.
5. Run `scripts/generate_ugc_prompts.py` to create 10 UGC prompt variants grounded in the product brief.
6. Run `scripts/generate_images.py` to create image-to-image “pad images” or start/end keyframes using GPT-Image-2 and the selected product references.
7. Run `scripts/generate_videos.py` to send generated pad images or start/end keyframes to VEO 3.1 async video generation.
8. If LaoZhang VEO channels are unavailable, run `scripts/generate_videos_lk888.py` to send public start/end keyframe URLs to LK888/updrama VEO.

Default output structure:

```text
product-ugc-output/
├── 01-product-name/
│   ├── product_manifest.json
│   ├── materials.md
│   ├── images/
│   ├── image_analysis.json
│   ├── product_brief.json
│   ├── ugc_prompts.json
│   ├── generated_images/
│   └── videos/
└── run_manifest.json
```

## Quick Commands

```bash
python product-ugc-pipeline/scripts/scrape_products.py urls.txt --out product-ugc-output
LAOZHANG_API_KEY=sk-... python product-ugc-pipeline/scripts/analyze_materials.py product-ugc-output
LAOZHANG_API_KEY=sk-... python product-ugc-pipeline/scripts/build_product_brief.py product-ugc-output
LAOZHANG_API_KEY=sk-... python product-ugc-pipeline/scripts/generate_ugc_prompts.py product-ugc-output --count 10
LAOZHANG_API_KEY=sk-... python product-ugc-pipeline/scripts/generate_images.py product-ugc-output --variants 1-10 --model gpt-image-2-vip --size 1024x1536 --keyframes
LAOZHANG_API_KEY=sk-... python product-ugc-pipeline/scripts/generate_videos.py product-ugc-output --variants 1-10 --model veo-3.1-fast-fl
LK888_API_KEY=sk-... python product-ugc-pipeline/scripts/generate_videos_lk888.py product-ugc-output --variants 1-10 --model veo3.1 --generation-mode fast
```

Use `--dry-run` on generation scripts when the user wants prompts and manifests without paid API calls.

## Product Folder Requirements

For each product folder:

- `product_manifest.json`: source URL, product name, detected price, selling points, downloaded image list, source image URLs.
- `materials.md`: human-readable material log; update it after image analysis and product-brief synthesis.
- `images/`: original downloaded product-only images; never overwrite these.
- `image_analysis.json`: per-image visual description, product-related flag, exact product-identity details, visible/inferred use mechanics, UGC usefulness score, prompt risks, and recommended usage.
- `product_brief.json`: synthesized product cognition, including confirmed identity, step-by-step usage, scenes, proof moments, misuse risks, and reference image strategy.
- `ugc_prompts.json`: 10 prompt variants with creator persona, scene, usage logic, proof moment, dialogue/script, image prompt, start/end keyframe prompts, video prompt, and selected reference images.
- `generated_images/`: GPT-Image-2 outputs named by prompt variant; with `--keyframes`, writes `variant-XX-start.png` and `variant-XX-end.png`.
- `videos/`: VEO output JSON, status JSON, and downloaded MP4 files.

## Prompt Standards

Generate prompts in English for image/video models, but keep metadata fields readable in either Chinese or English depending on user preference.

Every UGC variant must include:

- Hook in the first 2 seconds.
- Creator persona and shot style, e.g. kitchen counter demo, unboxing, problem-solution, ASMR cleaning, mom-life hack, apartment mini-kitchen.
- Natural dialogue that explains the product, not a silent product montage.
- VEO prompts may include native English voiceover/dialogue when the user wants spoken product explanation. Short Instagram-style feature overlay labels should be stored as post-production metadata; do not ask VEO to render overlay text because model-rendered text can garble.
- A proof moment showing the core function clearly.
- A final sell shot with product in hand or on counter.
- Product-fidelity block: “Use the provided product reference as the canonical source. Do not redesign, recolor, simplify, enlarge logos, change flower/gourd/cat silhouette, or invent extra parts.”
- Negative constraints: no fake claims, no impossible effects, no unrelated accessories, no distorted product geometry.

Actual VEO `video_prompt` should be a conservative usage demo:

- Treat the generated pad image / first frame as the visual identity lock.
- Show one simple real-world use action supported by `product_brief.json`.
- Prefer start/end keyframes for 8-second usage videos: start = hook/problem setup, end = believable proof/sell shot.
- When two keyframes exist, VEO receives both as `input_reference`; image 1 is the first frame and image 2 is the final frame.
- Allow adult hands and kitchen/sink/tabletop context when needed for a useful demo.
- Describe the action flow, proof moment, and camera style, but avoid re-describing product geometry as if VEO should redesign it.
- Do not ask VEO to add new product parts, mechanisms, labels, containers, chambers, hinges, buttons, reservoirs, or unsupported accessories.
- Keep detailed UGC dialogue, product explanation, and usage logic in `dialogue_script`, `function_intro_prompt`, `voiceover_script_8s`, `usage_logic`, `shot_plan`, and `model_suggested_video_prompt` for later editing/voiceover; do not feed those directly to VEO by default.
- `on_screen_callouts` may contain short feature tags such as “MagSafe Snap” or “Foldable Stand”, but these are for post-production overlays; put spoken explanation directly into VEO native-audio prompt, not as captions.

Every UGC variant must be grounded in `product_brief.json`:

- Use `step_by_step_usage` and `confirmed_use_cases` as the truth source for product operation.
- Use `misuse_risks_to_avoid` to prevent wrong demonstrations.
- Use `reference_image_strategy` plus `image_analysis.json` to choose full-product reference images for Image 2.
- Prefer explicit `canonical_reference_images` / `full_product_reference_images` in `product_brief.json` when present, and exclude `alternate_sku_reference_images`, `rejected_reference_images`, `non_canonical_reference_images`, and `avoid_reference_images`.
- The canonical reference must show the true product full silhouette, correct SKU/style, real proportions, and key functional zones. Do not use accessory-only, packaging-only, loose parts, alternate colorway/SKU, or detail-only photos as the identity reference.
- If usage is uncertain, write a conservative tabletop/hand demo rather than inventing a dramatic function.

## LaoZhang API Notes

Read `references/laozhang-api-notes.md` before changing API calls. Key defaults:

- Base URL: `https://api.laozhang.ai/v1`
- API key env var: `LAOZHANG_API_KEY`
- GPT-Image-2 reverse routes: `/images/generations`, `/images/edits`, or `/chat/completions`.
- Use `gpt-image-2-vip` for common explicit sizes; avoid unsupported 4K sizes on VIP.
- VEO 3.1 async endpoint: `POST /videos`, poll `GET /videos/{id}`, then download via `GET /videos/{id}/content`.
- Use VEO models with `-fl` suffix for image-to-video reference frames.

## LK888 / updrama API Notes

Use `scripts/generate_videos_lk888.py` only when LK888/updrama is the requested provider or LaoZhang VEO is unavailable.

Key defaults:

- Base URL: `https://api.lk888.ai/api`
- API key env var: `LK888_API_KEY`
- Capability refresh endpoints: `GET /v1/skills`, `GET /v1/skills/guide`, and `GET /v1/skills/models/{model_name}`.
- Balance endpoint: `GET /v1/skills/balance`; query it before paid batches when practical.
- Media creation endpoint: `POST /v1/media/generate`; poll `GET /v1/skills/task-status?task_id={task_id}` until `is_final=true`.
- VEO 3.1 model name: `veo3.1`; common params are `generation_mode=fast`, `aspect_ratio=9:16`, `images=[start_url,end_url]`, and `enhance_prompt=false`.
- `veo3.1-lite` uses `quality=sd|4k` instead of `generation_mode`, but may have inactive channels; verify pricing/status before relying on it.
- Upload params require publicly reachable URLs. The API does not accept local file paths or multipart image uploads for `images`.
- The adapter writes LK888 outputs to `videos_lk888/` so LaoZhang outputs in `videos/` remain untouched.
- If an API behavior contradicts the capability docs, submit `POST /v1/skills/feedback` and record the returned `feedback_id`.

## Quality Gate

Before delivering outputs, inspect `materials.md`, `image_analysis.json`, and `ugc_prompts.json` for each product:

- Reject image prompts that do not preserve the exact product form.
- Reject VEO prompts that redesign the product, invent mechanisms, or introduce unsupported actions.
- Reject prompts that use a weak reference image when a cleaner product image exists.
- Prefer close-up product photos as image references over lifestyle images.
- Before calling Image 2, manually or programmatically verify the selected reference images are the correct product, not another SKU on the same page.
- Image prompts must explicitly say the first selected full-product reference is canonical and conflicting page images should be ignored.
- For Image 2 edits, pass multiple verified full-product references when available, with the first image as the canonical product identity lock.
- If generated images drift from the original product, prefer `generate_images.py --compose-only` with the cleanest reference asset over asking the image model to redraw the product.

## Defaults

- Scraping: use JSON-LD `Product.image` assets first and exclude generic page images by default. Add `--include-page-images` only when product pages lack structured product images.
- Vision analysis: analyze the first 6 filtered product images by default. Use `--limit-images 0` to analyze all filtered images, or `--limit-images 2` for cheap quick tests.
- Prompt generation: read `product_brief.json` when present; if missing, fall back to manifest + image analysis but treat that as lower confidence.

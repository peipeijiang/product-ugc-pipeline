---
name: product-ugc-pipeline
description: Build product UGC ad-production pipelines from ecommerce product URLs. Use when Codex needs to scrape product pages, save product image/material folders, analyze image assets with a vision model, generate multiple short-form ecommerce UGC prompts, create product-faithful reference images with LaoZhang GPT-Image-2, or create VEO 3.1 product videos through LaoZhang or LK888/updrama APIs.
---

# Product UGC Pipeline

## Core Rule

Preserve the original product appearance above all else. The pad image is the visual identity lock for VEO, but default videos should still show practical product use. Describe supported actions and scene flow, not a competing redesign of the product.

Product references lock the product, not the whole source photo. Use source images to preserve product identity, function surfaces, proportions, material, color, mechanisms, and supported use. Do not unnecessarily copy the original product-photo background, table, lighting, props, or composition unless those elements are essential to the product function.

## Workflow

1. Put product URLs in a text file, one URL per line.
2. Run `scripts/scrape_products.py` to create numbered product folders and download product-only page images.
3. Run `scripts/analyze_materials.py` with `LAOZHANG_API_KEY` to describe filtered product images and identify usage mechanics/reference roles.
4. Run `scripts/build_product_brief.py` to synthesize product usage cognition from `product_manifest.json` + `image_analysis.json`.
5. Run `scripts/generate_ugc_prompts.py` to create 10 UGC prompt variants grounded in the product brief.
6. Run `scripts/generate_images.py` to create image-to-image “pad images” or start/end keyframes using GPT-Image-2 and the selected product references.
7. Run `scripts/generate_videos.py` to send generated pad images or start/end keyframes to VEO 3.1 async video generation.
8. If LaoZhang VEO channels are unavailable, run `scripts/generate_videos_lk888.py` to send public start/end keyframe URLs to LK888/updrama VEO.
9. When the user asks for “two new versions”, “再来两个新版本”, or any fresh reroll, prefer `scripts/run_fresh_batch.py` so the skill first extends the canonical prompt file, then keyframes, then videos, instead of accidentally rerunning an old prompt batch.

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
│   ├── runs/
│   │   ├── 20260520-dual-refresh/
│   │   │   ├── prompt_batch.json
│   │   │   ├── image_generation_results.json
│   │   │   ├── video_generation_results.json
│   │   │   ├── keyframes/
│   │   │   └── videos/
│   │   └── ...
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
LK888_API_KEY=sk-... python product-ugc-pipeline/scripts/generate_videos_lk888.py product-ugc-output --variants 1-10 --model omni-flash --base-url https://api.lk888.ai --status-endpoint /v1/media/status --duration 8
LAOZHANG_API_KEY=sk-... LK888_API_KEY=sk-... python product-ugc-pipeline/scripts/run_fresh_batch.py product-ugc-output --products 01,02 --count 2 --batch-label 20260520-dual-refresh
```

This skill does not use a local dry-run fallback for prompt/image/video generation. Generation steps should run through the real model/API path so outputs stay consistent with production behavior.

This skill must fail fast when the cognition pipeline is incomplete. Do not manually invent `image_analysis.json`, `product_brief.json`, `ugc_prompts.json`, or generated keyframes to keep a batch moving. If vision analysis, product-brief synthesis, prompt generation, or Image2 keyframe generation fails, stop and report the failing provider/model/error. Continue only after switching to a working model/provider or after the user explicitly asks for a non-production experiment.

## Product Folder Requirements

For each product folder:

- `product_manifest.json`: source URL, product name, detected price, selling points, downloaded image list, source image URLs.
- `materials.md`: human-readable material log; update it after image analysis and product-brief synthesis.
- `images/`: original downloaded product-only images; never overwrite these.
- `image_analysis.json`: per-image visual description, product-related flag, exact product-identity details, visible/inferred use mechanics, UGC usefulness score, prompt risks, and recommended usage.
- `product_brief.json`: synthesized product cognition, including confirmed identity, step-by-step usage, scenes, proof moments, misuse risks, and reference image strategy.
- `ugc_prompts.json`: canonical prompt file. New rerolls should append new variants into this same file so prompt history stays in one place. Final media generation reads `image_prompt`, `start_frame_prompt`, `end_frame_prompt`, and `video_prompt`; do not keep duplicate “model suggested” prompt fields in this canonical file.
- `runs/`: append-only batch history. Every fresh reroll or re-generation should create a labeled run folder containing the batch JSON, intermediate keyframes, and that run's own result manifests. Keep only the latest canonical `generated_images/` and `videos/` at the top level for quick access.
- `generated_images/`: GPT-Image-2 outputs named by prompt variant; with `--keyframes`, writes `variant-XX-start.png` and `variant-XX-end.png`.
- `videos/`: canonical VEO output JSON, status JSON, and downloaded MP4 files. New runs should append by `variant-XX` inside this folder instead of creating `videos_*` batch folders.

### Fail-Fast Production Contract

For production videos:

- `image_analysis.json` must come from a successful vision model run. If any image analysis record contains `analysis.error`, stop.
- `product_brief.json` must include product identity, confirmed use cases, step-by-step usage, misuse risks, and hallucination defense. If any required field is missing, stop.
- `ugc_prompts.json` must be generated from the valid manifest + image analysis + product brief, either by the prompt model or by Codex directly when product cognition is clear. Do not invent prompts without reading the product source files; direct Codex-authored prompts are production-valid when they cite the same inputs, pass the quality gate, and record a `prompt_history` note.
- Functional start/end keyframes must be generated by Image2/model image generation from canonical product references. Do not use `--compose-only` product-photo pads for usage videos; those are acceptable only for explicit stable b-roll.
- If the pipeline cannot complete a step, report the exact failed step/model/provider and do not proceed to paid video generation.

### Universal Hallucination Defense

Every product gets automatic hallucination-defense injection into all VEO/image prompts.

**How it works:**
1. `build_product_brief.py` asks the LLM to produce `hallucination_defense` with six categories per product:
   phantom_parts, shape_preservation, material_texture_lock, action_bounds, context_contamination, scale_anchor.
2. `generate_ugc_prompts.py` reads `product_brief.json` and auto-injects defense into:
   `product_fidelity_block()` (appended to every prompt), `negative_prompt`, and LLM prompt-writing instructions.
3. Without `product_brief.json`, a universal baseline defense fires covering all common VEO hallucination categories.

**Categories (universal):**
- Phantom parts: cables, wires, hoses, motors, buttons, lids, chambers, hinges, handles, blades, text, packaging
- Shape drift: silhouette must not change (flower→circle, gourd→cylinder)
- Material/texture: surface finish, color, transparency must stay exact
- Action invention: product cannot do things unsupported by reference images
- Context contamination: training-data clichés (“every outlet has a cord”, “every kitchen has a window”)
- Scale distortion: product must stay realistic size relative to hands/objects


## Prompt Standards

Generate prompts in English for image/video models, but keep metadata fields readable in either Chinese or English depending on user preference.

Before generating image/video prompts, separate cognition into four layers:

1. Product identity: exact appearance, silhouette, materials, functional surfaces, visible mechanisms, ports, accessories, and SKU/colorway that must never drift.
2. Commercial promise: the product title, page selling points, and confirmed selling points that explain why a buyer would care.
3. Product function: confirmed use cases, step-by-step operation, proof moments, misuse risks, and what must be visible for a buyer to believe the promise.
4. Buyer-visible effect: the after-state created by the product, such as calmer pet, cleaner sink, faster prep, less clutter, easier setup, cooler air, more comfortable sleep, or safer grooming.
5. Scene imagination: realistic lifestyle contexts inferred from the buyer problem, function, and selling angle, not limited to the original product-page photos.

Every batch should deliberately vary the variants by buyer problem, selling angle, scenario, action, proof moment, and final effect. Avoid making all prompts the same “place product on counter/table, show result” pattern.
For rerolls, always treat older `ugc_prompts*.json` files as history to avoid, not as the default video source, unless the user explicitly asks to rerun that exact batch.

Before writing multiple variants, allocate a distinct `primary_function_focus` from `product_brief.confirmed_selling_points`, product-page `selling_points`, `confirmed_use_cases`, `step_by_step_usage`, and `proof_moments`. Do not let minor hardware details, materials, or setup steps become the lead angle when the product title/page clearly sells a higher-level benefit. If overlap is unavoidable, materially change at least four dimensions: buyer problem, buyer-visible effect, scene geometry, proof moment, camera idea, pace, and creator style. For multifunction wearables such as smart rings, do not default every clip to remote photo control; split variants across confirmed functions such as app/health check, display/status glance, charging dock, touch gesture, activity tracking, waterproof daily wear, or fit/detail as supported by the product brief.

When a phone appears in an image or video prompt, specify physically possible phone geometry:

- If the phone is acting as the camera for selfie / remote shutter / timer capture, the phone screen should face the creator and the camera lens should point toward the creator. The viewer should see the phone back/side, mirror reflection, or over-shoulder setup unless a second camera/phone is explicitly present.
- If the viewer must see the phone screen or app preview, use an over-shoulder, mirror, tabletop, or second-device composition so the screen faces the external camera while the product/hand remains visible.
- Do not show an impossible shot where a single phone both films the creator with its front camera and has its screen facing the external viewer with no mirror/secondary-camera explanation.
- For wireless charging pads, the phone lies flat screen-up on the charging surface unless the actual product is a stand. Do not make the phone stand upright just because it is being charged.

Every UGC variant must include:

- Hook in the first 2 seconds.
- Creator persona and shot style, e.g. kitchen counter demo, unboxing, problem-solution, ASMR cleaning, mom-life hack, apartment mini-kitchen.
- Natural dialogue that sells the buyer problem/desire, the product intervention, and the improved after-state. The voice should feel like a stylish short-form lifestyle creator: young, bright, specific, and emotionally interested in the product benefit, without asking for any platform UI, platform logo, or social icon.
- VEO prompts may include native English voiceover/dialogue when the user wants a spoken product explanation. VEO may render 1–2 stylish feature-tag overlays (bold rounded pill labels, warm vibrant accent tints, compact pop-up badge typography) with short plain-English words like “100 speeds” or “Tilt airflow”. These must not be subtitles, sentence captions, transcripts, lower thirds, karaoke text, platform UI, social media icons, logos, reaction icons, camera icons, or watermarks.
- For 8-second VEO clips, the spoken copy must be written to finish naturally inside 8 seconds at normal creator pace, not merely shortened arbitrarily.
- Keep 8-second native voiceover at normal spoken pace: target 14–18 English words total, hard maximum 20 words, and no more than 3 short lines. Avoid unfinished trailing phrases such as “set and...”. Do not repeat the same spoken line across multiple storyboard beats, and explicitly forbid extra filler/CTA beyond the scripted lines.
- A proof/result moment showing the product creating the advertised benefit or a safe buyer-perceived version of that benefit.
- A final sell shot where the viewer understands the improved outcome, not merely a product-in-hand beauty shot.
- Product-fidelity block: “Use the provided product reference as the canonical source. Do not redesign, recolor, simplify, enlarge logos, change flower/gourd/cat silhouette, or invent extra parts.”
- Negative constraints: no fake claims, no impossible effects, no unrelated accessories, no distorted product geometry.
- `reference_scope`: a short note that says which parts of source images are product identity locks and which parts are free to reinterpret as lifestyle scene design.
- `scene_imagination`: a realistic scene derived from product function and buyer use case; it may differ from the product photos when functionally appropriate.

Actual VEO `video_prompt` should be a conservative usage demo:

- Treat the generated pad image / first frame as the visual identity lock.
- Show one simple real-world use action supported by `product_brief.json`, but organize the clip around the buyer-visible effect.
- Prefer start/end keyframes for 8-second usage videos: start = hook/problem setup, end = believable improved outcome / proof / sell shot.
- For wearable products such as collars, rings, braces, or pillows, the start frame should show the real pre-use context and the product about to be used; the end frame should show the same subject wearing/using it correctly. Static product-photo pads are not acceptable for functional usage videos.
- Start/end keyframes should be meaningfully different enough to imply an 8-second action arc, while keeping the exact same product identity. Avoid nearly identical start/end frames unless the goal is a stable b-roll shot.
- Start and end keyframes should usually stay in the same room, with the same subject identity, wardrobe, props, lighting, and camera setup; the end frame should feel like a few seconds later in the same moment, not a different shoot.
- Prefer generating the end keyframe from the already-generated start keyframe plus canonical product references, so the person and scene stay continuous while the action advances.
- When two keyframes exist, VEO receives both as `input_reference`; image 1 is the first frame and image 2 is the final frame.
- Allow adult hands and kitchen/sink/tabletop context when needed for a useful demo.
- Describe the buyer problem, product intervention, after-state, proof moment, and camera style. Keep product-identity constraints concise so they do not drown out the selling idea.
- Do not ask VEO to add new product parts, mechanisms, labels, containers, chambers, hinges, buttons, reservoirs, or unsupported accessories. Do not pile on generic negative constraints unrelated to this product; use only the few risks that matter.
- Keep detailed UGC dialogue, product explanation, and usage logic in `dialogue_script`, `function_intro_prompt`, `voiceover_script_8s`, `usage_logic`, and `shot_plan` for planning/editing context. The final VEO prompt is always `video_prompt`.
- Use a single `storyboard_8s` as the source of truth for each variant. Each beat should include `time`, `visual`, `spoken`, and optional `overlay`. `video_prompt` should include the full storyboard, `start_frame_prompt` should depict the first beat, and `end_frame_prompt` should depict the final beat. Overlay labels must be sparse feature tags only, never subtitles or repeated spoken text.
- `start_frame_prompt` and `end_frame_prompt` are still-image prompts, not planning prompts. They must request one single vertical 9:16 realistic photo for the chosen beat only. Do not include the full storyboard, timeline, multiple beats, “first vs final” wording, contact sheet language, multi-panel language, collage/grid wording, or colorway-range phrases such as “five prints” / “multi-colorway”. Keep only the current frame description, product identity constraints, reference-image scope, and same-scene continuity requirements.
- The start keyframe is generated first from canonical product references. The end keyframe should usually be generated from the start keyframe plus canonical product references, so the same outlet/table/person/room/camera carries through while only the action result advances. The end frame must not independently invent a different room, wall socket, phone orientation, person, wardrobe, or product state.
- In `storyboard_8s`, assign each spoken line to only one beat. Other beats should have no new spoken words rather than repeating the previous line, otherwise VEO may over-speak and cut off the ending.
- Do not let start/end keyframes be generic “before/after” images. They must correspond to the first and final storyboard beats, with a visible action-state change while preserving the same product identity, subject, room, wardrobe, lighting, and continuity.
- Voiceover and visuals must pass the benefit test: with sound on, the spoken line names the buyer problem/desire and the product-created result; with sound off, the first and final frames still show a believable before/after or need/payoff arc.
- `on_screen_callouts` may contain short feature tags such as “Fast Setup”, “Water Resistant”, or “Foldable Stand”. For VEO, prefer short plain-English words, 1–3 words per label, max 18 characters, rendered as stylish short-form creator typography (bold rounded pill badges, warm vibrant accent tints, compact pop-up labels) — but never platform/app/action icons, camera/reel icons, reaction icons, or UI chrome. If clean stylish text is uncertain, skip overlay rather than produce ugly or garbled text. Emoji may be stored for later manual editing only; do not send emoji into VEO overlay instructions.
- Never ask image or video models to render any social media or platform logos/icons, app icons, story frames, platform UI chrome, like/comment/share bars, camera/reel icons, subtitles, captions, transcript text, lower thirds, karaoke text, or watermarks. Avoid positive platform-branded style phrases in generation prompts; say "stylish short-form creator-ad energy" instead. If VEO overlays are used, they must be stylish short-form feature-tag typography only (bold pill labels, warm vibrant tints), never platform branding.

Every UGC variant must be grounded in `product_brief.json`:

- Use `confirmed_selling_points`, product-page `selling_points`, and the product title to identify the main buyer reason to care before choosing a scene.
- Use `step_by_step_usage` and `confirmed_use_cases` as the truth source for product operation.
- Use `misuse_risks_to_avoid` to prevent wrong demonstrations.
- Use `reference_image_strategy` plus `image_analysis.json` to choose full-product reference images for Image 2.
- Prefer explicit `canonical_reference_images` / `full_product_reference_images` in `product_brief.json` when present, and exclude `alternate_sku_reference_images`, `rejected_reference_images`, `non_canonical_reference_images`, and `avoid_reference_images`.
- The canonical reference must show the true product full silhouette, correct SKU/style, real proportions, and key functional zones. Do not use accessory-only, packaging-only, loose parts, alternate colorway/SKU, or detail-only photos as the identity reference.
- Do not let the reference image over-constrain the lifestyle scene. Once the correct product identity and usage mechanics are locked, expand the scene to realistic buyer contexts that make the function easier to understand.
- For each variant, map one selling point to one buyer problem, one usage action, one proof/result moment, and one final improved after-state. If several functions exist, split them across variants rather than cramming them into the same clip.
- If usage is uncertain, write a conservative tabletop/hand demo rather than inventing a dramatic function.

## LaoZhang API Notes

Read `references/laozhang-api-notes.md` before changing API calls. Key defaults:

- Base URL: `https://api.laozhang.ai/v1`
- API key env var: `LAOZHANG_API_KEY`
- GPT-Image-2 reverse routes: `/images/generations`, `/images/edits`, or `/chat/completions`.
- Use `gpt-image-2-vip` for common explicit sizes; avoid unsupported 4K sizes on VIP.
- VEO 3.1 async endpoint: `POST /videos`, poll `GET /videos/{id}`, then download via `GET /videos/{id}/content`.
- Use VEO models with `-fl` suffix for image-to-video reference frames.

## MiniMax API Notes

MiniMax can be used as a backup vision/chat provider when LaoZhang vision endpoints fail.

Key defaults:

- Base URL: `https://api.minimaxi.com/v1`
- Common model: `MiniMax-M3`
- The current scripts are OpenAI-compatible and can call MiniMax by passing `--model MiniMax-M3 --base-url https://api.minimaxi.com/v1`.
- MiniMax may return JSON inside `<think>...</think>` blocks or fenced ```json code blocks. The JSON parsers in `analyze_materials.py`, `build_product_brief.py`, and `generate_ugc_prompts.py` strip those wrappers before parsing.
- The legacy `https://api.minimax.io` host may not accept newer `sk-cp-...` keys; prefer `https://api.minimaxi.com/v1` for these keys.

## LK888 / updrama API Notes

Use `scripts/generate_videos_lk888.py` only when LK888/updrama is the requested provider or LaoZhang VEO is unavailable.

Key defaults:

- Base URL: `https://api.lk888.ai/api`
- API key env var: `LK888_API_KEY`
- Capability refresh endpoints: `GET /v1/skills`, `GET /v1/skills/guide`, and `GET /v1/skills/models/{model_name}`.
- Balance endpoint: `GET /v1/skills/balance`; query it before paid batches when practical.
- Media creation endpoint: `POST /v1/media/generate`; poll `GET /v1/skills/task-status?task_id={task_id}` until `is_final=true`.
- VEO 3.1 model name: `veo3.1`; common params are `generation_mode=fast`, `aspect_ratio=9:16`, `images=[start_url,end_url]`, and `enhance_prompt=false`.
- Gemini Omni Flash video model name: `omni-flash`; use the updrama media endpoint with `base_url=https://api.lk888.ai`, create path `/v1/media/generate`, status path `/v1/media/status`, `duration=8`, `aspect_ratio=9:16`, `images=[start_url,end_url]`, and `enhance_prompt=false`. It is a video/media model, not a chat prompt-writing model.
- `veo3.1-lite` uses `quality=sd|4k` instead of `generation_mode`, but may have inactive channels; verify pricing/status before relying on it.
- Upload params require publicly reachable URLs. The API does not accept local file paths or multipart image uploads for `images`.
- The adapter writes LK888 outputs to `videos_lk888/` so LaoZhang outputs in `videos/` remain untouched.
- If an API behavior contradicts the capability docs, submit `POST /v1/skills/feedback` and record the returned `feedback_id`.

## Quality Gate

Before delivering outputs, inspect `materials.md`, `image_analysis.json`, and `ugc_prompts.json` for each product:

- Reject image prompts that do not preserve the exact product form.
- Reject VEO prompts that redesign the product, invent mechanisms, or introduce unsupported actions.
- Reject prompts that imply social media/platform icons, logos, app UI, story stickers, like/comment/share chrome, camera/reel icons, watermark overlays, subtitles, captions, transcript text, lower thirds, karaoke text, or VEO-rendered emoji text. Allow only sparse stylish feature-tag overlay words (bold pill labels, warm vibrant tints) that evoke short-form creator energy without platform branding.
- Reject prompts that use a weak reference image when a cleaner product image exists.
- Prefer close-up product photos as image references over lifestyle images.
- Reject batches where the variants only differ cosmetically but repeat the same scene, camera angle, action, and proof moment.
- Reject keyframes that copy the original source-photo environment without a functional reason; scene design should come from buyer context and selling angle.
- Reject start/end keyframes that are too similar to produce a meaningful 8-second product-use video, unless the variant is explicitly stable b-roll.
- Before calling Image 2, manually or programmatically verify the selected reference images are the correct product, not another SKU on the same page.
- Image prompts must explicitly say the first selected full-product reference is canonical and conflicting page images should be ignored.
- For Image 2 edits, pass multiple verified full-product references when available, with the first image as the canonical product identity lock.
- If generated images drift from the original product, prefer `generate_images.py --compose-only` with the cleanest reference asset over asking the image model to redraw the product.

## Defaults

- Scraping: use JSON-LD `Product.image` assets first and exclude generic page images by default. Add `--include-page-images` only when product pages lack structured product images.
- Vision analysis: analyze the first 6 filtered product images by default. Use `--limit-images 0` to analyze all filtered images, or `--limit-images 2` for cheap quick tests.
- Prompt generation: read `product_brief.json` when present; if missing, fall back to manifest + image analysis but treat that as lower confidence.
- Prompt generation: default model is `gpt-5.2`; override with `--model`, `--prompt-model`, or `PRODUCT_UGC_PROMPT_MODEL` when a specific provider/model such as `omni-flash` is available in the active API channel.
- Prompt generation: do not use LK888 media/video models as prompt writers. For small ad-hoc rerolls where Codex has enough product context, Codex may directly author and append/rewrite variants in `ugc_prompts.json`; record this in `prompt_history` with a manual rewrite note.
- Prompt generation: prefer direct Codex-authored prompts instead of calling an external chat model when any of these are true: the user has given a clear creative direction, the product has already been analyzed in this thread, previous model prompts missed the selling point, the task is a small reroll for one known product, or external prompt models are timing out / returning malformed JSON. This is not a dry-run fallback; it is the canonical creative-planning path. Codex must still ground the prompts in `product_manifest.json`, `image_analysis.json`, `product_brief.json`, and prior `ugc_prompts.json`, then append a `prompt_history` entry describing why direct authoring was used.
- Prompt generation: use history-aware mode by default. `generate_ugc_prompts.py` passes the full prior `ugc_prompts*.json` history into the model context so the model can directly avoid repeating older scenes, actions, proof moments, buyer contexts, and selling angles.

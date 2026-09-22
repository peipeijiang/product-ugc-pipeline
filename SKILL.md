---
name: product-ugc-pipeline
description: Build product-faithful short-form UGC ads from ecommerce product URLs. Use for source-complete product research, product cognition, creative routing, Omni Flash chronological storyboard references, omni-reference video generation, and QC.
---

# Product UGC Pipeline

## Production contract

All production video generation uses LK888/upDrama Omni Flash in `omni-reference` mode.

- Default model: `omni-flash`.
- Optional fixed-duration route: `omni_flash-10s`.
- Reference mode: always `omni-reference`.
- Video aspect ratio: always `9:16` unless the user explicitly requests another format.
- Video references are all-purpose references, never timeline endpoints.
- Reference order is: chronological storyboard, verified product identity grid, then optional QC-passed operation grid.
- `omni-flash` accepts at most three references. Reject excess references before paid submission.
- Do not silently switch to another video model or provider.

The chronological storyboard is one reference sheet with a layout derived from the panel count and target frame ratio that contains the full 0–10 second progression in clearly ordered panels. It replaces separate scene endpoint assets. The storyboard controls sequence and scene continuity; the identity grid controls exact SKU appearance; the optional operation grid controls only source-supported configuration changes.

## Storyboard contract

Follow PostPlus storyboard-grid-writer: a short common prompt and detailed visible events per panel. Use exactly **6 panels (3 columns × 2 rows)** by default, or **9 panels (3 × 3)** when dense action or proof needs additional continuity. Read left-to-right, then top-to-bottom.

Keep `targetFrameAspectRatio` separate from `boardLayoutRatio`. Each panel uses the requested video ratio (`target_frame_aspect_ratio`, default 9:16); the board ratio is `(columns × frame width):(rows × frame height)`. Thus 9:16 footage uses a 27:32 six-panel board or a 9:16 nine-panel board. Never force every board to 9:16 or distort the panels to fit a fixed canvas.

`storyboard_10s` is the single source of truth for image and video visual descriptions. Each panel must specify its contiguous time interval, camera position, subject placement, visible action, environment anchors and spoken line. Preserve product reveal timing and supported physical states. Do not replace it with a separately rewritten shot plan, truncate nine panels to six, or invent filler panels in the renderer. Rewrite legacy non-6/9 timelines before rendering.

Persist `grid_spec` in image provenance. QC must verify the exact panel count, ratios, chronological order and each panel against the corresponding visual description. QC writes both the stage report and `qc/storyboards/variant-XX-storyboard.json`, including observed panel count, visual alignment, layout agreement and per-panel evidence. Missing observations never pass. Changes to timeline or layout invalidate the storyboard and its review. Video submission rebuilds its visual sequence from this reviewed timeline; oversized prompts must be revised, never truncated. One product per panel permits the same product to appear across multiple panels.

## Core rule

Preserve the real product above all else. Product references lock silhouette, proportions, material, color, mechanisms, labels and supported use. They do not lock the source-photo background, props or composition unless those elements are functionally necessary.

Never invent dimensions, functions, product parts, lighting, screens, indicators, accessories or state changes. Unknown facts must remain unknown.

## Market and spoken language

The target market is a required input, not an assumption. Spoken language, creator casting and scene framing must match the market the user asked for.

- Resolve the market from the product brief, the market profile, the prompt batch or an explicit `--market` / `--voice-locale` flag.
- Persist the resolved `market` and `voice_locale` at the top level of `ugc_prompts.json` and on every variant.
- Precedence is: `variant.voice_locale` → explicit CLI flag → `prompts.voice_locale` → declared market.
- An unresolved or misspelled locale is a hard failure before any paid step. There is no English default.
- Every spoken line must be written in the target language and pass the language gate. A Japanese-market batch with English copy fails before video submission.
- Prefer a visual-only clip plus target-language text-to-speech in post over a mixed-language or language-mismatched clip.

Supported locales live in `scripts/voice_locale.py`. Add a locale there instead of letting an unknown value fall back to English.

## Required workflow

1. Put product URLs in a text file, one URL per line.
2. Extract the complete offer asset set with `scripts/scrape_products.py` or the authenticated browser route required by the page.
3. Analyze every downloaded image and write `image_analysis.json`.
4. Build `product_brief.json` with `scripts/build_product_brief.py`.
5. Classify the product with `scripts/classify_product_category.py`.
6. Generate one product identity grid with `scripts/generate_product_identity_lock.py`.
7. Generate the source-backed usage ledger with `scripts/generate_usage_pose_sheet.py`. Products that fold, assemble, install, attach, extend, open or otherwise change configuration also require an operation grid.
8. Run identity and operation-grid QC with `scripts/qc_dual_consistency.py`.
9. Generate UGC variants with `scripts/generate_ugc_prompts.py --target-video-model omni-flash`.
10. Generate one chronological storyboard sheet per variant with `scripts/generate_images.py --storyboards`.
11. Run storyboard QC. Never submit a paid video from a missing, stale or failed storyboard.
12. Submit videos with `scripts/generate_videos_lk888.py --model omni-flash --reference-mode omni-reference`.
13. Run sampled-frame video QC and report any uncertainty honestly.

For fresh rerolls, use `scripts/run_fresh_batch.py`. It appends history-aware prompts, generates new storyboards, and submits Omni videos through the same fixed route.

## Browser routing

Pages that depend on login state, cookies, membership, age verification, account context or region context must use the user's authenticated browser session first. TikTok Shop PDPs are presumed session- and region-sensitive. Do not begin with unauthenticated static scraping for those pages.

If the page presents a login, CAPTCHA or device confirmation, stop and hand control to the user. Never bypass authentication.

For TikTok Shop, treat the live Next.js `loaderData` product payload as the authoritative asset list. Parse gallery images, SKU images, description images and videos; use the DOM only as a cross-check.

## Source completeness gate

Before product cognition, download every product-related main-gallery image, SKU/colorway image, detail-description image, installed/use image, packaging image and product-video poster exposed by the live offer. Preserve source URL and source surface in `product_manifest.json`.

The analyzed local-path set must cover the manifest image set exactly. Partial visual analysis is a hard failure. A single image is acceptable only when the live offer truly contains one usable product image, and that limitation must be recorded.

## Reference contract

For each variant, the production reference set is:

1. `generated_images/variant-XX-storyboard.png` — chronological action, creator, room, wardrobe, camera and pacing.
2. `identity_lock/reference_sheet.png` — canonical SKU identity and physical truth.
3. Optional operation grid — only for a source-supported state change that passed QC and is allowed by the risk route.

The storyboard provenance must include `type=chronological_storyboard` and a current timeline hash. Video submission must verify provenance, hashes and QC before uploading.

Never submit raw product photos alone as video references. Raw photos are inputs to the reference-generation and identity-lock steps.

## Creative routing

Run `scripts/creative_risk_router.py` before prompt finalization. Prefer the lowest-risk useful proof:

- stable ready-state product use;
- one simple supported interaction;
- detail or result proof;
- creator reaction and buyer-visible payoff.

When installation, assembly, folding, insertion or other topology change lacks direct motion evidence, keep the product in one verified ready-to-use configuration. Communicate setup through editing or real footage, not model-invented interpolation.

Each variant must differ materially in hook archetype, buyer context, creator persona, scene geometry, proof moment, camera grammar and pacing. Cosmetic wording changes do not count as new concepts.

## Prompt contract

Every variant must include:

- one core selling claim;
- buyer problem or desire;
- one supported product intervention;
- buyer-visible result;
- 0–10 second `storyboard_10s` beats;
- benefit-led voiceover that can finish naturally within ten seconds;
- exact product-fidelity constraints;
- a low-risk proof moment;
- a video prompt written specifically for Omni Flash all-purpose references.

The video prompt must explain that the storyboard, identity grid and optional operation grid are all-purpose references. It must not assign any reference image to a specific timeline endpoint.

Avoid subtitles, transcript text, platform logos, app UI, social icons, watermarks and invented product branding. Sparse short feature tags are allowed only when clean text generation is credible; otherwise omit them.

## Fail-fast rules

Stop before paid submission when any of these is true:

- product extraction is incomplete;
- image analysis has missing or failed files;
- product cognition lacks identity, use, function or misuse constraints;
- the target market or spoken locale is undeclared, unresolvable, or disagrees with the written voiceover;
- identity or operation QC is missing, stale or uncertain;
- storyboard is missing, stale, not chronological or failed QC;
- reference count exceeds the model limit;
- aspect ratio is not the requested format;
- the API route, model or reference mode differs from this contract;
- balance, channel availability or provider status is insufficient.

Do not fabricate JSON outputs or manually mark QC as passed to keep a batch moving.

## Quick commands

```bash
python scripts/scrape_products.py urls.txt --out product-ugc-output
LAOZHANG_API_KEY=sk-... python scripts/analyze_materials.py product-ugc-output --limit-images 0
LAOZHANG_API_KEY=sk-... python scripts/build_product_brief.py product-ugc-output
python scripts/classify_product_category.py product-ugc-output
LK888_API_KEY=sk-... python scripts/generate_product_identity_lock.py product-ugc-output
python scripts/generate_usage_pose_sheet.py product-ugc-output
LAOZHANG_API_KEY=sk-... python scripts/qc_dual_consistency.py product-ugc-output --stage identity
LAOZHANG_API_KEY=sk-... python scripts/generate_ugc_prompts.py product-ugc-output --count 10 --target-video-model omni-flash --market Japan
LK888_API_KEY=sk-... python scripts/generate_images.py product-ugc-output --variants 1-10 --storyboards
LK888_API_KEY=sk-... python scripts/generate_videos_lk888.py product-ugc-output --variants 1-10 --model omni-flash --base-url https://api.lk888.ai --status-endpoint /v1/media/status --reference-mode omni-reference
```

## Provider defaults

Image steps default to upDrama/LK888 `tt-image-2.5`. The automatic image fallback chain is `tt-image-2.5` → `tt-image-2` → the OpenAI-compatible GPT-Image-2 route. Record the actual provider, parameters and hashes in provenance.

Video steps use `POST https://api.lk888.ai/v1/media/generate` and poll `GET /v1/media/status?task_id=...`. The adapter writes results to `videos_lk888/` and records the exact model, reference mode, parameters and task response.

## Quality gate

Before delivery, verify:

- the product is the correct SKU in every storyboard panel and sampled video frame;
- silhouette, color, texture, part count and mechanisms remain stable;
- one physical product appears per panel unless the concept genuinely requires more;
- the action and payoff match source-backed usage;
- the creator, wardrobe, room and lighting remain coherent;
- phone orientation and other physical geometry are possible;
- no unsupported claims, magical changes, duplicate products, garbled text or platform UI appear;
- the batch concepts are genuinely distinct.

QC returns pass, fail, needs_review or error with evidence. Missing evidence and uncertain checks are never a pass. Video QC is sampled-frame review, not exhaustive motion or audio validation.

## Classification

Use four layers: catalog path, reusable visual family, cross-category physical traits and interaction modes. Add a trait when a physical/QC rule crosses categories. Add a new production family only when existing layouts and QC needs are structurally unsuitable. Unknown products use `general-merchandise` and require review.

Read the matching category and trait references in `references/`, especially `references/state-change-products.md`, `references/product-taxonomy.md`, `references/category-universal.md` and `references/low-risk-video-direction.md`.

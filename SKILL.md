---
name: product-ugc-pipeline
description: Build product-faithful short-form UGC ads from ecommerce product URLs. Use for source-complete product research, product cognition, creative routing, Omni Flash chronological storyboard references, omni-reference video generation, and QC.
---

# Product UGC Pipeline

## Production contract

The following standalone Omni production contract does not apply when this skill is invoked in product-intake mode by `ad-muse`; that caller owns backend selection, planning images and submission.

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

Keep `targetFrameAspectRatio` separate from `boardLayoutRatio`. Every production panel is 9:16. The mathematical six-panel board is **1620×1920**: 3×2 cells, each **540×960**, whole-board ratio 27:32; the mathematical nine-panel board is **1080×1920**: 3×3 cells, each **360×640**, whole-board ratio 9:16. If the image provider does not support 27:32, send the nearest supported media-task ratio, preserve the 9:16 panel instruction in the prompt, and record both mathematical and provider ratios in provenance. Do not stretch or claim the provider canvas is 27:32 when it is not.

`storyboard_10s` is the single source of truth for image and video visual descriptions. Each panel must specify its contiguous time interval, camera position, subject placement, visible action, environment anchors and spoken line. Preserve product reveal timing and supported physical states. Do not replace it with a separately rewritten shot plan, truncate nine panels to six, or invent filler panels in the renderer. Rewrite legacy non-6/9 timelines before rendering.

Keep panel content and board layout in separate layers. A `storyboard_10s[*].visual` describes only what appears inside that shot; it must never contain `3x2`/`3x3`, grid, contact-sheet, storyboard-sheet, panel-number, border, gutter, collage, split-screen or other board-layout instructions. The image renderer alone adds the 3×2 or 3×3 arrangement. Use edge-to-edge equal panels with only hairline-thin neutral separators and no panel numbers, labels, title bands, timestamps, outer frame or large blank margins.

The video adapter must rebuild exactly 6 or 9 chronological beats from the same layout-free timeline and state that the storyboard is a planning map only. Final video output is always one full-screen moving image at each moment: never reproduce the reference board, gutters, borders, numbering, contact-sheet composition, split screen, collage, picture-in-picture or simultaneous panels. Board-layout vocabulary found in a panel visual is a hard failure before paid submission.

Choose the panel count from the authored story before image generation. Use 9 panels when the story needs more than six distinct visible events, or when multiple time/location transitions plus product action, proof and payoff would otherwise be compressed; otherwise use 6. Persist `storyboard_panel_count` (`6|9`) and a concise `storyboard_density_reason` on every variant. The declared count, `storyboard_10s` length and rendered grid must agree. Risk routing may constrain unsafe product motion, but it must never replace the authored story with a generic six-panel template or reduce a nine-panel story to six.

The identity grid and optional operation grid are supporting references, not chronological storyboards; their panel counts may differ from 6/9. Never describe them to the user as completed storyboards. A storyboard is ready only when `generated_images/variant-XX-storyboard.png` exists, its provenance is bound to the current `storyboard_10s`, and storyboard QC passes.

Persist `grid_spec` in image provenance. QC must verify the exact panel count, ratios, chronological order and each panel against the corresponding visual description. QC writes both the stage report and `qc/storyboards/variant-XX-storyboard.json`, including observed panel count, visual alignment, layout agreement and per-panel evidence. Missing observations never pass. Changes to timeline or layout invalidate the storyboard and its review. Video submission rebuilds its visual sequence from this reviewed timeline; the beat count must equal `storyboard_panel_count`, and prompt QC must confirm that no board-layout instruction leaked into those beats. Oversized prompts must be revised, never truncated. One product per panel permits the same product to appear across multiple panels.

## Core rule

Preserve the real product above all else. Product references lock silhouette, proportions, material, color, mechanisms, labels and supported use. They do not lock the source-photo background, props or composition unless those elements are functionally necessary.

Never invent dimensions, functions, product parts, lighting, screens, indicators, accessories or state changes. Unknown facts must remain unknown.

## Invocation modes

When called by `$ad-muse`, run **product-intake mode only**. Complete source extraction, full asset manifest, image analysis, product brief/taxonomy, canonical product references and intake QC; generate identity images only when verified original images are insufficient, per the caller’s reference plan; then stop and hand off the documented artifacts. Do not run `generate_ugc_prompts.py`, storyboard generation, `generate_videos_lk888.py`, or the Omni Flash submission route in that mode.

The Omni Flash video route below remains available only when the user explicitly asks for an Omni Flash/omni-reference video or a legacy run is being resumed. The unified caller may also select Omni Flash, but it then owns prompt serialization and submission using its own canonical artifacts; do not run this standalone legacy chain under that caller.

## Market and spoken language

The target market is a required input, not an assumption. Spoken language, creator casting and scene framing must match the market the user asked for.

- Resolve the market from the product brief, the market profile, the prompt batch or an explicit `--market` / `--voice-locale` flag.
- Persist the resolved `market` and `voice_locale` at the top level of `ugc_prompts.json` and on every variant.
- Resolve once, then lock it for the entire batch. A variant locale or CLI locale that conflicts with the declared country is a hard failure, not an override.
- Persist a canonical `creator_market_identity` on every variant. Creator nationality/market identity, casting, wardrobe, gestures, home details and social context must remain consistent with that country from storyboard through video.
- An unresolved or misspelled locale is a hard failure before any paid step. There is no English default.
- Every spoken surface must be written in the target language and pass the language gate independently: `dialogue_script`, all `voiceover_script_10s` lines, every storyboard `spoken`/`spoken_line`, narration and final oral delivery. One correct line may not mask another wrong-language line. A Japanese-market batch with any English spoken line fails before video submission.
- Prefer a visual-only clip plus target-language text-to-speech in post over a mixed-language or language-mismatched clip.

Supported locales live in `scripts/voice_locale.py`. Add a locale there instead of letting an unknown value fall back to English.

## Agent-native vision

Product-image analysis, the product brief, the UGC prompt batch and image QC are done by the multimodal model already running this agent. No external vision or chat API and no API key are used for these steps.

Each step is two passes of the same command:

1. The script writes a task file listing the exact local images (with SHA-256), the instructions and the required JSON fields, then exits with code 3 (`agent-review-pending`).
2. Open every listed image yourself, write the answer file next to the task and copy the task's `task_sha256` into it.
3. Rerun the command. It validates full coverage, enums and evidence, then writes the final artifact.

| Step | Task | Answer | Final artifact |
|---|---|---|---|
| Per-image analysis | `analysis/image_analysis.task.json` | `analysis/image_analysis.answer.json` | `image_analysis.json`, `materials.md` |
| Product brief | `analysis/product_brief.task.json` | `analysis/product_brief.answer.json` | `product_brief.json` |
| UGC prompt batch | `analysis/ugc_prompts/<output-stem>.task.json` | `analysis/ugc_prompts/<output-stem>.answer.json` | `ugc_prompts.json` |
| Identity/usage/storyboard/video QC | `qc/agent/<stage>/<target>/task.json` | `qc/agent/<stage>/<target>/answer.json` | `qc/<stage>.json` |

Describe only what is visible in the images. A missing, partial or stale answer (wrong `task_sha256`) never passes. Never write an answer without actually looking at every listed image.

## Required workflow

1. Put product URLs in a text file, one URL per line.
2. Extract the complete offer asset set with `scripts/scrape_products.py` or the authenticated browser route required by the page.
3. Analyze every downloaded image yourself with `scripts/analyze_materials.py` (agent-native vision) and finalize `image_analysis.json`.
4. Write and finalize `product_brief.json` with `scripts/build_product_brief.py` (agent-native).
5. Classify the product with `scripts/classify_product_category.py`.
6. Generate one product identity grid with `scripts/generate_product_identity_lock.py`.
7. Generate the source-backed usage ledger with `scripts/generate_usage_pose_sheet.py`. Products that fold, assemble, install, attach, extend, open or otherwise change configuration also require an operation grid.
8. Run identity and operation-grid QC with `scripts/qc_dual_consistency.py` (agent-native review).
9. Write UGC variants with `scripts/generate_ugc_prompts.py --target-video-model omni-flash` (agent-native: the task carries the full system and user prompt; answer it yourself).
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
python scripts/analyze_materials.py product-ugc-output      # writes task → agent answers → rerun
python scripts/build_product_brief.py product-ugc-output    # writes task → agent answers → rerun
python scripts/classify_product_category.py product-ugc-output
LK888_API_KEY=sk-... python scripts/generate_product_identity_lock.py product-ugc-output
python scripts/generate_usage_pose_sheet.py product-ugc-output
python scripts/qc_dual_consistency.py product-ugc-output --stage identity   # agent-native review
python scripts/generate_ugc_prompts.py product-ugc-output --count 10 --target-video-model omni-flash --market Japan   # writes task → agent answers → rerun
LK888_API_KEY=sk-... python scripts/generate_images.py product-ugc-output --variants 1-10 --storyboards
LK888_API_KEY=sk-... python scripts/generate_videos_lk888.py product-ugc-output --variants 1-10 --model omni-flash --base-url https://api.lk888.ai --status-endpoint /v1/media/status --reference-mode omni-reference
```

## Provider defaults

Image steps use only the upDrama/LK888 media-task route: `tt-image-2.5` by default, with `tt-image-2` as the single automatic fallback (`--image-fallback none` disables it). Record the actual provider, parameters and hashes in provenance.

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

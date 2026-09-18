# Product UGC Pipeline

A product-faithful ecommerce UGC pipeline for complete source extraction, visual cognition, identity locking, creative risk routing, chronological storyboard references, Omni Flash video generation, and QC.

## Single production video route

- Model: `omni-flash` or `omni_flash-10s`
- Provider: LK888/upDrama
- Reference mode: always `omni-reference`
- Reference order: chronological storyboard, product identity grid, optional QC-passed operation grid
- Aspect ratio: `9:16` by default
- Spoken market: required (`--market Japan` or `--voice-locale ja-JP`); unresolved locales fail before any paid step instead of defaulting to English

All images are all-purpose references. Each variant creates one `generated_images/variant-XX-storyboard.png` containing the complete 0–10 second visual sequence.

```bash
LAOZHANG_API_KEY=sk-... python scripts/generate_ugc_prompts.py product-ugc-output --count 10 --target-video-model omni-flash --market Japan
LK888_API_KEY=sk-... python scripts/generate_images.py product-ugc-output --variants 1-10 --storyboards
LK888_API_KEY=sk-... python scripts/generate_videos_lk888.py product-ugc-output --variants 1-10 --model omni-flash --base-url https://api.lk888.ai --status-endpoint /v1/media/status --reference-mode omni-reference
```

See `SKILL.md` for the full production and fail-fast contract.

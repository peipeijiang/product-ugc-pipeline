# LaoZhang image and chat fallback notes

LaoZhang is used only by the legacy standalone prompt writer (`generate_ugc_prompts.py`) and the OpenAI-compatible image-generation fallback. It is not a video route, and it is never used for product-image analysis, the product brief or QC: those are done by the agent's own multimodal model (see "Agent-native vision" in SKILL.md).

## Base configuration

- Base URL: `https://api.laozhang.ai/v1`
- API key: `LAOZHANG_API_KEY`
- Chat endpoint: `/chat/completions`
- Image endpoints: `/images/generations` and `/images/edits`
- Common image model: `gpt-image-2-vip`

The normal image path is LK888/upDrama `tt-image-2.5`. The LaoZhang image endpoint is the final fallback after the media-task image routes fail. Record the actual provider and request parameters in provenance.

For image edits, send verified canonical product references only. Do not use alternate SKUs, packaging-only photos, loose accessories or unrelated detail crops as the primary identity source.

Video generation always uses the LK888/upDrama Omni Flash adapter in `omni-reference` mode.

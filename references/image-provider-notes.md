# Image Provider Notes

Reference for the image stage of the product UGC pipeline. Read this before
changing any image-generation call.

## Provider chain

`generate_images.py`, `generate_product_identity_lock.py` and
`generate_usage_pose_sheet.py` share one provider chain, configured through
`add_image_provider_arguments()`:

| Order | Provider flag | Route | Model |
|---|---|---|---|
| 1 | `tt-image-2.5` (default) | upDrama media task | `tt-image-2.5` |
| 2 | `tt-image-2` | upDrama media task | `tt-image-2` |
| 3 | `laozhang-image2` | OpenAI-compatible Images | `--model` (default `gpt-image-2-vip`) |

Steps 2 and 3 run automatically when step 1 raises. Pass
`--image-fallback none` to disable the chain and fail on the primary provider
alone. Each frame records `image_provider` and `provider_fallbacks` in
`generated_images/image_generation_results.json`.

## upDrama media-task route

```text
POST https://api.lk888.ai/v1/media/generate
GET  https://api.lk888.ai/v1/media/status?task_id={task_id}
```

Request body is exactly `model`, `prompt` and `params`. References go in
`params.images` as public URLs or `data:<mime>;base64,<data>` inline values;
`tt-image-2.5` accepts 1-16, some channels cap at 8.

Params used by the pipeline:

| Param | Value | Notes |
|---|---|---|
| `aspect_ratio` | `9:16` | Vertical product UGC. |
| `resolution` | `2K` | `auto` / `1K` / `2K` / `4K`. |
| `version` | `sunburst` | `flare` = standard, `sunburst` = enhanced detail. |
| `quality` | `high` | `auto`/`low`/`medium`/`high`/`xhigh`/`max`. |
| `background` | `opaque` | `transparent` forces PNG and narrows channel routing. |

Poll with `is_final === true` for the terminal state and `state` for
success/failure. `status` and `status_group` are Chinese display strings and
must not drive business logic. A failed task is refunded automatically.

To keep aspect ratio and resolution independent, do not also send `size`;
`size` is only for the fallback route.

## OpenAI-compatible fallback route

`POST /images/edits` with multipart files when references exist, otherwise
`POST /images/generations`. One reference uses the `image` field; two or more
must use `image[]`. Base URL defaults to `https://api.laozhang.ai/v1` and the
model to `gpt-image-2-vip`.

## Keys

`LK888_API_KEY` or `UPDRAMA_API_KEY` is required for the media route;
`LAOZHANG_API_KEY` for the fallback. `require_api_key_for_base_url()` picks
the right variable from the base URL, and all HTTP calls bypass system and
environment proxies on purpose.

## When both script routes are unavailable

An interactive Codex session may generate the frame with its own image tool and
save it to the expected path. The frame still has to record its provider, hash
and parameters, and still has to pass the same vision QC before any video
submission. Never skip QC because a different generator produced the frame.

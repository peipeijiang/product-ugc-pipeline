# LaoZhang API Notes

Sources checked on 2026-04-27:

- GPT Image 2: https://docs.laozhang.ai/en/api-capabilities/gpt-image-2
- VEO 3.1 Async: https://docs.laozhang.ai/en/api-capabilities/veo/veo-31-async-api

## Base

- Base URL: `https://api.laozhang.ai/v1`
- Auth: `Authorization: Bearer $LAOZHANG_API_KEY`
- Do not include model-specific paths in the base URL.

## GPT-Image-2

Route behavior depends on the token group:

- Default group `gpt-image-2`: reverse ChatGPT Web route, no `size` or `quality`.
- Default group `gpt-image-2-vip`: reverse Codex route, supports common `size`, no `quality`.
- `Sora2Official` group `gpt-image-2`: official-transit route, supports official `size` and `quality`.

Common `gpt-image-2-vip` sizes:

- `1024x1024`
- `1536x1024`
- `1024x1536`
- `2048x2048`
- `2048x1152`
- `auto`

Avoid `3840x2160` and `2160x3840` on `gpt-image-2-vip`.

Supported endpoint patterns:

- Text-to-image: `POST /images/generations`
- Image-to-image: `POST /images/edits` multipart with `image=@source.png`
- Default-group chat image route: `POST /chat/completions`; response image is often a Markdown image URL in `choices[0].message.content`

For product-fidelity pad images, prefer `/images/edits` with the cleanest downloaded product photo as `image`.

## VEO 3.1 Async

Endpoint:

- Create: `POST /videos`
- Poll: `GET /videos/{video_id}`
- Content: `GET /videos/{video_id}/content`

VEO 3.1 models:

- `veo-3.1`: portrait, text-to-video
- `veo-3.1-fl`: portrait, image-to-video
- `veo-3.1-fast`: portrait, text-to-video, cheaper/faster
- `veo-3.1-fast-fl`: portrait, image-to-video, cheaper/faster
- `veo-3.1-landscape`: landscape, text-to-video
- `veo-3.1-landscape-fl`: landscape, image-to-video
- `veo-3.1-landscape-fast`: landscape, text-to-video, cheaper/faster
- `veo-3.1-landscape-fast-fl`: landscape, image-to-video, cheaper/faster

For image-to-video, send multipart `input_reference` files. `-fl` models support one or two reference images; with two images, the first is the first frame and the second is the last frame.

Statuses:

- Continue polling: `queued`, `processing`, `in_progress`, `submitted`
- Complete: `completed`, then call `/videos/{id}/content`
- Stop/fail: `failed`, `cancelled`, `canceled`, `expired`

Video content may return JSON with a temporary MP4 URL. Download immediately; URLs may expire.

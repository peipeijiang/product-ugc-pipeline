#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.laozhang.ai/v1"


def slugify(value: str, fallback: str = "product") -> str:
    normalized = re.sub(r"[\s_]+", "-", value.strip().lower())
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff-]+", "", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized[:80] or fallback


def read_urls(path: Path) -> list[str]:
    urls: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        urls.append(stripped_line)
    return urls


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def product_dirs(output_dir: Path) -> list[Path]:
    folders = [folder for folder in output_dir.iterdir() if folder.is_dir() and re.match(r"^\d{2}-", folder.name)]
    return sorted(folders)


def selected_product_dirs(output_dir: Path, products: str = "") -> list[Path]:
    folders = product_dirs(output_dir)
    if not products.strip():
        return folders
    selectors = [selector.strip().lower() for selector in products.split(",") if selector.strip()]
    selected: list[Path] = []
    for folder in folders:
        folder_name = folder.name.lower()
        folder_index = folder.name.split("-", 1)[0]
        if any(folder_name.startswith(selector) or folder_index == selector.zfill(2) for selector in selectors):
            selected.append(folder)
    return selected


def user_agent() -> str:
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )


def http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: int = 60,
) -> tuple[int, dict[str, str], bytes]:
    try:
        import requests

        request_headers = {"User-Agent": user_agent()}
        if headers:
            request_headers.update(headers)
        response = requests.request(method, url, headers=request_headers, data=data, timeout=timeout)
        response.raise_for_status()
        return response.status_code, dict(response.headers.items()), response.content
    except ImportError:
        pass
    except Exception as error:
        if error.__class__.__name__ in {"HTTPError"} and getattr(error, "response", None) is not None:
            response = error.response
            body = response.content
            raise RuntimeError(f"HTTP {response.status_code} for {url}: {body[:1000].decode('utf-8', 'ignore')}") from error
        raise RuntimeError(f"Request failed for {url}: {error}") from error

    request_headers = {"User-Agent": user_agent()}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        body = error.read()
        raise RuntimeError(f"HTTP {error.code} for {url}: {body[:1000].decode('utf-8', 'ignore')}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Request failed for {url}: {error}") from error


def request_json(
    endpoint: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    method: str = "POST",
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 120,
) -> dict[str, Any]:
    url = endpoint if endpoint.startswith("http") else f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {"Authorization": f"Bearer {api_key}"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    _, _, body = http_request(url, method=method, headers=headers, data=data, timeout=timeout)
    return json.loads(body.decode("utf-8"))


def guess_mime(path: Path) -> str:
    guessed_mime, _ = mimetypes.guess_type(str(path))
    return guessed_mime or "application/octet-stream"


def data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{guess_mime(path)};base64,{encoded}"


def multipart_request(
    endpoint: str,
    api_key: str,
    fields: dict[str, str],
    files: list[tuple[str, Path]],
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 180,
) -> dict[str, Any]:
    boundary = f"----codex-product-ugc-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for field_name, field_value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(field_value).encode("utf-8"))
        chunks.append(b"\r\n")
    for field_name, file_path in files:
        mime_type = guess_mime(file_path)
        safe_name = file_path.name.replace('"', "")
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{field_name}"; filename="{safe_name}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(file_path.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    url = endpoint if endpoint.startswith("http") else f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    _, _, response_body = http_request(url, method="POST", headers=headers, data=body, timeout=timeout)
    return json.loads(response_body.decode("utf-8"))


def require_api_key() -> str:
    api_key = os.environ.get("LAOZHANG_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Missing LAOZHANG_API_KEY. Export it before running this script.")
    return api_key


def download_binary(url: str, destination: Path, timeout: int = 60) -> bool:
    try:
        _, headers, body = http_request(url, timeout=timeout)
    except RuntimeError as error:
        print(f"[warn] download failed: {url} ({error})")
        return False
    content_type = headers.get("Content-Type", "")
    if "text/html" in content_type and len(body) < 2000:
        print(f"[warn] skipped likely html asset: {url}")
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)
    return True


def image_quality_metadata(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image, ImageStat

        image = Image.open(path).convert("RGB")
        width, height = image.size
        stat = ImageStat.Stat(image)
        mean_brightness = sum(stat.mean) / 3
        mean_variance = sum(stat.var) / 3
        aspect_ratio = width / height if height else 0
        too_small = width < 320 or height < 320
        too_wide_or_flat = aspect_ratio > 2.4 or aspect_ratio < 0.35
        almost_blank = mean_variance < 25
        nearly_black = mean_brightness < 8
        usable = not (too_small or too_wide_or_flat or almost_blank or nearly_black)
        return {
            "width": width,
            "height": height,
            "aspect_ratio": round(aspect_ratio, 3),
            "mean_brightness": round(mean_brightness, 2),
            "mean_variance": round(mean_variance, 2),
            "usable_product_material": usable,
            "quality_reasons": {
                "too_small": too_small,
                "too_wide_or_flat": too_wide_or_flat,
                "almost_blank": almost_blank,
                "nearly_black": nearly_black,
            },
        }
    except Exception as error:
        return {"usable_product_material": True, "quality_error": str(error)}


def save_response_image(response: dict[str, Any], destination: Path) -> Path | None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    data_items = response.get("data") or []
    if data_items:
        first_item = data_items[0]
        base64_value = first_item.get("b64_json")
        if base64_value:
            if base64_value.startswith("data:"):
                base64_value = base64_value.split(",", 1)[1]
            destination.write_bytes(base64.b64decode(base64_value))
            return destination
        image_url = first_item.get("url")
        if image_url and download_binary(image_url, destination):
            return destination
    content = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    match = re.search(r"!\[[^\]]*]\((https?://[^)\s]+)\)", content)
    if not match:
        match = re.search(r"(https?://\S+\.(?:png|jpe?g|webp)(?:\?\S+)?)", content, flags=re.IGNORECASE)
    if match and download_binary(match.group(1), destination):
        return destination
    return None


def sleep_with_status(seconds: int, label: str) -> None:
    print(label, flush=True)
    time.sleep(seconds)

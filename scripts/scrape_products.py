#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from common import download_binary, http_request, image_quality_metadata, read_urls, slugify, write_json, write_text


class ProductHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.scripts: list[str] = []
        self._in_title = False
        self._in_script = False
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = attr_map.get("property") or attr_map.get("name")
            value = attr_map.get("content")
            if key and value:
                self.meta[key.lower()] = html.unescape(value)
        elif tag == "link":
            self.links.append(attr_map)
        elif tag == "img":
            self.images.append(attr_map)
        elif tag == "script":
            self._in_script = True
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_script = False
            script_text = "".join(self._script_parts).strip()
            if script_text:
                self.scripts.append(script_text)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif self._in_script:
            self._script_parts.append(data)


def first_present(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return html.unescape(value.strip())
    return ""


def clean_product_name(value: str, url: str) -> str:
    candidate = re.sub(r"\s*[|–—-]\s*Depth\s*Stores.*$", "", value, flags=re.IGNORECASE).strip()
    if candidate:
        return candidate
    slug = Path(urllib.parse.urlparse(url).path).name
    return slug.replace("-", " ").title()


def absolute_url(value: str, page_url: str) -> str:
    value = html.unescape(value.strip())
    if value.startswith("//"):
        return "https:" + value
    return urllib.parse.urljoin(page_url, value)


def parse_srcset(srcset: str, page_url: str) -> list[str]:
    urls: list[str] = []
    for item in srcset.split(","):
        candidate = item.strip().split(" ")[0]
        if candidate:
            urls.append(absolute_url(candidate, page_url))
    return urls


def canonical_image_key(image_url: str) -> str:
    parsed = urllib.parse.urlparse(image_url)
    path = re.sub(r"_(?:\d+x|\d+)\.(png|jpe?g|webp)$", r".\1", parsed.path, flags=re.IGNORECASE)
    return f"{parsed.netloc}{path}".lower()


def product_image_urls(product: dict[str, Any], page_url: str) -> list[str]:
    values: list[str] = []
    product_images = product.get("image")
    if isinstance(product_images, str):
        values.append(absolute_url(product_images, page_url))
    elif isinstance(product_images, list):
        for product_image in product_images:
            if isinstance(product_image, str):
                values.append(absolute_url(product_image, page_url))
    deduped: list[str] = []
    seen: set[str] = set()
    for image_url in values:
        key = canonical_image_key(image_url)
        if key not in seen:
            deduped.append(image_url)
            seen.add(key)
    return deduped


def collect_image_urls(
    parser: ProductHTMLParser,
    page_url: str,
    html_text: str,
    product: dict[str, Any],
    product_only: bool = True,
) -> list[dict[str, str]]:
    collected: dict[str, dict[str, str]] = {}
    seen_canonical: set[str] = set()

    def add_image(raw_url: str, source: str, alt: str = "") -> None:
        if not raw_url or raw_url.startswith("data:"):
            return
        image_url = absolute_url(raw_url, page_url)
        if not re.search(r"\.(?:png|jpe?g|webp)(?:[?#].*)?$", urllib.parse.urlparse(image_url).path, re.IGNORECASE):
            if "cdn" not in image_url and "image" not in image_url:
                return
        key = canonical_image_key(image_url)
        if key in seen_canonical:
            return
        seen_canonical.add(key)
        collected.setdefault(image_url, {"url": image_url, "source": source, "alt": alt})

    structured_product_images = product_image_urls(product, page_url)
    for product_image in structured_product_images:
        add_image(product_image, "json_ld_product_image")
    if product_only and structured_product_images:
        return list(collected.values())
    for key in ("og:image", "og:image:secure_url", "twitter:image"):
        add_image(parser.meta.get(key, ""), key)
    for image_attrs in parser.images:
        add_image(first_present(image_attrs.get("src"), image_attrs.get("data-src"), image_attrs.get("data-original")), "img", image_attrs.get("alt", ""))
        for srcset_key in ("srcset", "data-srcset"):
            for srcset_url in parse_srcset(image_attrs.get(srcset_key, ""), page_url):
                add_image(srcset_url, srcset_key, image_attrs.get("alt", ""))
    for match in re.finditer(r"https?:\\/\\/[^\"']+\.(?:png|jpe?g|webp)(?:\?[^\"']*)?", html_text):
        add_image(match.group(0).replace("\\/", "/"), "script-url")
    for match in re.finditer(r"(?:https?:)?//[^\"'\s]+\.(?:png|jpe?g|webp)(?:\?[^\"'\s]*)?", html_text):
        add_image(match.group(0), "html-url")
    return list(collected.values())


def description_sections(description: str) -> dict[str, str]:
    text = html.unescape(description or "")
    headings = [
        "Versatile Cleaning Tool",
        "Durable and Eco-Friendly Design",
        "Perfect for a Variety of Uses",
        "Easy to Use and Clean",
        "Key Features:",
    ]
    sections: dict[str, str] = {}
    current = "overview"
    buffer: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        matched_heading = next((heading for heading in headings if line.startswith(heading)), "")
        if matched_heading:
            if buffer:
                sections[current] = " ".join(buffer).strip()
            current = matched_heading.strip(":").lower().replace(" ", "_")
            remainder = line[len(matched_heading) :].strip()
            buffer = [remainder] if remainder else []
        else:
            buffer.append(line)
    if buffer:
        sections[current] = " ".join(buffer).strip()
    return sections


def extract_json_ld(parser: ProductHTMLParser) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for script_text in parser.scripts:
        stripped_text = script_text.strip()
        if not (stripped_text.startswith("{") or stripped_text.startswith("[")):
            continue
        try:
            parsed = json.loads(stripped_text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            records.extend(item for item in parsed if isinstance(item, dict))
        elif isinstance(parsed, dict):
            graph = parsed.get("@graph")
            if isinstance(graph, list):
                records.extend(item for item in graph if isinstance(item, dict))
            records.append(parsed)
    return records


def product_record(json_ld_records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in json_ld_records:
        record_type = record.get("@type")
        if record_type == "Product" or (isinstance(record_type, list) and "Product" in record_type):
            return record
    return {}


def extract_bullets(html_text: str) -> list[str]:
    banned = {
        "smart glasses",
        "ai smart ring",
        "mp3 player",
        "bluetooth speaker",
        "digital camera",
        "all products",
        "refund policy",
        "privacy policy",
        "terms of service",
        "contact us",
        "track order",
    }
    bullets: list[str] = []
    for match in re.finditer(r"<li[^>]*>(.*?)</li>", html_text, flags=re.IGNORECASE | re.DOTALL):
        text = re.sub(r"<[^>]+>", " ", match.group(1))
        text = html.unescape(re.sub(r"\s+", " ", text)).strip()
        if 8 <= len(text) <= 220 and text.lower() not in banned and text.lower() not in {"home", "catalog", "contact"}:
            bullets.append(text)
    deduped: list[str] = []
    for bullet in bullets:
        if bullet not in deduped:
            deduped.append(bullet)
    return deduped[:12]


def selling_points_from_description(description: str) -> list[str]:
    text = html.unescape(description or "")
    points: list[str] = []
    if "Key Features:" in text:
        text = text.split("Key Features:", 1)[1]
    for raw_line in text.splitlines():
        cleaned = re.sub(r"\s+", " ", raw_line).strip(" •-\t")
        if 10 <= len(cleaned) <= 180 and cleaned.lower() not in {"key features:"}:
            points.append(cleaned)
    deduped: list[str] = []
    for point in points:
        if point not in deduped:
            deduped.append(point)
    return deduped[:8]


def extension_for_url(image_url: str) -> str:
    suffix = Path(urllib.parse.urlparse(image_url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


def build_materials_md(manifest: dict[str, Any]) -> str:
    lines = [
        f"# {manifest['product_name']}",
        "",
        f"- Source URL: {manifest['source_url']}",
        f"- Price: {manifest.get('price') or 'Not detected'}",
        "",
        "## Core Selling Points",
        "",
    ]
    for index, point in enumerate(manifest.get("selling_points") or [], start=1):
        lines.append(f"{index}. {point}")
    if not manifest.get("selling_points"):
        lines.append("- Not detected from static HTML; use image/page analysis.")
    lines.extend(["", "## Product Description Sections", ""])
    for key, value in (manifest.get("description_sections") or {}).items():
        lines.append(f"### {key.replace('_', ' ').title()}")
        lines.append("")
        lines.append(value)
        lines.append("")
    lines.extend(["", "## Usage Signals From Page", ""])
    for index, signal in enumerate(manifest.get("usage_signals") or [], start=1):
        lines.append(f"{index}. {signal}")
    if not manifest.get("usage_signals"):
        lines.append("- Not detected from page text; rely on image analysis.")
    lines.extend(["", "## Downloaded Image Materials", ""])
    for image_item in manifest["images"]:
        lines.append(
            f"- `{image_item['local_path']}` — source={image_item['source']} alt={image_item.get('alt') or 'n/a'} url={image_item['url']}"
        )
    lines.extend(["", "## Image Understanding Log", "", "Run `analyze_materials.py` to fill `image_analysis.json`."])
    return "\n".join(lines) + "\n"


def usage_signals_from_text(description: str, selling_points: list[str]) -> list[str]:
    text = " ".join([description] + selling_points)
    sentences = re.split(r"(?<=[.!?。！？])\s+|\n+", html.unescape(text))
    usage_verbs = re.compile(r"\b(clean|wash|scrub|rinse|squeeze|press|open|hold|store|mince|crush|peel|cut|hang|drain|wipe)\b", re.IGNORECASE)
    signals: list[str] = []
    for sentence in sentences:
        cleaned = re.sub(r"\s+", " ", sentence).strip(" -•")
        if 12 <= len(cleaned) <= 240 and usage_verbs.search(cleaned):
            if cleaned not in signals:
                signals.append(cleaned)
    return signals[:10]


def scrape_product(index: int, url: str, output_dir: Path, max_images: int, image_timeout: int, include_page_images: bool) -> dict[str, Any]:
    print(f"[scrape] {index:02d} {url}", flush=True)
    _, _, body = http_request(url, timeout=60)
    html_text = body.decode("utf-8", "ignore")
    parser = ProductHTMLParser()
    parser.feed(html_text)
    json_ld_records = extract_json_ld(parser)
    product = product_record(json_ld_records)
    raw_name = first_present(
        str(product.get("name") or ""),
        parser.meta.get("og:title"),
        "".join(parser.title_parts),
    )
    product_name = clean_product_name(raw_name, url)
    folder = output_dir / f"{index:02d}-{slugify(product_name)}"
    images_dir = folder / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    image_records: list[dict[str, Any]] = []
    all_image_candidates = collect_image_urls(parser, url, html_text, product, product_only=not include_page_images)
    image_candidates = all_image_candidates[:max_images]
    for image_index, image_info in enumerate(image_candidates, start=1):
        image_url = image_info["url"]
        local_path = images_dir / f"{image_index:02d}{extension_for_url(image_url)}"
        print(f"[image] {index:02d}.{image_index:02d} {image_url}", flush=True)
        downloaded = download_binary(image_url, local_path, timeout=image_timeout)
        if downloaded:
            quality = image_quality_metadata(local_path)
            if not quality.get("usable_product_material", True):
                print(f"[skip-image] {index:02d}.{image_index:02d} unusable material {quality}", flush=True)
                local_path.unlink(missing_ok=True)
                continue
            image_records.append(
                {
                    "index": image_index,
                    "url": image_url,
                    "local_path": str(local_path.relative_to(folder)),
                    "source": image_info["source"],
                    "alt": image_info.get("alt", ""),
                    "quality": quality,
                }
            )
    offers = product.get("offers") if isinstance(product.get("offers"), dict) else {}
    price = first_present(str(offers.get("price") or ""), parser.meta.get("product:price:amount"))
    description = first_present(str(product.get("description") or ""), parser.meta.get("description"), parser.meta.get("og:description"))
    selling_points = selling_points_from_description(description)
    for bullet in extract_bullets(html_text):
        if bullet not in selling_points:
            selling_points.append(bullet)
    if description and description not in selling_points and len(description) <= 260:
        selling_points.insert(0, description[:260])
    sections = description_sections(description)
    usage_signals = usage_signals_from_text(description, selling_points)
    manifest = {
        "index": index,
        "source_url": url,
        "product_name": product_name,
        "slug": slugify(product_name),
        "price": price,
        "description": description,
        "description_sections": sections,
        "selling_points": selling_points[:12],
        "usage_signals": usage_signals,
        "material_policy": {
            "product_only_images": not include_page_images,
            "image_selection_rule": "Prefer JSON-LD Product.image assets; page images are only used when --include-page-images is set or structured product images are missing.",
            "raw_candidate_count_after_filter": len(all_image_candidates),
        },
        "images": image_records,
        "json_ld_product": product,
    }
    write_json(folder / "product_manifest.json", manifest)
    write_text(folder / "materials.md", build_materials_md(manifest))
    return {"folder": str(folder), "product_name": product_name, "url": url, "image_count": len(image_records)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape product pages into numbered material folders.")
    parser.add_argument("urls_file", type=Path)
    parser.add_argument("--out", type=Path, default=Path("product-ugc-output"))
    parser.add_argument("--max-images", type=int, default=12)
    parser.add_argument("--image-timeout", type=int, default=20)
    parser.add_argument("--include-page-images", action="store_true", help="Also include non-JSON-LD page images such as lifestyle/page assets.")
    args = parser.parse_args()
    urls = read_urls(args.urls_file)
    args.out.mkdir(parents=True, exist_ok=True)
    run_records = [
        scrape_product(index, url, args.out, args.max_images, args.image_timeout, args.include_page_images)
        for index, url in enumerate(urls, start=1)
    ]
    write_json(args.out / "run_manifest.json", {"products": run_records})
    print(f"[done] wrote {len(run_records)} product folders to {args.out}")


if __name__ == "__main__":
    main()

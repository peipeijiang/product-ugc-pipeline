#!/usr/bin/env python3
"""
Parallel fire-and-forget pipeline for image→video generation.
Submits all tasks at once, polls concurrently, cascades start→end→video.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Any

import requests

# ── config ──────────────────────────────────────────────────────────────
LK888_BASE = "https://api.lk888.ai"
LAOZHANG_BASE = "https://api.laozhang.ai/v1"
POLL_SECONDS = 4
MAX_POLL_SECONDS = 600  # 10 minute timeout per task

write_lock = Lock()


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    with write_lock:
        print(f"[{ts}] {msg}", flush=True)


def upload_litterbox(path: Path, lifetime: str = "1h") -> str:
    """Upload a file to litterbox.catbox.moe, return public URL."""
    cmd = [
        "curl", "--noproxy", "*", "--http1.1", "-fsS",
        "-F", "reqtype=fileupload",
        "-F", f"time={lifetime}",
        "-F", f"fileToUpload=@{path}",
        "https://litterbox.catbox.moe/resources/internals/api.php",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
    url = result.stdout.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"Unexpected upload response: {url[:300]}")
    return url


def lk888_post(endpoint: str, payload: dict) -> dict:
    resp = requests.post(
        f"{LK888_BASE}{endpoint}",
        headers={
            "Authorization": f"Bearer {LK888_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    if data.get("code") not in (None, 200):
        raise RuntimeError(f"API error: {json.dumps(data, ensure_ascii=False)}")
    return data


def lk888_get(endpoint: str, params: dict | None = None) -> dict:
    resp = requests.get(
        f"{LK888_BASE}{endpoint}",
        headers={"Authorization": f"Bearer {LK888_KEY}"},
        params=params,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    return resp.json()


def poll_task(task_id: str) -> dict:
    """Poll until is_final, return status dict."""
    deadline = time.time() + MAX_POLL_SECONDS
    transient = 0
    while time.time() < deadline:
        try:
            raw = lk888_get("/v1/media/status", params={"task_id": task_id})
            transient = 0
        except Exception as e:
            transient += 1
            if transient > 8:
                raise
            log(f"  poll transient error {transient}/8: {e}")
            time.sleep(POLL_SECONDS * 2)
            continue

        state = str(raw.get("state", "")).lower()
        is_final = bool(raw.get("is_final"))
        progress = raw.get("progress", "")

        if is_final:
            return raw
        if state in ("failed", "error", "cancelled", "canceled", "expired"):
            return raw

        if int(time.time()) % 15 == 0:
            log(f"  poll {task_id}: {state} {progress}")
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"Task {task_id} timed out after {MAX_POLL_SECONDS}s")


def submit_image(prompt: str, ref_urls: list[str], size: str = "auto") -> str:
    """Submit image gen to LK888 gpt-image-2, return task_id."""
    data = lk888_post("/v1/media/generate", {
        "model": "gpt-image-2",
        "prompt": prompt,
        "params": {
            "images": ref_urls,
            "size": size,
            "quality": "auto",
        },
    })
    task_ids = data.get("data", {}).get("task_ids", [])
    if not task_ids:
        task_ids = data.get("data", {}).get("任务ids", [])
    if not task_ids:
        raise RuntimeError(f"No task_id in response: {json.dumps(data, ensure_ascii=False)[:500]}")
    return str(task_ids[0])


def submit_video_veo(prompt: str, ref_urls: list[str], duration: str = "8") -> str:
    """Submit VEO video gen to LK888, return task_id."""
    data = lk888_post("/v1/media/generate", {
        "model": "veo3.1",
        "prompt": prompt,
        "params": {
            "images": ref_urls,
            "duration": duration,
            "aspect_ratio": "9:16",
        },
    })
    task_ids = data.get("data", {}).get("task_ids", [])
    if not task_ids:
        task_ids = data.get("data", {}).get("任务ids", [])
    if not task_ids:
        raise RuntimeError(f"No task_id: {json.dumps(data, ensure_ascii=False)[:500]}")
    return str(task_ids[0])


def is_veo_model(model: str) -> bool:
    return model.lower().startswith("veo")


def download_result(result_url: str, output_path: Path) -> bool:
    """Download result to output_path."""
    try:
        r = requests.get(result_url, timeout=120)
        if r.status_code == 200:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(r.content)
            return True
        log(f"  download HTTP {r.status_code}: {result_url[:100]}")
        return False
    except Exception as e:
        log(f"  download error: {e}")
        return False


# ── pipeline phases ────────────────────────────────────────────────────

def generate_image_from_tasks(
    tasks: list[dict],  # [{variant_id, role: "start"|"end", prompt, ref_urls}]
) -> dict[int, dict]:
    """Submit all image tasks in parallel, poll all, return {variant_id: {role: url}}."""
    results: dict[int, dict] = {}
    pending: dict[str, tuple[int, str]] = {}  # task_id -> (variant_id, role)

    # Phase 1: Submit all
    log(f"Submitting {len(tasks)} image tasks in parallel...")
    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as pool:
        futures = {}
        for t in tasks:
            fut = pool.submit(submit_image, t["prompt"], t["ref_urls"])
            futures[fut] = t
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                task_id = fut.result()
                pending[task_id] = (t["variant_id"], t["role"])
                results.setdefault(t["variant_id"], {})["_task_id"] = task_id
                log(f"  submitted variant-{t['variant_id']:02d} {t['role']} → {task_id}")
            except Exception as e:
                log(f"  FAILED submit variant-{t['variant_id']:02d} {t['role']}: {e}")

    # Phase 2: Poll all
    log(f"Polling {len(pending)} image tasks...")
    with ThreadPoolExecutor(max_workers=min(len(pending), 8)) as pool:
        poll_futures = {pool.submit(poll_task, tid): tid for tid in pending}
        for fut in as_completed(poll_futures):
            tid = poll_futures[fut]
            vid, role = pending[tid]
            try:
                status = fut.result()
                state = str(status.get("state", "")).lower()
                if state in ("success", "completed"):
                    url = status.get("result_url", "")
                    if url:
                        results.setdefault(vid, {})[role] = url
                        log(f"  ✓ variant-{vid:02d} {role}: {url[:80]}...")
                    else:
                        log(f"  ⚠ variant-{vid:02d} {role}: no result_url")
                else:
                    err = status.get("error", "") or status.get("status", "")
                    log(f"  ✗ variant-{vid:02d} {role} failed: {err}")
            except Exception as e:
                log(f"  ✗ variant-{vid:02d} {role} poll error: {e}")

    return results


def run_video_batch(
    product_dir: Path,
    variants: list[int],
    video_model: str,
    duration: str,
) -> None:
    """Run parallel video generation for given variants."""
    prompts_path = product_dir / "ugc_prompts.json"
    if not prompts_path.exists():
        log(f"No prompts file: {prompts_path}")
        return

    with open(prompts_path) as f:
        data = json.load(f)

    all_variants = data.get("variants", [])
    variant_map = {int(v.get("variant_id", 0)): v for v in all_variants}

    gen_dir = product_dir / "generated_images"
    video_dir = product_dir / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)

    # Collect tasks
    tasks = []
    for vid in variants:
        v = variant_map.get(vid)
        if not v:
            log(f"variant-{vid:02d}: not found in prompts")
            continue

        start_path = gen_dir / f"variant-{vid:02d}-start.png"
        end_path = gen_dir / f"variant-{vid:02d}-end.png"
        single_path = gen_dir / f"variant-{vid:02d}.png"

        refs = []
        if is_veo_model(video_model):
            missing = [p.name for p in (start_path, end_path) if not p.exists()]
            if missing:
                log(
                    f"variant-{vid:02d}: VEO requires generated start+end keyframes; "
                    f"missing {', '.join(missing)}, skipping video submission"
                )
                continue
            refs = [start_path, end_path]
        else:
            if start_path.exists():
                refs.append(start_path)
            if end_path.exists():
                refs.append(end_path)
            if not refs and single_path.exists():
                refs.append(single_path)
            if not refs:
                log(
                    f"variant-{vid:02d}: no Image2-generated reference frame in generated_images/, "
                    "skipping video submission"
                )
                continue

        output_path = video_dir / f"variant-{vid:02d}.mp4"
        if output_path.exists() and output_path.stat().st_size > 10000:
            log(f"variant-{vid:02d}: output exists ({output_path.stat().st_size} bytes), skipping")
            continue

        video_prompt = v.get("video_prompt", v.get("prompt", ""))
        tasks.append({
            "variant_id": vid,
            "ref_paths": refs,
            "video_prompt": video_prompt,
            "output_path": output_path,
        })

    if not tasks:
        log("No tasks to submit.")
        return

    log(f"Uploading {sum(len(t['ref_paths']) for t in tasks)} reference images...")
    
    # Upload all images in parallel
    ref_url_cache: dict[Path, str] = {}
    with ThreadPoolExecutor(max_workers=min(sum(len(t["ref_paths"]) for t in tasks), 8)) as pool:
        upload_futures = {}
        for t in tasks:
            for p in t["ref_paths"]:
                if p not in ref_url_cache and p not in upload_futures.values():
                    upload_futures[pool.submit(upload_litterbox, p)] = p

        for fut in as_completed(upload_futures):
            p = upload_futures[fut]
            try:
                url = fut.result()
                ref_url_cache[p] = url
                log(f"  uploaded {p.name} → {url[:60]}...")
            except Exception as e:
                log(f"  upload failed {p.name}: {e}")

    # Submit all video tasks in parallel
    log(f"Submitting {len(tasks)} video tasks to {video_model}...")
    pending: dict[str, dict] = {}  # task_id -> task info
    
    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as pool:
        submit_futures = {}
        for t in tasks:
            ref_urls = []
            for p in t["ref_paths"]:
                url = ref_url_cache.get(p)
                if url:
                    ref_urls.append(url)
            if not ref_urls:
                log(f"variant-{t['variant_id']:02d}: no ref URLs, skipping")
                continue
            
            try:
                fut = pool.submit(submit_video_veo, t["video_prompt"], ref_urls, duration)
                submit_futures[fut] = t
            except Exception as e:
                log(f"submit failed variant-{t['variant_id']:02d}: {e}")

        for fut in as_completed(submit_futures):
            t = submit_futures[fut]
            try:
                task_id = fut.result()
                pending[task_id] = t
                log(f"  submitted variant-{t['variant_id']:02d} → {task_id}")
            except Exception as e:
                log(f"  FAILED variant-{t['variant_id']:02d}: {e}")

    if not pending:
        log("No video tasks submitted.")
        return

    # Poll all video tasks in parallel
    log(f"Polling {len(pending)} video tasks...")
    completed = 0
    with ThreadPoolExecutor(max_workers=min(len(pending), 8)) as pool:
        poll_futures = {pool.submit(poll_task, tid): (tid, pending[tid]) for tid in pending}
        for fut in as_completed(poll_futures):
            tid, t = poll_futures[fut]
            try:
                status = fut.result()
                state = str(status.get("state", "")).lower()
                if state in ("success", "completed"):
                    url = status.get("result_url", "")
                    cost = status.get("cost", "?")
                    if url:
                        ok = download_result(url, t["output_path"])
                        if ok:
                            log(f"  ✓ variant-{t['variant_id']:02d}: downloaded ({t['output_path'].stat().st_size} bytes) cost=${cost}")
                            completed += 1
                        else:
                            log(f"  ✗ variant-{t['variant_id']:02d}: download failed")
                    else:
                        log(f"  ⚠ variant-{t['variant_id']:02d}: no result_url")
                else:
                    err = status.get("error", "") or status.get("status", "")
                    cost = status.get("cost", "?")
                    log(f"  ✗ variant-{t['variant_id']:02d}: {state} cost=${cost} error={err[:200]}")
            except Exception as e:
                log(f"  ✗ variant-{t['variant_id']:02d} poll error: {e}")

    log(f"Done. {completed}/{len(tasks)} videos completed.")


# ── CLI ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parallel image→video pipeline")
    parser.add_argument("product_dir", type=Path)
    parser.add_argument("--variants", default="12-19")
    parser.add_argument("--video-model", default="veo3.1")
    parser.add_argument("--duration", default="8")
    parser.add_argument("--lk888-key", default=os.environ.get("LK888_API_KEY", ""))
    args = parser.parse_args()

    LK888_KEY = args.lk888_key
    if not LK888_KEY:
        print("Missing LK888_API_KEY", file=sys.stderr)
        sys.exit(1)

    variant_ids = []
    for part in args.variants.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            variant_ids.extend(range(int(a), int(b) + 1))
        else:
            variant_ids.append(int(part))

    # Ensure no proxy interference
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        os.environ.pop(var, None)

    run_video_batch(args.product_dir, variant_ids, args.video_model, args.duration)

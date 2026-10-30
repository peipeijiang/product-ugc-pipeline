"""Shared storyboard contract.

Panel content is shared by image and video generation.  Board-layout language is
owned only by the image renderer and must never leak into a video beat.
"""
import re


_LAYOUT_PATTERNS = (
    re.compile(r"\bstrict\s+literal\s+3\s*[x×]\s*[23]\s+grid\s*:[^.]*\.?", re.I),
    re.compile(r"\bpostplus\s+contact\s+sheet\s+frame\s+\d+\s*/\s*\d+\s*\.?", re.I),
    re.compile(
        r"\b(?:equal\s+)?(?:\d+\s*:\s*\d+\s+)?portrait\s+frame\s+in\s+(?:an?\s+)?"
        r"(?:six|nine|\d+)[-\s]frame(?:\s+3\s*[x×]\s*[23])?\s+storyboard\s+sheet\s*\.?",
        re.I,
    ),
    re.compile(r"\bpanel\s+\d+\s+(?:of|/)\s+(?:6|9)\s*[:.\-]?", re.I),
)

_FORBIDDEN_PANEL_LAYOUT_MARKERS = (
    re.compile(r"\bcontact\s+sheet\b", re.I),
    re.compile(r"\bstoryboard\s+(?:sheet|grid|board|layout)\b", re.I),
    re.compile(r"\b3\s*[x×]\s*[23]\b", re.I),
    re.compile(r"\bgutters?\b", re.I),
    re.compile(r"\bpanel\s+(?:borders?|labels?|numbers?)\b", re.I),
    re.compile(r"\bsplit[-\s]?screen\b", re.I),
    re.compile(r"\bpicture[-\s]?in[-\s]?picture\b", re.I),
    re.compile(r"\bcollage\b", re.I),
)

VIDEO_SINGLE_CANVAS_RULE = (
    "Use the storyboard only as a chronological reference. Output one full-screen scene at every moment; never render "
    "the board as a collage, grid, split screen or picture-in-picture."
)


def sanitize_storyboard_visual(value):
    """Remove known board-layout wrappers while preserving the panel's action."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    for pattern in _LAYOUT_PATTERNS:
        text = pattern.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .;:-")
    for pattern in _FORBIDDEN_PANEL_LAYOUT_MARKERS:
        if pattern.search(text):
            raise RuntimeError(
                "Storyboard panel visual contains board-layout language; keep visual to camera, subject, action and environment only"
            )
    if not text:
        raise RuntimeError("Storyboard panel visual became empty after removing board-layout instructions")
    return text


def storyboard_panel_visual(panel):
    """Return one layout-free visible beat, preferring structured panel fields."""
    if not isinstance(panel, dict):
        raise RuntimeError("Every storyboard panel must be an object")
    action = str(panel.get("action") or "").strip()
    if action:
        parts = [panel.get("camera"), panel.get("subject"), action, panel.get("environment")]
        return sanitize_storyboard_visual(". ".join(str(part).strip() for part in parts if str(part or "").strip()))
    return sanitize_storyboard_visual(panel.get("visual") or panel.get("shot"))


def storyboard_video_beats(variant):
    """Build the exact 6/9 chronological beat list used by video prompts."""
    storyboard_spec(variant)
    beats = []
    for panel in variant["storyboard_10s"]:
        beats.append({
            "time": str(panel.get("time") or panel.get("timing") or "").strip(),
            "visual": storyboard_panel_visual(panel),
            "spoken": str(panel.get("spoken") or panel.get("spoken_line") or "").strip(),
            "overlay": str(panel.get("overlay") or "").strip(),
        })
    return beats


def storyboard_spec(variant):
    panels = variant.get("storyboard_10s")
    if not isinstance(panels, list) or len(panels) not in (6, 9):
        raise RuntimeError("Storyboard requires exactly 6 panels, or 9 for dense action; revise storyboard_10s before rendering")
    declared = variant.get("storyboard_panel_count")
    if declared is not None:
        if isinstance(declared, bool) or declared not in (6, 9):
            raise RuntimeError("storyboard_panel_count must be 6 or 9")
        if declared != len(panels):
            raise RuntimeError("storyboard_panel_count must match storyboard_10s length")
    reason = variant.get("storyboard_density_reason")
    if reason is not None and not str(reason).strip():
        raise RuntimeError("storyboard_density_reason cannot be empty when provided")
    previous = 0.0
    for panel in panels:
        if not isinstance(panel, dict) or not str(panel.get("visual") or panel.get("shot") or panel.get("action") or "").strip():
            raise RuntimeError("Every storyboard panel requires an explicit visual description")
        times = re.findall(r"\d+(?:\.\d+)?", str(panel.get("time", "")))
        if len(times) != 2:
            raise RuntimeError("Every panel requires a start-end time interval")
        start, end = map(float, times)
        if abs(start - previous) > 0.011 or end <= start:
            raise RuntimeError("Storyboard intervals must be contiguous and chronological")
        previous = end
    if abs(previous - 10) > 0.011:
        raise RuntimeError("Storyboard must cover exactly 0-10 seconds")
    frame = str(variant.get("target_frame_aspect_ratio") or "9:16")
    if frame != "9:16":
        raise RuntimeError("UGC storyboard panels must be 9:16; use a separate pipeline for another delivery format")
    # Six portrait panels are arranged as 3 columns x 2 rows. Each cell stays
    # 9:16 and the whole sheet is the natural 27:32 storyboard canvas.
    columns, rows = (3, 2) if len(panels) == 6 else (3, 3)
    # These are exact production canvases, not provider-selected approximations.
    # Six 540x960 cells make 1620x1920 (27:32); nine 360x640 cells make 1080x1920.
    board_ratio, size, cell_size = (
        ("27:32", "1620x1920", "540x960")
        if len(panels) == 6
        else ("9:16", "1080x1920", "360x640")
    )
    spec = {"panel_count": len(panels), "columns": columns, "rows": rows,
            "targetFrameAspectRatio": frame,
            "boardLayoutRatio": board_ratio,
            "size": size,
            "panelPixelSize": cell_size,
            "reading_order": "left-to-right, then top-to-bottom"}
    persisted = variant.get("grid_spec")
    if persisted is not None and persisted != spec:
        raise RuntimeError("Persisted grid_spec must match storyboard_panel_count, storyboard_10s and target frame ratio")
    return spec

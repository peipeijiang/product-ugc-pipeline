"""Shared panel and canvas contract; never infer new scenes in the image runner."""
from fractions import Fraction
import re


def storyboard_spec(variant):
    panels = variant.get("storyboard_10s")
    if not isinstance(panels, list) or len(panels) not in (6, 9):
        raise RuntimeError("Storyboard requires exactly 6 panels, or 9 for dense action; revise storyboard_10s before rendering")
    previous = 0.0
    for panel in panels:
        if not isinstance(panel, dict) or not str(panel.get("visual") or "").strip():
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
    try:
        w, h = map(int, frame.split(":"))
        if w <= 0 or h <= 0:
            raise ValueError()
    except ValueError:
        raise RuntimeError("Invalid target_frame_aspect_ratio") from None
    columns, rows = 3, len(panels) // 3
    ratio = Fraction(columns * w, rows * h)
    # Whole-sheet dimensions preserve the per-panel ratio on every provider.
    unit = max(1, round(1920 / max(columns * w, rows * h)))
    return {"panel_count": len(panels), "columns": columns, "rows": rows,
            "targetFrameAspectRatio": frame,
            "boardLayoutRatio": f"{ratio.numerator}:{ratio.denominator}",
            "size": f"{columns*w*unit}x{rows*h*unit}",
            "reading_order": "left-to-right, then top-to-bottom"}

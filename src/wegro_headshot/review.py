"""Builds the human checkpoint: before/after images and one contact sheet.

An automated identity score is useful but it is not the final word. The design
team still has to look at the set, so the review folder is built to make that
take a couple of minutes rather than an afternoon.
"""

from __future__ import annotations

import html
from pathlib import Path

import cv2
import numpy as np

from .manifest import STATUS_FINAL, STATUS_NEEDS_ATTENTION, Manifest

PANEL_HEIGHT = 520


def _fit_height(image: np.ndarray, height: int) -> np.ndarray:
    scale = height / image.shape[0]
    return cv2.resize(
        image, (max(1, int(round(image.shape[1] * scale))), height),
        interpolation=cv2.INTER_AREA,
    )


def _label(panel: np.ndarray, text: str) -> np.ndarray:
    bar = np.full((34, panel.shape[1], 3), 24, dtype=np.uint8)
    cv2.putText(bar, text, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (235, 235, 235), 1, cv2.LINE_AA)
    return np.vstack([bar, panel])


def write_comparison(
    original: np.ndarray, final: np.ndarray, employee_id: str,
    similarity: float | None, cfg,
) -> Path:
    """Save an original-vs-finished image so a person can judge the result."""
    left = _label(_fit_height(original, PANEL_HEIGHT), "ORIGINAL")
    score = f"  (face match {similarity:.2f})" if similarity is not None else ""
    right = _label(_fit_height(final, PANEL_HEIGHT), f"FINISHED{score}")

    gap = np.full((left.shape[0], 12, 3), 24, dtype=np.uint8)
    sheet = np.hstack([left, gap, right])

    path = cfg.path("review") / f"{employee_id}_compare.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return path


def _card(record, cfg) -> str:
    final_png = cfg.path("final") / f"{record.employee_id}.png"
    compare = cfg.path("review") / f"{record.employee_id}_compare.jpg"

    if final_png.exists():
        src = f"../05_final/{record.employee_id}.png"
    elif compare.exists():
        src = f"{record.employee_id}_compare.jpg"
    else:
        src = ""

    score = (f"{record.face_similarity:.2f}"
             if record.face_similarity is not None else "n/a")
    warn = record.face_similarity is not None and \
        record.face_similarity < float(cfg.qa.min_face_similarity)

    chips = "".join(
        f'<span class="chip">{html.escape(f)}</span>' for f in record.flags
    )
    if record.status != STATUS_FINAL:
        chips += f'<span class="chip bad">{html.escape(record.status)}</span>'

    reason = (f'<p class="reason">{html.escape(record.reason)}</p>'
              if record.reason else "")

    image = (f'<img src="{html.escape(src)}" alt="{html.escape(record.employee_id)}" loading="lazy">'
             if src else '<div class="missing">no image</div>')

    return f"""
    <figure class="card{' flagged' if warn else ''}">
      {image}
      <figcaption>
        <strong>{html.escape(record.employee_id)}</strong>
        <span class="score{' bad' if warn else ''}">face match {score}</span>
        <div class="chips">{chips}</div>
        {reason}
      </figcaption>
    </figure>"""


def write_contact_sheet(manifest: Manifest, cfg) -> Path:
    """One page showing every employee, worst face-match score first."""
    records = sorted(
        manifest.employees.values(),
        key=lambda r: (r.status == STATUS_FINAL,
                       r.face_similarity if r.face_similarity is not None else -1.0),
    )

    total = len(records)
    ok = sum(1 for r in records if r.status == STATUS_FINAL)
    attention = sum(1 for r in records if r.status == STATUS_NEEDS_ATTENTION)

    cards = "\n".join(_card(r, cfg) for r in records)

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WeGro team photos - review</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ margin: 0; padding: 32px; font: 15px/1.5 system-ui, sans-serif;
         background: #14171a; color: #e8eaed; }}
  h1 {{ margin: 0 0 4px; font-size: 22px; }}
  .summary {{ color: #9aa4ad; margin-bottom: 24px; }}
  .summary b {{ color: #e8eaed; }}
  .note {{ background: #1d2126; border-left: 3px solid #4a90d9; padding: 12px 16px;
           margin-bottom: 28px; border-radius: 4px; color: #b9c2cb; max-width: 70ch; }}
  .grid {{ display: grid; gap: 20px;
          grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }}
  .card {{ margin: 0; background: #1d2126; border-radius: 8px; overflow: hidden;
          border: 1px solid #2a2f36; }}
  .card.flagged {{ border-color: #c2683a; }}
  .card img {{ width: 100%; display: block; background: #000; }}
  .missing {{ aspect-ratio: 4/3; display: grid; place-items: center; color: #6b7480; }}
  figcaption {{ padding: 12px 14px 14px; }}
  figcaption strong {{ display: block; margin-bottom: 4px; word-break: break-all; }}
  .score {{ color: #7fba7a; font-size: 13px; }}
  .score.bad {{ color: #e0895c; }}
  .chips {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; }}
  .chip {{ font-size: 11px; padding: 2px 7px; border-radius: 10px;
          background: #2c323a; color: #b9c2cb; }}
  .chip.bad {{ background: #5a2f22; color: #f0b49a; }}
  .reason {{ margin: 8px 0 0; font-size: 12px; color: #e0895c; }}
</style>
</head>
<body>
  <h1>WeGro team photos &mdash; review</h1>
  <p class="summary">
    <b>{total}</b> people &middot; <b>{ok}</b> ready &middot;
    <b>{attention}</b> need attention &middot; sorted worst match first
  </p>
  <p class="note">
    Scroll the grid and check that every face still looks like the right person
    and that heads are all the same size. Anything you are unhappy with: delete
    that person's files from <code>05_final</code>, put a better source photo in
    <code>01_inbox</code> using the same file name, and run the tool again.
  </p>
  <div class="grid">{cards}
  </div>
</body>
</html>"""

    path = cfg.path("review") / "_contact_sheet.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path

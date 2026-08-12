"""Stage 7: write the website-ready files."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def _write(path: Path, image: np.ndarray, params: list[int] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image, params or [])
    if not ok:
        raise OSError(f"Could not write {path}")
    return path


def export(image: np.ndarray, employee_id: str, cfg) -> list[Path]:
    """Save the finished composite in every configured format."""
    final_dir = cfg.path("final")
    width, height = int(cfg.output.width), int(cfg.output.height)

    # The working render is larger than the export, so this downscale is what
    # gives the final files their crispness.
    web = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)

    written = [_write(final_dir / f"{employee_id}.png", web,
                      [cv2.IMWRITE_PNG_COMPRESSION, 6])]

    if cfg.output.webp:
        written.append(_write(
            final_dir / f"{employee_id}.webp", web,
            [cv2.IMWRITE_WEBP_QUALITY, int(cfg.output.webp_quality)],
        ))

    if cfg.output.save_large and image.shape[1] > width:
        written.append(_write(
            final_dir / f"{employee_id}-large.png", image,
            [cv2.IMWRITE_PNG_COMPRESSION, 6],
        ))

    return written


def expected_outputs(employee_id: str, cfg) -> list[Path]:
    """The files a completed employee should have, used by the skip check."""
    final_dir = cfg.path("final")
    paths = [final_dir / f"{employee_id}.png"]
    if cfg.output.webp:
        paths.append(final_dir / f"{employee_id}.webp")
    if cfg.output.save_large:
        paths.append(final_dir / f"{employee_id}-large.png")
    return paths

"""A back-end that generates nothing.

Used to exercise ingest, skip logic, framing, compositing and export without
spending any of the free API quota. Run with:  run.bat --provider stub
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from .base import ImageProvider


class StubProvider(ImageProvider):
    name = "stub"

    def __init__(self, cfg: Any):
        self.cfg = cfg

    def restyle(self, image: np.ndarray, outfit: dict[str, str]) -> np.ndarray:
        """Return the input on a flat grey field, so the cutout stage has
        something realistic to work with."""
        out = image.copy()
        h, w = out.shape[:2]
        label = f"STUB - {outfit['suit']}"
        cv2.putText(
            out, label, (12, h - 16), cv2.FONT_HERSHEY_SIMPLEX,
            0.6, (0, 0, 255), 2, cv2.LINE_AA,
        )
        return out

    @property
    def model_label(self) -> str:
        return "stub (no AI)"

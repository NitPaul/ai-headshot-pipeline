"""Stage 1: make wildly different source photos comparable.

The inbox realistically contains phone snaps, WhatsApp forwards and old ID
photos: different orientations, colour casts and resolutions. Everything here
is deterministic clean-up, before any AI is involved.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from . import facedet

FLAG_LOW_QUALITY = "LOW_QUALITY"
FLAG_UPSCALED = "UPSCALED"
FLAG_MULTIPLE_FACES = "MULTIPLE_FACES"


class NoFaceFound(RuntimeError):
    pass


def load_image(path: Path) -> np.ndarray:
    """Read any common format as BGR, honouring the EXIF rotation flag.

    Phone photos are frequently stored sideways with a rotation tag; without
    this, half the inbox arrives lying on its side.
    """
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            flat = Image.new("RGB", img.size, (255, 255, 255))
            flat.paste(img, mask=img.split()[-1])
            img = flat
        else:
            img = img.convert("RGB")
        rgb = np.array(img)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def neutralize_white_balance(bgr: np.ndarray, strength: float = 0.7) -> np.ndarray:
    """Remove yellow/blue colour casts so everyone matches on the team page.

    Uses a white-patch estimate: the brightest few percent of pixels should be
    neutral. Applied only partially, because a full correction tends to drain
    the warmth out of skin tones.
    """
    if strength <= 0:
        return bgr

    work = bgr.astype(np.float32)
    luma = work.mean(axis=2)
    threshold = np.percentile(luma, 97.0)
    bright = work[luma >= threshold]
    if bright.size == 0:
        return bgr

    means = bright.mean(axis=0)
    if float(means.min()) < 1.0:
        return bgr

    target = float(means.mean())
    gains = target / means
    gains = 1.0 + (gains - 1.0) * float(strength)
    # Cap the correction so a photo shot against a coloured wall is not wrecked.
    gains = np.clip(gains, 0.75, 1.35)

    corrected = work * gains.reshape(1, 1, 3)
    return np.clip(corrected, 0, 255).astype(np.uint8)


def upscale_to_face_size(
    bgr: np.ndarray, face: facedet.Face, target_face_px: int, max_factor: float = 4.0
) -> tuple[np.ndarray, float]:
    """Enlarge a small photo so the face carries enough detail to survive
    the crop. Returns the image and the scale factor applied."""
    if face.width <= 0 or face.width >= target_face_px:
        return bgr, 1.0

    factor = min(target_face_px / face.width, max_factor)
    if factor <= 1.01:
        return bgr, 1.0

    h, w = bgr.shape[:2]
    enlarged = cv2.resize(
        bgr, (int(round(w * factor)), int(round(h * factor))),
        interpolation=cv2.INTER_LANCZOS4,
    )
    # Lanczos leaves upscaled photos slightly soft; a light unsharp mask
    # restores perceived detail without the halos of aggressive sharpening.
    blurred = cv2.GaussianBlur(enlarged, (0, 0), 1.6)
    sharpened = cv2.addWeighted(enlarged, 1.5, blurred, -0.5, 0)
    return sharpened, factor


def normalize(path: Path, cfg) -> tuple[np.ndarray, facedet.Face, list[str]]:
    """Full stage-1 pass. Returns the cleaned image, its face, and any flags."""
    flags: list[str] = []
    bgr = load_image(path)

    if cfg.input.neutralize_white_balance:
        bgr = neutralize_white_balance(bgr)

    face = facedet.detect(bgr)
    if face is None:
        raise NoFaceFound(
            "No face could be found in this photo. It may be too dark, too "
            "small, side-on, or not a portrait."
        )

    if face.total_faces > 1:
        flags.append(FLAG_MULTIPLE_FACES)

    if face.width < cfg.qa.min_face_width_px:
        flags.append(FLAG_LOW_QUALITY)

    if cfg.input.upscale_small_inputs:
        bgr, factor = upscale_to_face_size(
            bgr, face, int(cfg.input.upscale_target_face_px)
        )
        if factor > 1.01:
            flags.append(FLAG_UPSCALED)
            # Landmarks were measured before the resize, so find them again.
            refreshed = facedet.detect(bgr)
            if refreshed is not None:
                face = refreshed

    return bgr, face, flags

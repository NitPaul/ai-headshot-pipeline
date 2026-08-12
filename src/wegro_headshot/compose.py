"""Stage 6: place the person on the branded background.

The supplied frame is a flat 1080x1080 background plate with no transparency,
while the website format is wider. The plate is therefore extended sideways by
mirroring and blurring its edges. Because the plate is an out-of-focus office
scene, the extension is not visible.

The plate is built once and cached, so every employee is composited onto
byte-identical pixels. That is what guarantees the backgrounds match exactly.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def _cover_resize(image: np.ndarray, width: int, height: int) -> np.ndarray:
    """Scale to fill the target, cropping the overflow, without distortion."""
    h, w = image.shape[:2]
    scale = max(width / w, height / h)
    resized = cv2.resize(
        image, (int(np.ceil(w * scale)), int(np.ceil(h * scale))),
        interpolation=cv2.INTER_LANCZOS4,
    )
    y = (resized.shape[0] - height) // 2
    x = (resized.shape[1] - width) // 2
    return resized[y: y + height, x: x + width]


def _extend_sides(image: np.ndarray, width: int, blur: int) -> np.ndarray:
    """Widen by mirroring both edges, then blur only the added strips."""
    h, w = image.shape[:2]
    if w >= width:
        x = (w - width) // 2
        return image[:, x: x + width]

    pad_left = (width - w) // 2
    pad_right = width - w - pad_left
    widened = cv2.copyMakeBorder(
        image, 0, 0, pad_left, pad_right, cv2.BORDER_REFLECT_101
    )

    blur = max(3, int(blur) | 1)
    blurred = cv2.GaussianBlur(widened, (blur, blur), 0)

    # Ramp from original to blurred across the seam so no hard line appears.
    ramp = np.ones(width, dtype=np.float32)
    ramp[:pad_left] = 0.0
    ramp[width - pad_right:] = 0.0
    ramp = cv2.GaussianBlur(ramp.reshape(1, -1), (0, 0), pad_left * 0.6 + 1).ravel()
    ramp = np.clip(ramp, 0, 1)[None, :, None]

    return np.clip(
        widened.astype(np.float32) * ramp + blurred.astype(np.float32) * (1 - ramp),
        0, 255,
    ).astype(np.uint8)


def build_plate(cfg, width: int, height: int) -> np.ndarray:
    """Load, extend and cache the background plate at the working size."""
    cache = cfg.path("working") / f"_plate_{width}x{height}.png"
    if cache.exists():
        cached = cv2.imread(str(cache), cv2.IMREAD_COLOR)
        if cached is not None and cached.shape[:2] == (height, width):
            return cached

    source = cv2.imread(str(cfg.root / cfg.plate.file), cv2.IMREAD_COLOR)
    if source is None:
        raise FileNotFoundError(f"Could not read the plate: {cfg.plate.file}")

    # Match the height first, then widen, so nothing is squashed.
    scale = height / source.shape[0]
    scaled = cv2.resize(
        source,
        (int(round(source.shape[1] * scale)), height),
        interpolation=cv2.INTER_LANCZOS4,
    )

    if cfg.plate.extend_mode == "mirror_blur":
        plate = _extend_sides(scaled, width, int(cfg.plate.extend_blur))
    else:
        plate = _cover_resize(source, width, height)

    softness = 1.0 - float(cfg.plate.background_softness)
    if softness < 1.0:
        smoothed = cv2.GaussianBlur(plate, (0, 0), max(width, height) * 0.012)
        plate = np.clip(
            plate.astype(np.float32) * softness
            + smoothed.astype(np.float32) * (1.0 - softness),
            0, 255,
        ).astype(np.uint8)

    cache.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(cache), plate)
    return plate


def _drop_shadow(alpha: np.ndarray, cfg) -> np.ndarray:
    """A soft shadow behind the subject so they sit in the scene."""
    blur = max(3, int(cfg.plate.shadow.blur) | 1)
    shadow = cv2.GaussianBlur(alpha, (blur, blur), 0).astype(np.float32) / 255.0

    offset = int(cfg.plate.shadow.offset_y)
    if offset:
        shadow = np.roll(shadow, offset, axis=0)
        shadow[:offset] = 0

    return shadow * float(cfg.plate.shadow.opacity)


def composite(person_rgba: np.ndarray, plate: np.ndarray, cfg) -> np.ndarray:
    """Lay the cut-out person onto the plate."""
    height, width = plate.shape[:2]
    if person_rgba.shape[:2] != (height, width):
        person_rgba = cv2.resize(
            person_rgba, (width, height), interpolation=cv2.INTER_LANCZOS4
        )

    person = person_rgba[:, :, :3].astype(np.float32)
    alpha = person_rgba[:, :, 3]
    canvas = plate.astype(np.float32)

    if cfg.plate.shadow.enabled:
        shadow = _drop_shadow(alpha, cfg)[:, :, None]
        canvas = canvas * (1.0 - shadow)

    a = (alpha.astype(np.float32) / 255.0)[:, :, None]
    blended = canvas * (1.0 - a) + person * a
    return np.clip(blended, 0, 255).astype(np.uint8)

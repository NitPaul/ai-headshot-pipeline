"""Stage 5: separate the person from the generated background.

The model is asked to produce the person on a plain, evenly lit backdrop
precisely so this step is reliable. rembg does the work when available; if it
is not installed, a colour-key fallback handles the plain backdrop well enough
that the tool still runs.
"""

from __future__ import annotations

import cv2
import numpy as np

_session = None
_session_failed = False


def _get_session():
    """rembg loads a ~170 MB model on first use, so build it once."""
    global _session, _session_failed
    if _session is not None or _session_failed:
        return _session
    try:
        from rembg import new_session

        _session = new_session("u2net_human_seg")
    except Exception:
        _session_failed = True
        _session = None
    return _session


def _alpha_from_rembg(bgr: np.ndarray) -> np.ndarray | None:
    session = _get_session()
    if session is None:
        return None
    try:
        from rembg import remove

        rgba = remove(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA), session=session)
        return np.asarray(rgba)[:, :, 3]
    except Exception:
        return None


def _alpha_from_colour_key(bgr: np.ndarray) -> np.ndarray:
    """Fallback: the backdrop is plain, so key it out by colour distance.

    The backdrop colour is sampled from the image corners, which the subject
    never occupies in a head-and-shoulders crop.
    """
    h, w = bgr.shape[:2]
    patch = max(8, min(h, w) // 40)
    corners = np.concatenate([
        bgr[:patch, :patch].reshape(-1, 3),
        bgr[:patch, -patch:].reshape(-1, 3),
    ])
    background = np.median(corners, axis=0)

    distance = np.linalg.norm(bgr.astype(np.float32) - background, axis=2)
    spread = float(np.percentile(distance, 92)) or 1.0
    alpha = np.clip(distance / max(spread * 0.55, 1.0), 0, 1)

    alpha = (alpha * 255).astype(np.uint8)
    _, alpha = cv2.threshold(alpha, 40, 255, cv2.THRESH_TOZERO)

    # Keep only the largest connected region, so stray specks are dropped.
    binary = (alpha > 128).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if count > 1:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        alpha[labels != biggest] = 0

    return alpha


def _refine(alpha: np.ndarray, feather: int = 3) -> np.ndarray:
    """Tidy the matte: fill pinholes, pull the edge in slightly, soften it.

    Pulling the edge in by a pixel removes the halo of leftover backdrop that
    otherwise shows as a bright fringe against the darker brand plate.
    """
    alpha = cv2.morphologyEx(
        alpha, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    )
    alpha = cv2.erode(alpha, np.ones((3, 3), np.uint8), iterations=1)
    feather = max(3, int(feather) | 1)
    return cv2.GaussianBlur(alpha, (feather, feather), 0)


def _estimate_background(bgr: np.ndarray) -> np.ndarray:
    """The backdrop colour, sampled from the top corners the subject never fills."""
    h, w = bgr.shape[:2]
    patch = max(8, min(h, w) // 40)
    corners = np.concatenate([
        bgr[:patch, :patch].reshape(-1, 3),
        bgr[:patch, -patch:].reshape(-1, 3),
    ])
    return np.median(corners, axis=0).astype(np.float32)


def _decontaminate(bgr: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Remove the backdrop's colour from semi-transparent edge pixels.

    Around hair and shoulders a pixel is a mixture of subject and backdrop.
    Composited straight onto the darker brand plate, that leftover backdrop
    reads as a pale halo. Since the observed pixel is
    C = a*F + (1-a)*B, the subject's true colour can be recovered as
    F = (C - (1-a)*B) / a.
    """
    background = _estimate_background(bgr)
    a = (alpha.astype(np.float32) / 255.0)[:, :, None]

    # Only meaningful where the pixel is part subject; fully opaque pixels are
    # already correct and very transparent ones are too noisy to recover.
    edge = (a > 0.08) & (a < 0.98)
    if not edge.any():
        return bgr

    recovered = (bgr.astype(np.float32) - (1.0 - a) * background) / np.maximum(a, 0.08)
    recovered = np.clip(recovered, 0, 255)

    return np.where(edge, recovered, bgr.astype(np.float32)).astype(np.uint8)


def cut_out(bgr: np.ndarray) -> tuple[np.ndarray, str]:
    """Return a BGRA image of the person, and which method produced it."""
    alpha = _alpha_from_rembg(bgr)
    method = "rembg"
    if alpha is None:
        alpha = _alpha_from_colour_key(bgr)
        method = "colour-key"

    alpha = _refine(alpha)
    cleaned = _decontaminate(bgr, alpha)

    rgba = np.dstack([cleaned, alpha])
    return rgba, method

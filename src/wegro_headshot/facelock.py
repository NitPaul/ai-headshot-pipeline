"""Stage 4: put the employee's real face back.

Image models are good at inventing a suit but they do not reliably preserve a
person's identity: faces drift into "someone who looks similar". Rather than
trying to prompt that away, this stage takes the actual pixels of the original
face and composites them onto the generated body.

The three parts that make it look natural rather than pasted on:

  1. the original face is warped onto wherever the model put the face,
  2. its lighting is matched to the generated image in LAB colour space,
  3. the blend runs through a soft mask over the face interior only, so hair
     and the jaw/neck boundary stay with the generated image.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from . import facedet

# Landmarks that sit on rigid bone rather than moving with expression. Using
# these to fit the transform keeps a smile from skewing the alignment.
STABLE_POINTS = [
    33, 133, 362, 263,        # eye corners
    1, 4, 6, 168,             # nose bridge and tip
    234, 454,                 # cheek extremes
    10, 152,                  # forehead and chin
    127, 356,                 # temples
]


@dataclass
class FaceLockResult:
    image: np.ndarray
    applied: bool
    note: str = ""


def _similarity_from_landmarks(
    src: np.ndarray, dst: np.ndarray
) -> np.ndarray | None:
    src_pts = src[STABLE_POINTS].astype(np.float32)
    dst_pts = dst[STABLE_POINTS].astype(np.float32)
    matrix, _ = cv2.estimateAffinePartial2D(
        src_pts, dst_pts, method=cv2.LMEDS, refineIters=20
    )
    return matrix


def _similarity_from_eyes(src: facedet.Face, dst: facedet.Face) -> np.ndarray:
    """Two matching points fully determine a similarity transform."""
    src_pts = np.array([src.left_eye, src.right_eye], dtype=np.float32)
    dst_pts = np.array([dst.left_eye, dst.right_eye], dtype=np.float32)

    src_vec = src_pts[1] - src_pts[0]
    dst_vec = dst_pts[1] - dst_pts[0]
    scale = float(np.linalg.norm(dst_vec) / max(np.linalg.norm(src_vec), 1e-6))
    angle = float(
        np.degrees(np.arctan2(dst_vec[1], dst_vec[0]))
        - np.degrees(np.arctan2(src_vec[1], src_vec[0]))
    )

    src_mid = src_pts.mean(axis=0)
    dst_mid = dst_pts.mean(axis=0)
    matrix = cv2.getRotationMatrix2D((float(src_mid[0]), float(src_mid[1])),
                                     -angle, scale)
    matrix[0, 2] += dst_mid[0] - src_mid[0]
    matrix[1, 2] += dst_mid[1] - src_mid[1]
    return matrix


def _build_mask(
    face: facedet.Face, shape: tuple[int, int], mask_scale: float, feather: int
) -> np.ndarray:
    """A soft-edged mask covering the face interior, as float 0..1."""
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)

    oval = face.oval()
    if oval is not None:
        centroid = oval.mean(axis=0)
        shrunk = (oval - centroid) * mask_scale + centroid
        cv2.fillConvexPoly(mask, cv2.convexHull(shrunk.astype(np.int32)), 255)
    else:
        # Cascade fallback: an ellipse over the face box is close enough.
        x, y, w, h = face.bbox
        cv2.ellipse(
            mask,
            (int(x + w / 2), int(y + h / 2)),
            (int(w * 0.5 * mask_scale), int(h * 0.62 * mask_scale)),
            0, 0, 360, 255, -1,
        )

    feather = max(3, int(feather) | 1)
    mask = cv2.GaussianBlur(mask, (feather, feather), 0)
    return mask.astype(np.float32) / 255.0


def _match_lighting(
    source: np.ndarray, target: np.ndarray, mask: np.ndarray
) -> np.ndarray:
    """Give `source` the lighting of `target`, measured inside `mask`.

    Brightness is matched fully because that is what makes a paste look
    seamless. Colour is matched only halfway, so the employee keeps their own
    skin tone instead of adopting whatever the model produced.
    """
    weights = np.clip(mask, 0.0, 1.0)
    total = float(weights.sum())
    if total < 50:
        return source

    src_lab = cv2.cvtColor(source, cv2.COLOR_BGR2LAB).astype(np.float32)
    tgt_lab = cv2.cvtColor(target, cv2.COLOR_BGR2LAB).astype(np.float32)

    channel_weight = (1.0, 0.5, 0.5)  # L fully, a and b halfway
    out = src_lab.copy()

    for channel, strength in enumerate(channel_weight):
        src_c = src_lab[:, :, channel]
        tgt_c = tgt_lab[:, :, channel]

        src_mean = float((src_c * weights).sum() / total)
        tgt_mean = float((tgt_c * weights).sum() / total)
        src_std = float(np.sqrt(((src_c - src_mean) ** 2 * weights).sum() / total))
        tgt_std = float(np.sqrt(((tgt_c - tgt_mean) ** 2 * weights).sum() / total))

        if src_std < 1e-3:
            continue
        # Clamp so an odd generation cannot crush or blow out the face.
        ratio = float(np.clip(tgt_std / src_std, 0.6, 1.6))

        shifted = (src_c - src_mean) * ratio + tgt_mean
        out[:, :, channel] = src_c + (shifted - src_c) * strength

    out[:, :, 0] = np.clip(out[:, :, 0], 0, 255)
    out[:, :, 1:] = np.clip(out[:, :, 1:], 0, 255)
    return cv2.cvtColor(out.astype(np.uint8), cv2.COLOR_LAB2BGR)


def apply(
    original: np.ndarray, generated: np.ndarray, cfg
) -> FaceLockResult:
    """Composite the original face onto the generated image."""
    if not cfg.facelock.enabled or cfg.facelock.strength <= 0:
        return FaceLockResult(generated, False, "face lock disabled")

    if original.shape[:2] != generated.shape[:2]:
        original = cv2.resize(
            original, (generated.shape[1], generated.shape[0]),
            interpolation=cv2.INTER_LANCZOS4,
        )

    src_face = facedet.detect(original)
    dst_face = facedet.detect(generated)
    if src_face is None:
        return FaceLockResult(generated, False, "no face found in the original")
    if dst_face is None:
        return FaceLockResult(generated, False, "no face found in the generated image")

    matrix = None
    if src_face.landmarks is not None and dst_face.landmarks is not None:
        matrix = _similarity_from_landmarks(src_face.landmarks, dst_face.landmarks)
    if matrix is None:
        matrix = _similarity_from_eyes(src_face, dst_face)

    height, width = generated.shape[:2]
    warped = cv2.warpAffine(
        original, matrix, (width, height),
        flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE,
    )

    mask = _build_mask(
        dst_face, (height, width),
        float(cfg.facelock.mask_scale), int(cfg.facelock.feather),
    )
    if mask.max() <= 0:
        return FaceLockResult(generated, False, "face mask was empty")

    matched = _match_lighting(warped, generated, mask)

    alpha = (mask * float(cfg.facelock.strength))[:, :, None]
    blended = generated.astype(np.float32) * (1.0 - alpha) + \
        matched.astype(np.float32) * alpha

    return FaceLockResult(np.clip(blended, 0, 255).astype(np.uint8), True)

"""Stage 2: put every face in exactly the same place.

This is what makes the finished set look like one photo session rather than a
folder of unrelated pictures. Each face is rotated so the eyes are level,
scaled so every face is the same width, and shifted so every pair of eyes sits
on the same line.

The same transform is applied twice: once before generation, to hand the model
a consistently framed input, and once afterwards, because image models shift
the composition slightly. Re-aligning at the end means the final geometry is
guaranteed by arithmetic rather than hoped for.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import facedet

# Generation and compositing happen larger than the final export, so the
# downscale at the end adds a little crispness. 2048 wide also matches the
# largest size the free image models return.
WORK_WIDTH = 2048


def work_canvas(cfg) -> tuple[int, int]:
    ratio = cfg.output.height / cfg.output.width
    height = int(round(WORK_WIDTH * ratio))
    return WORK_WIDTH, height + (height % 2)


def canonical_transform(
    face: facedet.Face, canvas_w: int, canvas_h: int, cfg
) -> np.ndarray:
    """Build the 2x3 matrix that moves this face into the standard position."""
    target_face_px = cfg.framing.face_width_ratio * canvas_w
    scale = target_face_px / max(face.width, 1e-6)

    angle = face.roll_degrees if cfg.framing.level_eyes else 0.0

    eye_center = face.eye_center
    matrix = cv2.getRotationMatrix2D(
        (float(eye_center[0]), float(eye_center[1])), angle, scale
    )

    target_x = cfg.framing.center_x * canvas_w
    target_y = cfg.framing.eye_line * canvas_h
    matrix[0, 2] += target_x - eye_center[0]
    matrix[1, 2] += target_y - eye_center[1]
    return matrix


def apply(
    image: np.ndarray, matrix: np.ndarray, canvas_w: int, canvas_h: int
) -> np.ndarray:
    return cv2.warpAffine(
        image,
        matrix,
        (canvas_w, canvas_h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REPLICATE,
    )


def align(
    image: np.ndarray, face: facedet.Face, canvas_w: int, canvas_h: int, cfg
) -> tuple[np.ndarray, np.ndarray]:
    """Return the aligned image and the transform used to produce it."""
    matrix = canonical_transform(face, canvas_w, canvas_h, cfg)
    return apply(image, matrix, canvas_w, canvas_h), matrix


def align_detected(
    image: np.ndarray, canvas_w: int, canvas_h: int, cfg
) -> tuple[np.ndarray, facedet.Face] | None:
    """Detect the face in `image` and align it in one step."""
    face = facedet.detect(image)
    if face is None:
        return None
    aligned, _ = align(image, face, canvas_w, canvas_h, cfg)
    return aligned, face


def measure_eye_line(image: np.ndarray) -> float | None:
    """Where the eyes actually sit, as a fraction of image height.

    Used by the quality check to prove the framing really is consistent.
    """
    face = facedet.detect(image)
    if face is None:
        return None
    return float(face.eye_center[1] / image.shape[0])


def transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Move landmark coordinates through the same transform as the image."""
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.transform(pts, matrix).reshape(-1, 2)

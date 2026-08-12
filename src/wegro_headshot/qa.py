"""Stage 5b: prove the finished photo is still the same person.

Two measures, in order of preference:

  1. SFace face recognition, the same kind of comparison a face-unlock system
     makes. Scores are cosine similarity: above roughly 0.36 means "same
     person", so the default threshold of 0.45 leaves comfortable margin.
  2. A structural comparison of the face region, used only if the recognition
     model is missing. It proves the face was not replaced or badly warped, but
     it is not identity recognition. Every run reports which one was used.

Anything below the threshold is quarantined rather than published, so a face
that drifted cannot reach the website unnoticed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from . import facedet, models

_recognizer = None
_recognizer_tried = False

CROP_SIZE = 112


@dataclass
class QAResult:
    passed: bool
    similarity: float | None
    method: str
    reasons: list[str] = field(default_factory=list)
    eye_line: float | None = None


# ------------------------------------------------------------- face crops

# The recognition model expects a tight crop in which the face fills most of
# the frame. Covering 1.3x the face width puts it at about 80% of the crop,
# which is what the model was trained on.
CROP_COVERAGE = 1.3
CROP_EYE_LINE = 0.40


def _crop_face(image: np.ndarray, face: facedet.Face, size: int = CROP_SIZE) -> np.ndarray:
    """A standard, eye-levelled square crop in which the face fills the frame."""
    center = face.eye_center
    scale = size / (max(face.width, 1.0) * CROP_COVERAGE)

    matrix = cv2.getRotationMatrix2D(
        (float(center[0]), float(center[1])), face.roll_degrees, scale
    )
    matrix[0, 2] += size / 2 - center[0]
    matrix[1, 2] += size * CROP_EYE_LINE - center[1]
    return cv2.warpAffine(
        image, matrix, (size, size),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE,
    )


# ------------------------------------------------------------- recognition

def _get_recognizer():
    global _recognizer, _recognizer_tried
    if _recognizer_tried:
        return _recognizer
    _recognizer_tried = True
    if not models.available("sface"):
        return None
    try:
        _recognizer = cv2.FaceRecognizerSF.create(str(models.path("sface")), "")
    except Exception:
        _recognizer = None
    return _recognizer


def _recognition_similarity(
    recognizer, original: np.ndarray, final: np.ndarray,
    src_face: facedet.Face, dst_face: facedet.Face,
) -> float | None:
    try:
        src = recognizer.feature(_crop_face(original, src_face))
        dst = recognizer.feature(_crop_face(final, dst_face))
        score = recognizer.match(src, dst, cv2.FaceRecognizerSF_DISTYPE_FR_COSINE)
    except Exception:
        return None
    return max(0.0, min(1.0, float(score)))


# -------------------------------------------------------------- structural

def _ssim(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2

    mu_a = cv2.GaussianBlur(a, (11, 11), 1.5)
    mu_b = cv2.GaussianBlur(b, (11, 11), 1.5)
    mu_a2, mu_b2, mu_ab = mu_a * mu_a, mu_b * mu_b, mu_a * mu_b

    sigma_a = cv2.GaussianBlur(a * a, (11, 11), 1.5) - mu_a2
    sigma_b = cv2.GaussianBlur(b * b, (11, 11), 1.5) - mu_b2
    sigma_ab = cv2.GaussianBlur(a * b, (11, 11), 1.5) - mu_ab

    numerator = (2 * mu_ab + c1) * (2 * sigma_ab + c2)
    denominator = (mu_a2 + mu_b2 + c1) * (sigma_a + sigma_b + c2)
    return float(np.mean(numerator / np.maximum(denominator, 1e-8)))


def _structural_similarity(
    original: np.ndarray, final: np.ndarray,
    src_face: facedet.Face, dst_face: facedet.Face,
) -> float:
    a = cv2.cvtColor(_crop_face(original, src_face), cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(_crop_face(final, dst_face), cv2.COLOR_BGR2GRAY)
    # Even out exposure, so relighting is not mistaken for a different person.
    a, b = cv2.equalizeHist(a), cv2.equalizeHist(b)
    return max(0.0, min(1.0, _ssim(a, b)))


# ---------------------------------------------------------------- the check

def check(original: np.ndarray, final: np.ndarray, cfg,
          flags: list[str] | None = None) -> QAResult:
    """Compare the finished image against the employee's original photo."""
    reasons: list[str] = []

    src_face = facedet.detect(original)
    dst_face = facedet.detect(final)

    if dst_face is None:
        return QAResult(False, None, "none",
                        ["No face could be found in the finished image."])
    if src_face is None:
        return QAResult(False, None, "none",
                        ["No face could be found in the original photo."])

    if dst_face.total_faces > 1:
        reasons.append("More than one face appears in the finished image.")

    similarity = None
    method = "structural"
    recognizer = _get_recognizer()
    if recognizer is not None:
        similarity = _recognition_similarity(
            recognizer, original, final, src_face, dst_face
        )
        if similarity is not None:
            method = "sface"

    if similarity is None:
        similarity = _structural_similarity(original, final, src_face, dst_face)

    threshold = float(cfg.qa.min_face_similarity)
    if similarity < threshold:
        reasons.append(
            f"The face only scored {similarity:.2f} against the original "
            f"(needs {threshold:.2f}). It may not look like the right person."
        )

    eye_line = float(dst_face.eye_center[1] / final.shape[0])
    if abs(eye_line - float(cfg.framing.eye_line)) > float(cfg.qa.eye_line_tolerance):
        reasons.append(
            f"The eyes sit at {eye_line:.3f} instead of "
            f"{float(cfg.framing.eye_line):.3f}, so this photo will not line up "
            "with the others."
        )

    return QAResult(
        passed=not reasons,
        similarity=similarity,
        method=method,
        reasons=reasons,
        eye_line=eye_line,
    )


def method_note() -> str:
    return ("SFace identity matching"
            if _get_recognizer() is not None
            else "structural comparison (identity model not installed)")

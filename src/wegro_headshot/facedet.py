"""Face detection and landmarks.

MediaPipe's FaceLandmarker is preferred: its 468-point mesh gives the precise
face outline that the face-lock stage depends on. OpenCV's YuNet detector is
the fallback - it only returns a box and five points, which is enough to level
the eyes and frame the crop, but produces a coarser face-lock mask.

Both need a model file, downloaded once by setup.bat.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from . import models

# MediaPipe face-mesh landmark groups.
LEFT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
RIGHT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379,
    378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127,
    162, 21, 54, 103, 67, 109,
]
NOSE_TIP = 1
MOUTH_LEFT, MOUTH_RIGHT = 61, 291
CHEEK_LEFT, CHEEK_RIGHT = 234, 454


class FaceModelMissing(RuntimeError):
    """No face model is installed, so nothing can be processed."""


@dataclass
class Face:
    """A detected face, in image coordinates.

    `left_eye` is always the eye nearer the left edge of the picture, so the
    roll angle has a consistent sign whichever detector produced it.
    """

    left_eye: np.ndarray
    right_eye: np.ndarray
    width: float                     # cheek to cheek, pixels
    bbox: tuple[int, int, int, int]
    landmarks: np.ndarray | None = None   # (468, 2) with MediaPipe
    nose: np.ndarray | None = None
    mouth_left: np.ndarray | None = None
    mouth_right: np.ndarray | None = None
    total_faces: int = 1

    def __post_init__(self) -> None:
        if self.left_eye[0] > self.right_eye[0]:
            self.left_eye, self.right_eye = self.right_eye, self.left_eye

    @property
    def eye_center(self) -> np.ndarray:
        return (self.left_eye + self.right_eye) / 2.0

    @property
    def roll_degrees(self) -> float:
        """Head tilt in degrees; positive means the head leans clockwise."""
        delta = self.right_eye - self.left_eye
        return float(np.degrees(np.arctan2(delta[1], delta[0])))

    def oval(self) -> np.ndarray | None:
        if self.landmarks is None:
            return None
        return self.landmarks[FACE_OVAL].astype(np.float32)


class _MediaPipeBackend:
    name = "mediapipe face mesh"
    precise = True

    def __init__(self) -> None:
        import mediapipe as mp

        model_path = models.path("face_landmarker")
        if not models.available("face_landmarker"):
            raise FileNotFoundError(model_path)

        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_faces=5,
            min_face_detection_confidence=0.4,
        )
        self._mp = mp
        self._landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)

    def detect(self, bgr: np.ndarray) -> Face | None:
        h, w = bgr.shape[:2]
        image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)),
        )
        result = self._landmarker.detect(image)
        if not result.face_landmarks:
            return None

        meshes = [
            np.array([(lm.x * w, lm.y * h) for lm in mesh[:468]], dtype=np.float32)
            for mesh in result.face_landmarks
        ]
        # Largest face wins, so a colleague in the background cannot hijack the crop.
        pts = max(meshes, key=lambda p: np.ptp(p[:, 0]) * np.ptp(p[:, 1]))

        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        return Face(
            left_eye=pts[LEFT_EYE].mean(axis=0),
            right_eye=pts[RIGHT_EYE].mean(axis=0),
            width=float(np.linalg.norm(pts[CHEEK_RIGHT] - pts[CHEEK_LEFT])),
            bbox=(int(x0), int(y0), int(x1 - x0), int(y1 - y0)),
            landmarks=pts,
            nose=pts[NOSE_TIP],
            mouth_left=pts[MOUTH_LEFT],
            mouth_right=pts[MOUTH_RIGHT],
            total_faces=len(meshes),
        )


class _YuNetBackend:
    name = "opencv yunet"
    precise = False

    def __init__(self) -> None:
        if not models.available("yunet"):
            raise FileNotFoundError(models.path("yunet"))
        self._detector = cv2.FaceDetectorYN.create(
            str(models.path("yunet")), "", (320, 320), 0.6, 0.3, 5000
        )

    def detect(self, bgr: np.ndarray) -> Face | None:
        h, w = bgr.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(bgr)
        if faces is None or len(faces) == 0:
            return None

        row = max(faces, key=lambda r: r[2] * r[3])
        x, y, bw, bh = row[:4]
        # Columns 4..13 are five landmark pairs: two eyes, nose, two mouth corners.
        points = row[4:14].reshape(5, 2).astype(np.float32)

        return Face(
            left_eye=points[0],
            right_eye=points[1],
            width=float(bw),
            bbox=(int(x), int(y), int(bw), int(bh)),
            landmarks=None,
            nose=points[2],
            mouth_left=points[3],
            mouth_right=points[4],
            total_faces=len(faces),
        )


_backends: dict[str, object] | None = None

# How much context to include around a located face before re-running the mesh.
_CROP_PADDING = 2.4


def _build_backends() -> dict[str, object]:
    global _backends
    if _backends is not None:
        return _backends

    built: dict[str, object] = {}
    problems = []
    for key, builder in (("mesh", _MediaPipeBackend), ("yunet", _YuNetBackend)):
        try:
            built[key] = builder()
        except Exception as exc:
            problems.append(f"{builder.name}: {exc}")

    if not built:
        raise FaceModelMissing(
            "No face detection model could be loaded. Run setup.bat to download "
            "the models.\nDetails: " + "; ".join(problems)
        )

    _backends = built
    return _backends


def _offset(face: Face, dx: int, dy: int, total: int) -> Face:
    """Move a face detected in a crop back into full-image coordinates."""
    shift = np.array([dx, dy], dtype=np.float32)
    x, y, w, h = face.bbox
    return Face(
        left_eye=face.left_eye + shift,
        right_eye=face.right_eye + shift,
        width=face.width,
        bbox=(x + dx, y + dy, w, h),
        landmarks=None if face.landmarks is None else face.landmarks + shift,
        nose=None if face.nose is None else face.nose + shift,
        mouth_left=None if face.mouth_left is None else face.mouth_left + shift,
        mouth_right=None if face.mouth_right is None else face.mouth_right + shift,
        total_faces=total,
    )


def detect(bgr: np.ndarray) -> Face | None:
    """Find the main face, with a second attempt for small faces.

    The mesh model shrinks the picture before looking, so a face that is only
    a small part of a large photograph - somebody standing in a garden, say -
    can be missed entirely. When that happens the lightweight detector locates
    the head first, and the mesh is then run again on just that region, which
    keeps the precise landmarks the rest of the pipeline needs.
    """
    backends = _build_backends()
    mesh = backends.get("mesh")
    yunet = backends.get("yunet")

    if mesh is not None:
        face = mesh.detect(bgr)
        if face is not None:
            return face

    if yunet is None:
        return None

    located = yunet.detect(bgr)
    if located is None or mesh is None:
        return located

    height, width = bgr.shape[:2]
    x, y, w, h = located.bbox
    cx, cy = x + w / 2.0, y + h / 2.0
    half = max(w, h) * _CROP_PADDING / 2.0

    x0 = max(0, int(cx - half))
    y0 = max(0, int(cy - half))
    x1 = min(width, int(cx + half))
    y1 = min(height, int(cy + half))
    if x1 - x0 < 32 or y1 - y0 < 32:
        return located

    crop = bgr[y0:y1, x0:x1]
    # Small crops are enlarged so the mesh has enough pixels to work with.
    scale = 1.0
    if max(crop.shape[:2]) < 512:
        scale = 512 / max(crop.shape[:2])
        crop = cv2.resize(crop, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC)

    refined = mesh.detect(crop)
    if refined is None:
        return located

    if scale != 1.0:
        refined = Face(
            left_eye=refined.left_eye / scale,
            right_eye=refined.right_eye / scale,
            width=refined.width / scale,
            bbox=tuple(int(v / scale) for v in refined.bbox),
            landmarks=None if refined.landmarks is None else refined.landmarks / scale,
            nose=None if refined.nose is None else refined.nose / scale,
            mouth_left=None if refined.mouth_left is None else refined.mouth_left / scale,
            mouth_right=None if refined.mouth_right is None else refined.mouth_right / scale,
        )

    return _offset(refined, x0, y0, located.total_faces)


def backend_name() -> str:
    try:
        names = [b.name for b in _build_backends().values()]
    except FaceModelMissing:
        return "none installed"
    return " + ".join(names)


def has_landmarks() -> bool:
    try:
        return "mesh" in _build_backends()
    except FaceModelMissing:
        return False

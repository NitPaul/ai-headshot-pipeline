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


_backend = None
_backend_error: str | None = None


def get_backend():
    """Build the detector once; loading these models is slow."""
    global _backend, _backend_error
    if _backend is not None:
        return _backend

    problems = []
    for builder in (_MediaPipeBackend, _YuNetBackend):
        try:
            _backend = builder()
            return _backend
        except Exception as exc:
            problems.append(f"{builder.name}: {exc}")

    _backend_error = "; ".join(problems)
    raise FaceModelMissing(
        "No face detection model could be loaded. Run setup.bat to download "
        f"the models.\nDetails: {_backend_error}"
    )


def detect(bgr: np.ndarray) -> Face | None:
    return get_backend().detect(bgr)


def backend_name() -> str:
    try:
        return get_backend().name
    except FaceModelMissing:
        return "none installed"


def has_landmarks() -> bool:
    try:
        return get_backend().precise
    except FaceModelMissing:
        return False

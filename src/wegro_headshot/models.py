"""Small machine-learning models the tool depends on.

They are downloaded once by setup.bat rather than shipped, so the project
folder stays small enough to copy around or put in version control.
"""

from __future__ import annotations

import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"


@dataclass(frozen=True)
class ModelSpec:
    filename: str
    url: str
    min_bytes: int
    purpose: str
    required: bool


MODELS: dict[str, ModelSpec] = {
    # 468-point face mesh. Drives the crop geometry and the face-lock mask.
    "face_landmarker": ModelSpec(
        "face_landmarker.task",
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/1/face_landmarker.task",
        1_000_000,
        "precise face landmarks",
        required=True,
    ),
    # Lightweight face detector, used if the mesh model is unavailable.
    "yunet": ModelSpec(
        "face_detection_yunet.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx",
        100_000,
        "backup face detection",
        required=False,
    ),
    # Face recognition, used to prove the finished face is still the same person.
    "sface": ModelSpec(
        "face_recognition_sface.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx",
        1_000_000,
        "face identity checking",
        required=False,
    ),
}


def path(name: str) -> Path:
    return MODEL_DIR / MODELS[name].filename


def available(name: str) -> bool:
    spec = MODELS[name]
    target = path(name)
    return target.exists() and target.stat().st_size >= spec.min_bytes


_last_percent = -1


def _progress(count: int, block: int, total: int) -> None:
    """Only redraw on a real terminal; piped output would fill with percentages."""
    global _last_percent
    if total <= 0 or not sys.stdout.isatty():
        return
    done = min(100, count * block * 100 // total)
    if done != _last_percent:
        _last_percent = done
        sys.stdout.write(f"\r        {done}%")
        sys.stdout.flush()


def download(name: str, quiet: bool = False) -> bool:
    spec = MODELS[name]
    target = path(name)
    if available(name):
        if not quiet:
            print(f"      {spec.purpose}: already installed")
        return True

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")

    if not quiet:
        print(f"      {spec.purpose}...")
    try:
        urllib.request.urlretrieve(spec.url, partial, None if quiet else _progress)
        if not quiet:
            print()
        if partial.stat().st_size < spec.min_bytes:
            partial.unlink(missing_ok=True)
            return False
        partial.replace(target)
        return True
    except Exception as exc:
        if not quiet:
            print(f"\r      could not download {spec.filename}: {exc}")
        partial.unlink(missing_ok=True)
        return False


def download_all() -> tuple[list[str], list[str]]:
    """Returns (succeeded, failed-and-required)."""
    ok: list[str] = []
    missing_required: list[str] = []
    for name, spec in MODELS.items():
        if download(name):
            ok.append(name)
        elif spec.required:
            missing_required.append(name)
    return ok, missing_required

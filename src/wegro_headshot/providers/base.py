"""The contract every image back-end implements.

Keeping generation behind this interface is what lets the tool switch between
a paid API, a free API and a human working in a browser without any of the
surrounding pipeline changing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import cv2
import numpy as np


class ProviderError(RuntimeError):
    """Generation failed for this one person; the run continues."""


class QuotaExhausted(ProviderError):
    """The daily allowance is used up; the run should stop and resume tomorrow."""


class ModelNotAvailable(ProviderError):
    """The account's plan does not include this model at all.

    Reported by Google as a 429 with `limit: 0`, which looks like a quota
    error but is not one: waiting does not help, because the allowance is
    zero rather than spent.
    """


class SafetyBlocked(ProviderError):
    """The model refused to return an image for this input."""


class AwaitingManualInput(ProviderError):
    """This person is queued for a human to generate.

    Not a failure. The pipeline records it and moves on to the next person.
    """


class ImageProvider(ABC):
    name: str = "base"

    @abstractmethod
    def restyle(
        self, image: np.ndarray, outfit: dict[str, str], employee_id: str
    ) -> np.ndarray:
        """Take an aligned BGR headshot and return it wearing `outfit`.

        The returned image must be BGR, the same size as the input, and sit on
        a plain, evenly lit background so it can be cut out reliably.
        """

    def finish(self) -> str | None:
        """Called once after the run. Returns a note for the summary, if any."""
        return None

    @property
    def model_label(self) -> str:
        return self.name


def fit_to_canvas(bgr: np.ndarray, width: int, height: int) -> np.ndarray:
    """Resize to exactly width x height without distorting the person.

    Back-ends choose their own output resolution, and their aspect ratio can
    differ slightly from the working canvas, so this scales to cover and
    centre-crops rather than stretching. Any small shift it introduces is
    corrected afterwards, when the pipeline re-imposes the framing.
    """
    h, w = bgr.shape[:2]
    if (w, h) == (width, height):
        return bgr

    scale = max(width / w, height / h)
    resized = cv2.resize(
        bgr, (int(np.ceil(w * scale)), int(np.ceil(h * scale))),
        interpolation=cv2.INTER_LANCZOS4,
    )
    y = (resized.shape[0] - height) // 2
    x = (resized.shape[1] - width) // 2
    return resized[y: y + height, x: x + width]

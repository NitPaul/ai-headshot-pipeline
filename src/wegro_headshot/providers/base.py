"""The contract every image back-end implements.

Keeping generation behind this interface is what lets a local GPU back-end be
added later without touching the rest of the pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class ProviderError(RuntimeError):
    """Generation failed for this one person; the run continues."""


class QuotaExhausted(ProviderError):
    """The daily free allowance is used up; the run should stop cleanly."""


class SafetyBlocked(ProviderError):
    """The model refused to return an image for this input."""


class ImageProvider(ABC):
    name: str = "base"

    @abstractmethod
    def restyle(self, image: np.ndarray, outfit: dict[str, str]) -> np.ndarray:
        """Take an aligned BGR headshot and return it wearing `outfit`.

        The returned image must be BGR, the same size as the input, and sit on
        a plain, evenly lit background so it can be cut out reliably.
        """

    @property
    def model_label(self) -> str:
        return self.name

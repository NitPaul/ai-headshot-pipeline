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
    """The daily allowance is used up; the run should stop and resume tomorrow."""


class ModelNotAvailable(ProviderError):
    """The account's plan does not include this model at all.

    Reported by Google as a 429 with `limit: 0`, which looks like a quota
    error but is not one: waiting does not help, because the allowance is
    zero rather than spent.
    """


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

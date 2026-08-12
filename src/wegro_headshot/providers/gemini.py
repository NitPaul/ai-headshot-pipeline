"""Google Gemini image-editing back-end.

Runs on the free Google AI Studio tier. Google no longer publishes fixed
free-tier image quotas, so this module is written to survive hitting them:
per-minute limits are waited out, and a daily limit stops the run cleanly so
the ledger can resume it tomorrow with no repeated work.
"""

from __future__ import annotations

import io
import os
import random
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .base import ImageProvider, ProviderError, QuotaExhausted, SafetyBlocked

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "suit_swap.md"

# Substrings that mean the daily allowance is gone rather than a short burst
# limit. A per-minute limit is worth waiting for; a per-day limit is not.
_DAILY_MARKERS = ("perday", "per day", "requests per day", "daily limit", "quota_limit_value")


def _aspect_ratio_label(width: int, height: int) -> str:
    """Pick the closest aspect ratio the model actually offers."""
    options = {
        "1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4,
        "16:9": 16 / 9, "9:16": 9 / 16, "3:2": 1.5, "2:3": 2 / 3,
    }
    ratio = width / height
    return min(options, key=lambda k: abs(options[k] - ratio))


class GeminiProvider(ImageProvider):
    name = "gemini"

    def __init__(self, cfg: Any):
        self.cfg = cfg
        self._model = cfg.provider.model
        self._used_model = cfg.provider.model
        self._last_call = 0.0

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key or api_key.strip() in ("", "paste_your_key_here"):
            raise ProviderError(
                "No Google API key found.\n"
                "  1. Get a free key at https://aistudio.google.com/apikey\n"
                "  2. Open the file named .env in this folder with Notepad\n"
                "  3. Put your key after GEMINI_API_KEY="
            )

        try:
            from google import genai
        except ImportError as exc:
            raise ProviderError(
                "The google-genai package is missing. Run setup.bat again."
            ) from exc

        self._genai = genai
        self._client = genai.Client(api_key=api_key.strip())
        self._prompt_template = PROMPT_FILE.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ utils

    def _throttle(self) -> None:
        gap = float(self.cfg.provider.throttle_seconds)
        elapsed = time.monotonic() - self._last_call
        if self._last_call and elapsed < gap:
            time.sleep(gap - elapsed)
        self._last_call = time.monotonic()

    def _build_config(self, aspect: str):
        from google.genai import types

        image_config = None
        # image_size is only present on newer SDK builds; asking for 2K when
        # it is available is what keeps the export sharp.
        for kwargs in ({"aspect_ratio": aspect, "image_size": "2K"},
                       {"aspect_ratio": aspect}):
            try:
                image_config = types.ImageConfig(**kwargs)
                break
            except TypeError:
                continue

        return types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=image_config,
        )

    @staticmethod
    def _extract_image(response) -> Image.Image | None:
        parts = getattr(response, "parts", None)
        if not parts:
            candidates = getattr(response, "candidates", None) or []
            if not candidates:
                return None
            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", None) or []

        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                return Image.open(io.BytesIO(inline.data)).convert("RGB")
        return None

    @staticmethod
    def _refusal_reason(response) -> str | None:
        feedback = getattr(response, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            return f"blocked: {feedback.block_reason}"
        for candidate in getattr(response, "candidates", None) or []:
            reason = getattr(candidate, "finish_reason", None)
            if reason and str(reason).upper().endswith(("SAFETY", "PROHIBITED_CONTENT")):
                return f"blocked: {reason}"
        return None

    # ---------------------------------------------------------------- request

    def _call(self, model: str, prompt: str, image: Image.Image, aspect: str):
        self._throttle()
        return self._client.models.generate_content(
            model=model,
            contents=[prompt, image],
            config=self._build_config(aspect),
        )

    def restyle(self, image: np.ndarray, outfit: dict[str, str]) -> np.ndarray:
        height, width = image.shape[:2]
        pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        aspect = _aspect_ratio_label(width, height)
        prompt = self._prompt_template.format(
            suit=outfit["suit"], shirt=outfit["shirt"], tie=outfit["tie"]
        )

        models = [self._model]
        if self.cfg.provider.fallback_model:
            models.append(self.cfg.provider.fallback_model)

        last_error: Exception | None = None
        max_retries = int(self.cfg.provider.max_retries)

        for model in models:
            for attempt in range(max_retries):
                try:
                    response = self._call(model, prompt, pil, aspect)
                except Exception as exc:  # SDK raises a variety of error types
                    last_error = exc
                    text = str(exc).lower()

                    if "429" in text or "resource_exhausted" in text or "quota" in text:
                        if any(marker in text for marker in _DAILY_MARKERS):
                            raise QuotaExhausted(
                                "The free daily image quota is used up. Run this "
                                "again tomorrow - everyone already finished will "
                                "be skipped automatically."
                            ) from exc
                        # Short-burst limit: back off and try again.
                        time.sleep(min(60, 2 ** attempt * 8) + random.uniform(0, 3))
                        continue

                    if any(code in text for code in ("500", "502", "503", "504",
                                                     "unavailable", "timeout")):
                        time.sleep(2 ** attempt + random.uniform(0, 2))
                        continue

                    if "api key" in text or "permission" in text or "401" in text:
                        raise ProviderError(
                            f"The API key was rejected by Google: {exc}"
                        ) from exc

                    break  # anything else: try the fallback model

                refusal = self._refusal_reason(response)
                if refusal:
                    raise SafetyBlocked(
                        f"The model declined to edit this photo ({refusal}). "
                        "Try a different source photo."
                    )

                produced = self._extract_image(response)
                if produced is None:
                    last_error = ProviderError("The model returned no image.")
                    continue

                self._used_model = model
                return self._fit(produced, width, height)

        if isinstance(last_error, QuotaExhausted):
            raise last_error
        raise ProviderError(f"Image generation failed: {last_error}")

    @staticmethod
    def _fit(pil: Image.Image, width: int, height: int) -> np.ndarray:
        """Return the result at exactly the size the pipeline expects.

        The model chooses its own output resolution, and its aspect ratio can
        differ very slightly from the working canvas, so this scales to cover
        and centre-crops rather than stretching the person.
        """
        bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]
        scale = max(width / w, height / h)
        resized = cv2.resize(
            bgr, (int(np.ceil(w * scale)), int(np.ceil(h * scale))),
            interpolation=cv2.INTER_LANCZOS4,
        )
        y = (resized.shape[0] - height) // 2
        x = (resized.shape[1] - width) // 2
        return resized[y: y + height, x: x + width]

    @property
    def model_label(self) -> str:
        return self._used_model

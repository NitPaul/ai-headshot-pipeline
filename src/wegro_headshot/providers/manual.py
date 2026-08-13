"""Generation done by a person, in the Gemini app.

Google's API does not include image generation on the free tier, but a Gemini
subscription does include it in the app. This back-end splits the pipeline at
that seam: the tool prepares a correctly framed image and the exact prompt, a
human generates it in the browser, and the tool takes over again for face
lock, cutting out, compositing and the identity check.

Everything that has to be exact is still done by code. Only the one step that
needs the subscription is done by hand.
"""

from __future__ import annotations

import html
import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .base import AwaitingManualInput, ImageProvider, ProviderError, fit_to_canvas

RESULT_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


class ManualProvider(ImageProvider):
    name = "manual"

    def __init__(self, cfg: Any):
        self.cfg = cfg
        root = cfg.root / cfg.manual.folder
        self.to_generate = root / "1_generate_these"
        self.results = root / "2_put_results_here"
        self.used = root / "_used"
        for folder in (self.to_generate, self.results, self.used):
            folder.mkdir(parents=True, exist_ok=True)

        prompt_file = (
            Path(__file__).resolve().parent.parent / "prompts" / "suit_swap.md"
        )
        self._prompt_template = prompt_file.read_text(encoding="utf-8")
        self._queued: list[str] = []
        self._consumed = 0

    # ------------------------------------------------------------------ paths

    def _find_result(self, employee_id: str) -> Path | None:
        for suffix in RESULT_SUFFIXES:
            candidate = self.results / f"{employee_id}{suffix}"
            if candidate.exists() and candidate.stat().st_size > 1024:
                return candidate
        return None

    def _consume(self, path: Path, employee_id: str) -> None:
        """Move a used result aside so a later re-run asks for a fresh one.

        Without this, changing somebody's source photo would silently reuse the
        old generation. The file is kept rather than deleted, so a result can
        be put back by hand if the compositing needs re-running.
        """
        target = self.used / f"{employee_id}{path.suffix}"
        if target.exists():
            target.unlink()
        shutil.move(str(path), str(target))
        self._consumed += 1

    # ----------------------------------------------------------------- queue

    def _queue(self, image: np.ndarray, outfit: dict[str, str], employee_id: str) -> None:
        prompt = self._prompt_template.format(
            suit=outfit["suit"], shirt=outfit["shirt"], tie=outfit["tie"]
        )
        cv2.imwrite(
            str(self.to_generate / f"{employee_id}.jpg"), image,
            [cv2.IMWRITE_JPEG_QUALITY, 95],
        )
        (self.to_generate / f"{employee_id}.txt").write_text(prompt, encoding="utf-8")
        self._queued.append(employee_id)

    # --------------------------------------------------------------- restyle

    def restyle(
        self, image: np.ndarray, outfit: dict[str, str], employee_id: str
    ) -> np.ndarray:
        height, width = image.shape[:2]

        result_path = self._find_result(employee_id)
        if result_path is None:
            self._queue(image, outfit, employee_id)
            raise AwaitingManualInput(
                f"waiting for you to generate this one in the Gemini app"
            )

        generated = cv2.imread(str(result_path), cv2.IMREAD_COLOR)
        if generated is None:
            raise ProviderError(
                f"'{result_path.name}' could not be read. It may be corrupt or "
                "not really an image. Delete it and generate it again."
            )

        self._consume(result_path, employee_id)

        # The prepared copy is no longer needed once the result is in.
        (self.to_generate / f"{employee_id}.jpg").unlink(missing_ok=True)
        (self.to_generate / f"{employee_id}.txt").unlink(missing_ok=True)

        return fit_to_canvas(generated, width, height)

    # ---------------------------------------------------------------- finish

    def finish(self) -> str | None:
        """Write the worksheet and return a message for the run summary."""
        pending = sorted(p.stem for p in self.to_generate.glob("*.jpg"))
        page = self._write_worksheet(pending)

        if not pending:
            return None
        return (
            f"{len(pending)} photo(s) are waiting for you to generate.\n"
            f"  Open this file and follow the steps:\n"
            f"  {page}\n"
            f"  Then run this tool again to finish them."
        )

    def _write_worksheet(self, pending: list[str]) -> Path:
        cards = []
        for employee_id in pending:
            prompt_file = self.to_generate / f"{employee_id}.txt"
            prompt = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else ""
            cards.append(f"""
    <section class="person">
      <div class="shot">
        <img src="1_generate_these/{html.escape(employee_id)}.jpg" alt="" loading="lazy">
        <p class="who">{html.escape(employee_id)}</p>
      </div>
      <div class="ask">
        <button class="copy" type="button">Copy the instruction</button>
        <pre>{html.escape(prompt)}</pre>
      </div>
    </section>""")

        body = "\n".join(cards) if cards else (
            '<p class="done">Nothing is waiting. Everything has been generated.</p>'
        )

        page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Photos to generate</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ margin:0; padding:32px; font:15px/1.6 system-ui, sans-serif;
         background:#14171a; color:#e8eaed; }}
  h1 {{ margin:0 0 18px; font-size:22px; }}
  ol.steps {{ background:#1d2126; border-left:3px solid #4a90d9; margin:0 0 32px;
             padding:16px 16px 16px 38px; border-radius:4px; max-width:80ch; }}
  ol.steps li {{ margin:6px 0; }}
  code {{ background:#2c323a; padding:1px 6px; border-radius:4px; }}
  .person {{ display:grid; grid-template-columns:260px 1fr; gap:20px;
            background:#1d2126; border:1px solid #2a2f36; border-radius:8px;
            padding:16px; margin-bottom:18px; }}
  .shot img {{ width:100%; border-radius:6px; display:block; background:#000; }}
  .who {{ margin:8px 0 0; font-weight:600; word-break:break-all; }}
  pre {{ white-space:pre-wrap; background:#12151a; border:1px solid #2a2f36;
        border-radius:6px; padding:12px; margin:10px 0 0; font-size:12px;
        max-height:240px; overflow:auto; color:#b9c2cb; }}
  .copy {{ background:#2f6fb3; color:#fff; border:0; border-radius:6px;
          padding:9px 16px; font-size:14px; cursor:pointer; }}
  .copy:hover {{ background:#3a82ce; }}
  .copy.ok {{ background:#3f8f4a; }}
  .done {{ color:#7fba7a; font-size:17px; }}
  @media (max-width:720px) {{ .person {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
  <h1>Photos to generate &mdash; {len(pending)} waiting</h1>
  <ol class="steps">
    <li>Open <a href="https://gemini.google.com">gemini.google.com</a> and sign
        in with the account that has the Gemini subscription.</li>
    <li>For each person below: click <b>Copy the instruction</b>.</li>
    <li>In Gemini, attach that person's picture from the
        <code>1_generate_these</code> folder, paste the instruction, and send.</li>
    <li>Download the picture Gemini gives back.</li>
    <li>Save it into <code>2_put_results_here</code> named exactly
        <code>&lt;the same name&gt;.png</code> &mdash; for example
        <code>alvi-rahman.png</code>.</li>
    <li>When you have done as many as you want, run <code>run.bat</code> again.</li>
  </ol>
{body}
<script>
document.querySelectorAll('.copy').forEach(function (button) {{
  button.addEventListener('click', function () {{
    var text = button.parentElement.querySelector('pre').textContent;
    navigator.clipboard.writeText(text).then(function () {{
      button.textContent = 'Copied';
      button.classList.add('ok');
      setTimeout(function () {{
        button.textContent = 'Copy the instruction';
        button.classList.remove('ok');
      }}, 1600);
    }});
  }});
}});
</script>
</body>
</html>"""

        path = self.cfg.root / self.cfg.manual.folder / "START_HERE.html"
        path.write_text(page, encoding="utf-8")
        return path

    @property
    def model_label(self) -> str:
        return "manual (Gemini app)"

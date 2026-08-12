"""Runs every stage for every employee, and keeps the ledger honest.

Each person is processed independently and the ledger is saved after each one,
so an interrupted run - a crash, a closed window, an exhausted daily quota -
never costs more than the person in progress.
"""

from __future__ import annotations

import re
import shutil
import traceback
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from . import align, compose, cutout, export, facelock, normalize, palette, qa, review
from .manifest import (
    STATUS_FAILED,
    STATUS_FINAL,
    STATUS_NEEDS_ATTENTION,
    Manifest,
    Record,
    file_sha256,
    slugify,
)
from .providers.base import ModelNotAvailable, ProviderError, QuotaExhausted

FLAG_FACELOCK_SKIPPED = "FACELOCK_SKIPPED"
FLAG_COLOUR_KEY = "BASIC_CUTOUT"
FLAG_REALIGN_FAILED = "REALIGN_FAILED"


@dataclass
class Outcome:
    processed: int = 0
    skipped: int = 0
    attention: int = 0
    failed: int = 0
    remaining: int = 0
    stopped_reason: str | None = None


class Pipeline:
    def __init__(self, cfg, provider, manifest: Manifest, log):
        self.cfg = cfg
        self.provider = provider
        self.manifest = manifest
        self.log = log
        self.work_w, self.work_h = align.work_canvas(cfg)
        self._plate: np.ndarray | None = None

    @property
    def plate(self) -> np.ndarray:
        if self._plate is None:
            self._plate = compose.build_plate(self.cfg, self.work_w, self.work_h)
        return self._plate

    # ------------------------------------------------------------- discovery

    def find_inputs(self) -> list[Path]:
        inbox = self.cfg.path("inbox")
        extensions = {e.lower() for e in self.cfg.input.extensions}
        files = [
            p for p in sorted(inbox.iterdir())
            if p.is_file() and p.suffix.lower() in extensions
        ]
        return files

    # --------------------------------------------------------------- helpers

    def _work_dir(self, employee_id: str) -> Path:
        path = self.cfg.path("working") / employee_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _save_step(self, employee_id: str, name: str, image: np.ndarray) -> None:
        if not self.cfg.keep_intermediates:
            return
        cv2.imwrite(str(self._work_dir(employee_id) / name), image)

    def _quarantine(self, employee_id: str, image: np.ndarray, reason: str) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", reason.lower())[:60].strip("-")
        target = self.cfg.path("needs_attention") / f"{employee_id}__{slug}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(target), image)
        return target

    def _clear_previous_outputs(self, employee_id: str) -> None:
        """Stop a stale pass or fail from lingering when someone is redone."""
        for path in export.expected_outputs(employee_id, self.cfg):
            path.unlink(missing_ok=True)
        for path in self.cfg.path("needs_attention").glob(f"{employee_id}__*.png"):
            path.unlink(missing_ok=True)

    # --------------------------------------------------------------- one job

    def process_one(self, path: Path, record: Record) -> Record:
        employee_id = record.employee_id
        flags = list(record.flags)

        # 1. clean up the source photo and find the face
        source, face, norm_flags = normalize.normalize(path, self.cfg)
        flags += norm_flags
        self._save_step(employee_id, "01_normalized.png", source)

        # 2. put the face in the standard position
        aligned, _ = align.align(source, face, self.work_w, self.work_h, self.cfg)
        self._save_step(employee_id, "02_aligned.png", aligned)

        # 3. the only AI step: give them a suit
        outfit_index, outfit = palette.choose_outfit(self.cfg, employee_id)
        record.outfit_index = outfit_index
        self.log.detail(f"    outfit: {palette.describe(outfit)}")

        generated = self.provider.restyle(aligned, outfit)
        record.model = self.provider.model_label
        self._save_step(employee_id, "03_generated.png", generated)

        # 4. put their real face back on the generated body
        locked = facelock.apply(aligned, generated, self.cfg)
        if not locked.applied and self.cfg.facelock.enabled:
            flags.append(FLAG_FACELOCK_SKIPPED)
            self.log.warn(f"    face lock skipped: {locked.note}")
        self._save_step(employee_id, "04_facelocked.png", locked.image)

        # 5. re-impose the standard framing, because image models drift
        realigned = align.align_detected(
            locked.image, self.work_w, self.work_h, self.cfg
        )
        if realigned is None:
            flags.append(FLAG_REALIGN_FAILED)
            final_person = locked.image
        else:
            final_person, _ = realigned

        # 6. cut the person out of the plain backdrop
        rgba, method = cutout.cut_out(final_person)
        if method != "rembg":
            flags.append(FLAG_COLOUR_KEY)
        self._save_step(employee_id, "05_cutout.png", rgba)

        # 7. place them on the brand background
        composite = compose.composite(rgba, self.plate, self.cfg)

        # 8. prove it is still the same person
        result = qa.check(aligned, composite, self.cfg, flags)
        record.face_similarity = result.similarity
        record.flags = sorted(set(flags))

        review.write_comparison(
            aligned, composite, employee_id, result.similarity, self.cfg
        )

        if result.passed:
            self._clear_previous_outputs(employee_id)
            record.outputs = [
                str(p.relative_to(self.cfg.root))
                for p in export.export(composite, employee_id, self.cfg)
            ]
            record.status = STATUS_FINAL
            record.reason = None
        else:
            reason = " ".join(result.reasons)
            self._clear_previous_outputs(employee_id)
            if self.cfg.qa.quarantine_failures:
                self._quarantine(employee_id, composite, result.reasons[0])
            record.status = STATUS_NEEDS_ATTENTION
            record.reason = reason
            record.outputs = []

        record.stamp()
        return record

    # ------------------------------------------------------------------- run

    def run(
        self, *, force: set[str] | None = None, only: set[str] | None = None,
        limit: int | None = None, dry_run: bool = False,
    ) -> Outcome:
        outcome = Outcome()
        force = force or set()
        files = self.find_inputs()

        if not files:
            self.log.warn(
                f"No photos found in {self.cfg.paths['inbox']}. "
                "Put employee photos there and run again."
            )
            return outcome

        seen: dict[str, Path] = {}
        queue: list[tuple[Path, str, str]] = []

        for path in files:
            employee_id = slugify(path.name)

            if employee_id in seen:
                kept = seen[employee_id]
                # If one of the two is the file this person was processed from
                # before, keep that one. A stray copy must not silently take
                # over an employee who is already done.
                record = self.manifest.get(employee_id)
                if record is not None and path.name == record.source_file:
                    seen[employee_id] = path
                    kept, path = path, kept
                self.log.warn(
                    f"Skipping '{path.name}' - it becomes the same name as "
                    f"'{kept.name}' ({employee_id}), so one would overwrite the "
                    "other. Rename one of them."
                )
                continue
            seen[employee_id] = path

            if only and employee_id not in only:
                continue

            sha = file_sha256(path)
            expected = export.expected_outputs(employee_id, self.cfg)

            if employee_id not in force and self.manifest.should_skip(
                employee_id, sha, expected
            ):
                outcome.skipped += 1
                continue

            queue.append((path, employee_id, sha))

        self.log.info(
            f"{len(files)} photo(s) in the inbox: "
            f"{outcome.skipped} already done, {len(queue)} to process."
        )

        if limit is not None and len(queue) > limit:
            queue = queue[:limit]

        if dry_run:
            for _, employee_id, _ in queue:
                index, outfit = palette.choose_outfit(self.cfg, employee_id)
                self.log.detail(f"  would process {employee_id} - {palette.describe(outfit)}")
            outcome.remaining = len(queue)
            return outcome

        for position, (path, employee_id, sha) in enumerate(queue, start=1):
            self.log.step(f"[{position}/{len(queue)}] {employee_id}")
            record = self.manifest.begin_version(employee_id, path.name, sha)

            try:
                record = self.process_one(path, record)

            except (QuotaExhausted, ModelNotAvailable) as exc:
                # Neither is this photo's fault, and both affect every
                # remaining person, so stop rather than repeat the failure.
                outcome.remaining = len(queue) - position + 1
                outcome.stopped_reason = str(exc)
                self.manifest.save()
                return outcome

            except (normalize.NoFaceFound, ProviderError) as exc:
                record.status = STATUS_FAILED
                record.reason = str(exc)
                record.stamp()
                self.log.error(f"    {exc}")

            except Exception as exc:  # noqa: BLE001 - one bad photo must not stop the batch
                record.status = STATUS_FAILED
                record.reason = f"Unexpected error: {exc}"
                record.stamp()
                self.log.error(f"    unexpected error: {exc}")
                self.log.debug(traceback.format_exc())

            self.manifest.put(record)
            self.manifest.save()

            if record.status == STATUS_FINAL:
                outcome.processed += 1
                self.log.ok(f"    done  (face match {record.face_similarity:.2f})")
            elif record.status == STATUS_NEEDS_ATTENTION:
                outcome.attention += 1
                self.log.warn(f"    needs attention: {record.reason}")
            else:
                outcome.failed += 1

        return outcome

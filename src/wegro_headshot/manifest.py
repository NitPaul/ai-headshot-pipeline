"""The processing ledger.

This is what makes the tool safe to re-run and what stops employees being
processed twice. Every person is keyed by a slug derived from their file name,
and their source photo is fingerprinted with SHA-256.

  same slug + same fingerprint  -> already done, skip (no API call)
  same slug + new fingerprint   -> they sent a new photo, redo as a new version
  new slug                      -> new employee, process
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1

STATUS_FINAL = "final"
STATUS_NEEDS_ATTENTION = "needs_attention"
STATUS_FAILED = "failed"
STATUS_AWAITING = "awaiting_generation"


def slugify_text(text: str) -> str:
    """'Md. Golam Rabbe Bhuiyan' -> 'md-golam-rabbe-bhuiyan'.

    For plain text such as a person's name. Unlike `slugify` it does not treat
    a dot as the start of a file extension, which would cut 'Md. Golam' down
    to 'md'.
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "unnamed"


def slugify(name: str) -> str:
    """'John  Doe (HR).JPG' -> 'john-doe-hr'. Strips the file extension."""
    return slugify_text(Path(name).stem)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class Record:
    employee_id: str
    source_file: str
    source_sha256: str
    version: int = 1
    status: str = STATUS_FAILED
    outfit_index: int | None = None
    face_similarity: float | None = None
    flags: list[str] = field(default_factory=list)
    reason: str | None = None
    model: str | None = None
    processed_at: str | None = None
    outputs: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "employee_id": self.employee_id,
            "source_file": self.source_file,
            "source_sha256": self.source_sha256,
            "version": self.version,
            "status": self.status,
            "outfit_index": self.outfit_index,
            "face_similarity": self.face_similarity,
            "flags": self.flags,
            "reason": self.reason,
            "model": self.model,
            "processed_at": self.processed_at,
            "outputs": self.outputs,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Record":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def stamp(self) -> None:
        self.processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.employees: dict[str, Record] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt ledger must not destroy finished work. Keep a copy and
            # start fresh; already-exported files in 05_final are untouched.
            backup = self.path.with_suffix(".corrupt.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            return
        for key, value in (data.get("employees") or {}).items():
            self.employees[key] = Record.from_dict(value)

    def save(self) -> None:
        payload = {
            "version": MANIFEST_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "employees": {k: v.to_dict() for k, v in sorted(self.employees.items())},
        }
        # Write to a temporary file first so an interrupted run cannot leave a
        # half-written ledger behind.
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, employee_id: str) -> Record | None:
        return self.employees.get(employee_id)

    def put(self, record: Record) -> None:
        self.employees[record.employee_id] = record

    def should_skip(
        self, employee_id: str, sha: str, expected_outputs: list[Path]
    ) -> bool:
        """True when this exact photo already produced files that still exist."""
        record = self.employees.get(employee_id)
        if record is None:
            return False
        if record.source_sha256 != sha:
            return False
        if record.status != STATUS_FINAL:
            return False
        return all(p.exists() for p in expected_outputs)

    def begin_version(self, employee_id: str, source_file: str, sha: str) -> Record:
        """Create the record for this run, archiving any previous attempt."""
        previous = self.employees.get(employee_id)
        if previous is None:
            return Record(
                employee_id=employee_id, source_file=source_file, source_sha256=sha
            )

        # Same photo, and the last attempt never finished: this is that attempt
        # continuing rather than a new version. Without this, somebody waiting
        # on manual generation would gain a version on every single run.
        if previous.source_sha256 == sha and previous.status != STATUS_FINAL:
            return Record(
                employee_id=employee_id,
                source_file=source_file,
                source_sha256=sha,
                version=previous.version,
                outfit_index=previous.outfit_index,
                history=list(previous.history),
            )

        archived = previous.to_dict()
        archived.pop("history", None)
        history = list(previous.history)
        history.append(archived)

        return Record(
            employee_id=employee_id,
            source_file=source_file,
            source_sha256=sha,
            version=previous.version + 1,
            # A new photograph does not mean a new suit.
            outfit_index=previous.outfit_index,
            history=history[-10:],
        )

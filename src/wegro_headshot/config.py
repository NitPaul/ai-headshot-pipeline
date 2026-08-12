"""Loads config.yaml and exposes it as dotted-access settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class Section(dict):
    """A dict that also allows attribute access, so cfg.output.width works."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _wrap(value: Any) -> Any:
    if isinstance(value, dict):
        return Section({k: _wrap(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_wrap(v) for v in value]
    return value


class Config(Section):
    """Project settings, plus the resolved project root."""

    root: Path

    @classmethod
    def load(cls, root: Path) -> "Config":
        config_path = root / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(
                f"config.yaml not found at {config_path}. "
                "It should sit next to run.bat."
            )
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        cfg = cls(_wrap(raw))
        cfg.root = root
        _validate(cfg)
        return cfg

    def path(self, key: str) -> Path:
        """Resolve one of the configured folders to an absolute path."""
        return self.root / self.paths[key]

    def ensure_dirs(self) -> None:
        for key in ("inbox", "working", "review", "needs_attention", "final", "logs"):
            self.path(key).mkdir(parents=True, exist_ok=True)


def _validate(cfg: Config) -> None:
    """Fail early and in plain language rather than deep inside the pipeline."""
    problems: list[str] = []

    if cfg.output.width < 64 or cfg.output.height < 64:
        problems.append("output.width and output.height must both be at least 64.")

    if not 0.05 <= cfg.framing.eye_line <= 0.95:
        problems.append("framing.eye_line must be between 0.05 and 0.95.")

    if not 0.05 <= cfg.framing.face_width_ratio <= 0.9:
        problems.append("framing.face_width_ratio must be between 0.05 and 0.9.")

    if not 0.0 <= cfg.facelock.strength <= 1.0:
        problems.append("facelock.strength must be between 0.0 and 1.0.")

    if not 0.0 <= cfg.qa.min_face_similarity <= 1.0:
        problems.append("qa.min_face_similarity must be between 0.0 and 1.0.")

    if not cfg.attire.combinations:
        problems.append("attire.combinations must list at least one outfit.")

    plate = cfg.root / cfg.plate.file
    if not plate.exists():
        problems.append(f"Background plate not found: {plate}")

    for name, index in (cfg.attire.overrides or {}).items():
        if not isinstance(index, int) or not 1 <= index <= len(cfg.attire.combinations):
            problems.append(
                f"attire.overrides['{name}'] must be a number between 1 "
                f"and {len(cfg.attire.combinations)}."
            )

    if problems:
        raise ValueError(
            "There are problems in config.yaml:\n  - " + "\n  - ".join(problems)
        )

"""Console output that a designer can read, plus a full log file."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console

    _console = Console()
except Exception:  # rich is a convenience, not a requirement
    _console = None


class Log:
    def __init__(self, log_dir: Path | None = None, verbose: bool = False):
        self.verbose = verbose
        self._file = None
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / f"run-{datetime.now():%Y-%m-%d}.log"
            self._file = path.open("a", encoding="utf-8")
            self._write_file(f"\n===== run started {datetime.now():%H:%M:%S} =====")

    def _write_file(self, text: str) -> None:
        if self._file:
            self._file.write(text + "\n")
            self._file.flush()

    def _emit(self, text: str, style: str | None = None) -> None:
        if _console is not None and style:
            _console.print(text, style=style, highlight=False)
        else:
            print(text)
        self._write_file(text)

    def info(self, text: str) -> None:
        self._emit(text)

    def detail(self, text: str) -> None:
        self._emit(text, "dim")

    def step(self, text: str) -> None:
        self._emit(text, "bold cyan")

    def ok(self, text: str) -> None:
        self._emit(text, "green")

    def warn(self, text: str) -> None:
        self._emit(text, "yellow")

    def error(self, text: str) -> None:
        self._emit(text, "red")

    def debug(self, text: str) -> None:
        self._write_file(text)
        if self.verbose:
            self._emit(text, "dim")

    def rule(self, title: str = "") -> None:
        if _console is not None:
            _console.rule(title)
        else:
            print("-" * 60)
            if title:
                print(title)
        self._write_file(f"--- {title} ---")

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

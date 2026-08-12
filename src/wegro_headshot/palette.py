"""Picks which suit and tie each employee wears.

The CEO wants variety, but a team page still has to look like one company,
so the choice comes from a curated list of professional combinations only.

The choice is derived from the employee's id, not from a random number. That
means re-running the tool always gives the same person the same outfit, and
adding a new employee never disturbs anyone else's.
"""

from __future__ import annotations

import hashlib
from typing import Any


def choose_outfit(cfg: Any, employee_id: str) -> tuple[int, dict[str, str]]:
    """Return (1-based index, outfit) for this employee."""
    combos = cfg.attire.combinations

    override = (cfg.attire.overrides or {}).get(employee_id)
    if override is not None:
        return override, combos[override - 1]

    if not cfg.attire.vary_by_person:
        return 1, combos[0]

    digest = hashlib.sha256(employee_id.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(combos)
    return index + 1, combos[index]


def describe(outfit: dict[str, str]) -> str:
    return f"{outfit['suit']} suit / {outfit['shirt']} shirt / {outfit['tie']} tie"

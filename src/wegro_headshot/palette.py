"""Decides which suit, shirt and tie each employee wears.

Three things have to hold at once:

  * a team page must still look like one company, so only sensible business
    pairings are allowed - never a navy tie on a navy suit,
  * as many people as possible should look different from each other,
  * and nobody's outfit may change when somebody else joins.

The outfit is therefore chosen from the employee's own id, and the choice is
then written into the ledger. Once assigned it is never recalculated, so an
employee keeps the same suit for good. New joiners take the first free
combination starting from their own hash position, which keeps duplicates rare
without disturbing anyone already done.
"""

from __future__ import annotations

import hashlib
from typing import Any

# Colours that read as the same family. A tie is never put on a suit of the
# same family, because the two just merge into one another in a photograph.
_FAMILIES = {
    "navy": "blue", "blue": "blue", "royal": "blue",
    "charcoal": "grey", "grey": "grey", "gray": "grey", "graphite": "grey",
    "steel": "grey", "slate": "grey", "silver": "grey",
    "black": "black",
    "burgundy": "red", "oxblood": "red", "red": "red", "maroon": "red",
    "forest": "green", "green": "green",
    "orange": "orange", "bronze": "orange",
    "gold": "gold", "champagne": "gold",
    "purple": "purple", "plum": "purple",
}


def _family(colour: str) -> str:
    for word in colour.lower().split():
        if word in _FAMILIES:
            return _FAMILIES[word]
    return colour.lower()


def build_space(cfg: Any) -> list[dict[str, str]]:
    """Every acceptable suit/shirt/tie pairing, in a fixed order."""
    combos: list[dict[str, str]] = []
    for suit in cfg.attire.suits:
        for shirt in cfg.attire.shirts:
            for tie in cfg.attire.ties:
                if _family(suit) == _family(tie):
                    continue
                combos.append({"suit": suit, "shirt": shirt, "tie": tie})
    return combos


def _hash_index(employee_id: str, size: int) -> int:
    digest = hashlib.sha256(employee_id.encode("utf-8")).hexdigest()
    return int(digest, 16) % size


def assign(
    cfg: Any, employee_id: str, taken: set[int] | None = None
) -> tuple[int, dict[str, str]]:
    """Pick an outfit for someone who does not have one yet.

    `taken` holds the indexes other employees already own, so this person gets
    a different outfit where one is still available.
    """
    space = build_space(cfg)
    if not space:
        raise ValueError(
            "No valid outfits could be built. Check attire.suits and "
            "attire.ties in config.yaml - every tie may be clashing."
        )

    override = (cfg.attire.overrides or {}).get(employee_id)
    if override:
        outfit = {
            "suit": override.get("suit", space[0]["suit"]),
            "shirt": override.get("shirt", space[0]["shirt"]),
            "tie": override.get("tie", space[0]["tie"]),
        }
        return -1, outfit

    if not cfg.attire.vary_by_person:
        return 0, space[0]

    start = _hash_index(employee_id, len(space))
    taken = taken or set()

    for step in range(len(space)):
        index = (start + step) % len(space)
        if index not in taken:
            return index, space[index]

    # More employees than outfits: duplicates are unavoidable from here.
    return start, space[start]


def resolve(cfg: Any, index: int) -> dict[str, str] | None:
    """Look up an outfit already recorded in the ledger."""
    if index is None or index < 0:
        return None
    space = build_space(cfg)
    if index >= len(space):
        return None
    return space[index]


def describe(outfit: dict[str, str]) -> str:
    return f"{outfit['suit']} suit / {outfit['shirt']} shirt / {outfit['tie']} tie"

"""Downloads the small models the tool needs. Run once by setup.bat."""

from __future__ import annotations

from . import models


def _warm_rembg() -> None:
    """Pull the background-removal model now.

    rembg fetches a 176 MB model the first time it is used. Doing it here keeps
    that download inside setup, instead of surprising the design team in the
    middle of their first run.
    """
    print("      background removal model...")
    try:
        import numpy as np
        from rembg import new_session, remove

        session = new_session("u2net_human_seg")
        remove(np.zeros((32, 32, 4), dtype=np.uint8), session=session)
        print("      background removal model ready.")
    except Exception as exc:
        print(f"      [!] could not prepare background removal ({exc}).")
        print("          The tool will fall back to a simpler cutout method.")


def main() -> int:
    ok, missing_required = models.download_all()
    _warm_rembg()

    if missing_required:
        names = ", ".join(models.MODELS[m].purpose for m in missing_required)
        print(f"      [X] could not download: {names}")
        print("          The tool cannot run without this. Check your internet")
        print("          connection and run setup.bat again.")
        return 1

    optional_missing = [
        spec.purpose for name, spec in models.MODELS.items()
        if not spec.required and name not in ok
    ]
    if optional_missing:
        print(f"      [!] optional model not installed: {', '.join(optional_missing)}")
        print("          The tool will run, with reduced quality checking.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

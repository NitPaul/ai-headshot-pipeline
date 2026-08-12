"""Command line entry point.

The design team only ever double-clicks run.bat with no arguments. The options
below exist for troubleshooting and for redoing individual people.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import __version__, facedet, qa, review
from .config import Config
from .logging_util import Log
from .manifest import STATUS_FINAL, STATUS_NEEDS_ATTENTION, Manifest
from .pipeline import Pipeline
from .providers import build_provider
from .providers.base import ProviderError


def project_root() -> Path:
    # src/wegro_headshot/cli.py -> project root is two levels up from src
    return Path(__file__).resolve().parent.parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.bat",
        description="Turn employee photos into standard WeGro website headshots.",
    )
    parser.add_argument("--force", nargs="+", metavar="NAME",
                        help="Redo these people even if they are already done "
                             "(use the file name without the extension).")
    parser.add_argument("--force-all", action="store_true",
                        help="Redo everybody from scratch. Uses a lot of quota.")
    parser.add_argument("--only", nargs="+", metavar="NAME",
                        help="Process only these people.")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="Stop after N people. Useful for a first test.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without generating anything.")
    parser.add_argument("--provider", choices=["gemini", "stub"],
                        help="Override the AI back-end. 'stub' uses no quota.")
    parser.add_argument("--status", action="store_true",
                        help="Show the current state of everyone and exit.")
    parser.add_argument("--rebuild-review", action="store_true",
                        help="Rebuild the review page without processing anything.")
    parser.add_argument("--verbose", action="store_true", help="Show extra detail.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def show_status(manifest: Manifest, cfg, log: Log) -> None:
    if not manifest.employees:
        log.warn("Nothing has been processed yet.")
        return

    log.rule("Current status")
    for record in sorted(manifest.employees.values(), key=lambda r: r.employee_id):
        score = (f"{record.face_similarity:.2f}"
                 if record.face_similarity is not None else " n/a")
        flags = f"  [{', '.join(record.flags)}]" if record.flags else ""
        line = f"  {record.employee_id:<28} {record.status:<17} match {score}{flags}"
        if record.status == STATUS_FINAL:
            log.ok(line)
        elif record.status == STATUS_NEEDS_ATTENTION:
            log.warn(line)
        else:
            log.error(line)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = project_root()
    load_dotenv(root / ".env")

    try:
        cfg = Config.load(root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"\n{exc}\n")
        return 2

    cfg.ensure_dirs()
    log = Log(cfg.path("logs"), verbose=args.verbose)

    try:
        manifest = Manifest(cfg.root / cfg.paths["manifest"])

        if args.status:
            show_status(manifest, cfg, log)
            return 0

        if args.rebuild_review:
            path = review.write_contact_sheet(manifest, cfg)
            log.ok(f"Review page rebuilt: {path}")
            return 0

        if args.provider:
            cfg.provider["name"] = args.provider

        log.rule(f"WeGro headshots  v{__version__}")
        log.detail(f"  face detection: {facedet.backend_name()}")
        log.detail(f"  quality check:  {qa.method_note()}")

        try:
            provider = build_provider(cfg)
        except ProviderError as exc:
            log.error(f"\n{exc}\n")
            return 2

        log.detail(f"  image model:    {provider.model_label}")
        log.info("")

        force = set(args.force or [])
        if args.force_all:
            force = {r.employee_id for r in manifest.employees.values()}

        pipeline = Pipeline(cfg, provider, manifest, log)
        outcome = pipeline.run(
            force=force,
            only=set(args.only) if args.only else None,
            limit=args.limit,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            log.info(f"\nDry run: {outcome.remaining} person(s) would be processed.")
            return 0

        if manifest.employees:
            sheet = review.write_contact_sheet(manifest, cfg)
        else:
            sheet = None

        log.info("")
        log.rule("Summary")
        log.ok(f"  ready for the website : {outcome.processed}")
        log.detail(f"  already done, skipped : {outcome.skipped}")
        if outcome.attention:
            log.warn(f"  need a human look     : {outcome.attention}")
        if outcome.failed:
            log.error(f"  could not be done     : {outcome.failed}")

        if outcome.stopped_reason:
            log.info("")
            log.warn(f"  {outcome.stopped_reason}")
            log.warn(f"  {outcome.remaining} person(s) still waiting.")

        log.info("")
        if outcome.processed or outcome.attention:
            log.info(f"  Finished photos : {cfg.path('final')}")
            if sheet:
                log.info(f"  Check them here : {sheet}")
        if outcome.attention:
            log.info(f"  Needs attention : {cfg.path('needs_attention')}")

        return 0

    except KeyboardInterrupt:
        log.warn("\nStopped. Everything finished so far has been saved.")
        return 130
    finally:
        log.close()


if __name__ == "__main__":
    sys.exit(main())

"""Command line tools.

    python -m app.cli import            # import library + plan (backs up the DB first)
    python -m app.cli import --profile Abby --no-library --plan abby_plan.zip
    python -m app.cli import --check    # validate the sources without changing anything
    python -m app.cli seed-if-empty     # first-run import (used by the Docker entrypoint)
    python -m app.cli backup            # copy the database to data/backups/
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_factory
from app.models import Exercise, Profile
from app.services.backup import backup_database
from app.services.importer import ImportAborted, run_import


def _default_library() -> Path:
    return get_settings().seed_path.parent / "home_gym_exercises_verified.csv"


def _profile_id(name: str | None) -> int | None:
    """Resolve --profile (case-insensitive); None means the default owner profile."""
    if name is None:
        return None
    with session_factory()() as db:
        profiles = list(db.scalars(select(Profile)))
    match = next((p for p in profiles if p.name.lower() == name.strip().lower()), None)
    if match is None:
        raise SystemExit(f"Unknown profile '{name}'. Profiles: {', '.join(p.name for p in profiles)}")
    return match.id


def _import(args: argparse.Namespace) -> int:
    settings = get_settings()
    library = None if args.no_library else Path(args.library or _default_library())
    plan = None if args.no_plan else Path(args.plan or settings.seed_path)
    profile_id = _profile_id(args.profile)

    if args.check:
        # Run the full import against a throwaway transaction and media dir.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp, session_factory()() as db:
            try:
                report = run_import(db, library_path=library, plan_path=plan, media_dir=Path(tmp),
                                    sync_templates=not args.exercises_only, profile_id=profile_id)
            except ImportAborted as exc:
                print(exc.report.summary())
                return 1
            finally:
                db.rollback()
        print("Check only - nothing was saved.\n" + report.summary())
        return 0

    if not args.no_backup:
        path = backup_database("pre-import")
        if path:
            print(f"Backup written to {path}")
    with session_factory()() as db:
        try:
            report = run_import(db, library_path=library, plan_path=plan, media_dir=settings.media_dir,
                                sync_templates=not args.exercises_only, profile_id=profile_id)
        except ImportAborted as exc:
            print(exc.report.summary())
            print("Import aborted; no changes were made.")
            return 1
    print(report.summary())
    return 0


def _seed_if_empty(_: argparse.Namespace) -> int:
    settings = get_settings()
    with session_factory()() as db:
        count = db.scalar(select(func.count()).select_from(Exercise)) or 0
    if count:
        print(f"Database already has {count} exercises; skipping seed.")
        return 0
    if not settings.auto_seed:
        print("Auto seed disabled.")
        return 0
    library = _default_library()
    plan = settings.seed_path
    with session_factory()() as db:
        try:
            report = run_import(db, library_path=library if library.exists() else None,
                                plan_path=plan if plan.exists() else None, media_dir=settings.media_dir)
        except ImportAborted as exc:
            print(exc.report.summary())
            return 1
    print("Initial import complete.\n" + report.summary())
    return 0


def _backup(_: argparse.Namespace) -> int:
    path = backup_database("manual")
    print(f"Backup written to {path}" if path else "No database found.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Workout Pal tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="Import/update the exercise library and weekly plan")
    p_import.add_argument("--library", help="Exercise library CSV (default: seed/home_gym_exercises_verified.csv)")
    p_import.add_argument("--plan", help="Plan ZIP or CSV (default: seed/home_gym_workout_with_images.zip)")
    p_import.add_argument("--no-library", action="store_true", help="Skip the library CSV")
    p_import.add_argument("--no-plan", action="store_true", help="Skip the plan")
    p_import.add_argument("--exercises-only", action="store_true",
                          help="Update exercises and images but leave workout templates untouched")
    p_import.add_argument("--profile", help="Whose workouts the plan updates (default: the first profile, Trey)")
    p_import.add_argument("--check", action="store_true", help="Validate only; save nothing")
    p_import.add_argument("--no-backup", action="store_true", help="Skip the automatic pre-import backup")
    p_import.set_defaults(func=_import)

    sub.add_parser("seed-if-empty", help="Import the seed data when the database is empty").set_defaults(
        func=_seed_if_empty)
    sub.add_parser("backup", help="Back up the SQLite database").set_defaults(func=_backup)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

"""Move or copy everything from one Dropbox folder to another.

This is useful when you change the app's configured base folder and need to
physically migrate existing content in Dropbox from the old location to the new one.

Safety features:
- Supports --dry-run (no changes).
- Can skip/autorename/fail on conflicts.
- Moves/copies only the *children* of src into dst (does not try to move src itself).

Prereqs:
- Your Dropbox token must have access to BOTH folders.
- For Dropbox Business/Team spaces, you may need `DROPBOX_PATH_ROOT_MODE=root`
  so the API sees the same tree as the UI.

Usage examples:
  venv/bin/python scripts/migrate_dropbox_folder.py \
    --src "/IOK alfa/+IOK Cases/MiCaso App" \
    --dst "/IOK alfa/Casos App IOK" \
    --mode move \
    --dry-run

  venv/bin/python scripts/migrate_dropbox_folder.py \
    --src "/old/path" --dst "/new/path" --mode move --on-conflict autorename
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import dropbox
from dropbox import exceptions as dbx_exceptions

# Ensure project root is on sys.path even when running from outside the repo cwd.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.dropbox_utils import get_dropbox_client


def _norm(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    # Avoid trailing slash except for root
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path


@dataclass(frozen=True)
class MovePlanItem:
    src: str
    dst: str
    tag: str


def _list_folder_all(dbx: dropbox.Dropbox, folder: str) -> List[object]:
    # Dropbox SDK stubs can be incomplete; keep this intentionally untyped at the edges.
    res = dbx.files_list_folder(folder)
    entries = list(getattr(res, "entries", []) or [])
    while bool(getattr(res, "has_more", False)):
        res = dbx.files_list_folder_continue(getattr(res, "cursor"))
        entries.extend(list(getattr(res, "entries", []) or []))
    return entries


def _folder_exists(dbx: dropbox.Dropbox, path: str) -> bool:
    try:
        md = dbx.files_get_metadata(path)
        return getattr(md, ".tag", None) == "folder"
    except Exception:
        return False


def _ensure_folder(dbx: dropbox.Dropbox, path: str) -> None:
    try:
        dbx.files_create_folder_v2(path)
    except dbx_exceptions.ApiError as e:
        if "conflict" in str(e).lower():
            return
        raise


def _is_conflict_error(e: Exception) -> bool:
    return "conflict" in str(e).lower()


def _with_retries(fn, *, retries: int = 6, base_sleep: float = 0.6):
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last = e
            # Simple backoff for transient errors/rate limits.
            time.sleep(base_sleep * (2**attempt))
    if last:
        raise last


def build_plan(dbx: dropbox.Dropbox, src: str, dst: str) -> List[MovePlanItem]:
    src = _norm(src)
    dst = _norm(dst)

    entries = _list_folder_all(dbx, src)
    plan: List[MovePlanItem] = []
    for entry in entries:
        name = getattr(entry, "name", None)
        if not name:
            continue
        tag = getattr(entry, ".tag", "")
        from_path = getattr(entry, "path_lower", None) or getattr(entry, "path_display", None)
        to_path = _norm(dst + "/" + name)
        if not from_path:
            continue
        plan.append(MovePlanItem(src=from_path, dst=to_path, tag=tag))
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Dropbox folder contents")
    parser.add_argument("--src", required=True, help="Old Dropbox folder path")
    parser.add_argument("--dst", required=True, help="New Dropbox folder path")
    parser.add_argument("--mode", choices=["move", "copy"], default="move")
    parser.add_argument(
        "--on-conflict",
        choices=["autorename", "skip", "fail"],
        default="autorename",
        help="How to handle name conflicts in destination",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    parser.add_argument(
        "--create-dst",
        action="store_true",
        help="Create destination folder if missing",
    )
    parser.add_argument(
        "--delete-src-if-empty",
        action="store_true",
        help="After migrating, delete src folder if it becomes empty",
    )
    parser.add_argument(
        "--path-root-mode",
        choices=["env", "root", "default"],
        default="env",
        help="Override Dropbox Business path_root mode (env uses DROPBOX_PATH_ROOT_MODE as configured)",
    )

    args = parser.parse_args()

    if args.path_root_mode == "root":
        os.environ["DROPBOX_PATH_ROOT_MODE"] = "root"
    elif args.path_root_mode == "default":
        os.environ.pop("DROPBOX_PATH_ROOT_MODE", None)

    dbx = get_dropbox_client()
    if not dbx:
        print("ERROR: No Dropbox client available. Check token/env configuration.")
        return 2

    src = _norm(args.src)
    dst = _norm(args.dst)

    if not _folder_exists(dbx, src):
        print(f"ERROR: src folder not found or not a folder: {src}")
        return 3

    if not _folder_exists(dbx, dst):
        if args.create_dst:
            print(f"Destination folder does not exist; creating: {dst}")
            _with_retries(lambda: _ensure_folder(dbx, dst))
        else:
            print(f"ERROR: dst folder not found: {dst} (use --create-dst to create it)")
            return 4

    plan = build_plan(dbx, src, dst)
    print(f"Found {len(plan)} items in {src} to {args.mode} into {dst}")

    if args.dry_run:
        for item in plan[:50]:
            print(f"DRY-RUN {args.mode.upper()}: {item.src}  ->  {item.dst}  ({item.tag})")
        if len(plan) > 50:
            print(f"... ({len(plan) - 50} more)")
        return 0

    autorename = args.on_conflict == "autorename"

    moved = 0
    skipped = 0
    failed = 0

    for item in plan:
        def _op():
            if args.mode == "move":
                return dbx.files_move_v2(
                    item.src,
                    item.dst,
                    allow_shared_folder=True,
                    autorename=autorename,
                )
            return dbx.files_copy_v2(
                item.src,
                item.dst,
                allow_shared_folder=True,
                autorename=autorename,
            )

        try:
            _with_retries(_op)
            moved += 1
        except Exception as e:
            if args.on_conflict == "skip" and _is_conflict_error(e):
                skipped += 1
                continue
            failed += 1
            print(f"ERROR processing {item.src} -> {item.dst}: {e}")

    print(f"Done. ok={moved} skipped={skipped} failed={failed}")

    if args.delete_src_if_empty and failed == 0:
        try:
            remaining = _list_folder_all(dbx, src)
            if len(remaining) == 0:
                _with_retries(lambda: dbx.files_delete_v2(src))
                print(f"Deleted empty src folder: {src}")
            else:
                print(f"Src folder not empty ({len(remaining)} items), not deleting: {src}")
        except Exception as e:
            print(f"Could not delete src folder: {e}")

    return 0 if failed == 0 else 5


if __name__ == "__main__":
    raise SystemExit(main())

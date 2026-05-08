#!/usr/bin/env python3
"""
launch_deploy.py — deploy all (or specified) Grafana dashboard JSON files in parallel.

Usage:
    python3 launch_deploy.py                     # deploy every *.json in this directory
    python3 launch_deploy.py foo.json bar.json   # deploy specific files
    python3 launch_deploy.py --folder <uid>      # override target folder for all
    python3 launch_deploy.py --workers 10        # concurrency (default: 8)
    python3 launch_deploy.py --dry-run           # schema-detect and list only, no push

Parallel execution protection:
    A lock file (/tmp/grafana_deploy.lock) is held for the lifetime of this process.
    A second invocation will exit immediately with a non-zero code rather than
    running a conflicting deployment.
"""

import argparse
import fcntl
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Import the deploy logic from the sibling module
sys.path.insert(0, str(Path(__file__).parent))
from deploy_dashboard import deploy_v1, deploy_v2, is_v2_schema, DEFAULT_FOLDER_UID

LOCK_FILE    = "/tmp/grafana_deploy.lock"
SCRIPT_DIR   = Path(__file__).parent
MAX_WORKERS  = 8

# Files in the dashboard directory that are not deployable dashboards
SKIP_FILES = {
    "deploy_dashboard.py",
    "launch_deploy.py",
    "CLAUDE.md",
    "CLAUDE.new",
}


# ── Lock ──────────────────────────────────────────────────────────────────────

class DeployLock:
    """
    Non-blocking exclusive lock using flock(2).
    A second process calling acquire() while the lock is held gets False immediately
    (LOCK_EX | LOCK_NB), so there is no spin-wait or sleep.
    """
    def __init__(self, path: str):
        self.path = path
        self._fh  = None

    def acquire(self) -> bool:
        self._fh = open(self.path, "w")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fh.write(f"pid={os.getpid()}\n")
            self._fh.flush()
            return True
        except OSError:
            self._fh.close()
            self._fh = None
            return False

    def release(self):
        if self._fh:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
            self._fh = None

    def __enter__(self):
        if not self.acquire():
            # Read the PID from the existing lock file for a helpful message
            try:
                owner = open(self.path).read().strip()
            except OSError:
                owner = "unknown"
            print(f"ERROR: another deploy is already running ({owner}). Aborting.", file=sys.stderr)
            sys.exit(2)
        return self

    def __exit__(self, *_):
        self.release()


# ── Per-file work ─────────────────────────────────────────────────────────────

def deploy_one(json_path: Path, folder_uid: str, dry_run: bool) -> dict:
    """
    Load and deploy a single dashboard file.
    Returns a result dict with keys: file, schema, status, message, elapsed_s.
    """
    start = time.monotonic()
    result = {"file": json_path.name, "schema": "?", "status": "ok", "message": ""}

    try:
        with open(json_path) as f:
            dashboard = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        result.update(status="error", message=f"load failed: {exc}")
        result["elapsed_s"] = round(time.monotonic() - start, 2)
        return result

    schema = "v2" if is_v2_schema(dashboard) else "v1"
    result["schema"] = schema

    if dry_run:
        result["message"] = "dry-run"
        result["elapsed_s"] = round(time.monotonic() - start, 2)
        return result

    try:
        if schema == "v2":
            http_status, resp = deploy_v2(dashboard, folder_uid)
        else:
            http_status, resp = deploy_v1(dashboard, folder_uid)
    except Exception as exc:
        result.update(status="error", message=str(exc))
        result["elapsed_s"] = round(time.monotonic() - start, 2)
        return result

    if http_status in (200, 201):
        if "warning" in resp:
            result.update(status="warn", message=resp["warning"])
        elif schema == "v2":
            stored = len(resp.get("spec", {}).get("elements", {}))
            result["message"] = f"elements={stored}"
        else:
            result["message"] = f"version={resp.get('version')} url={resp.get('url','')}"
    else:
        msg = resp.get("message") or resp.get("raw") or str(resp)
        result.update(status="error", message=f"HTTP {http_status}: {msg}")

    result["elapsed_s"] = round(time.monotonic() - start, 2)
    return result


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Deploy Grafana dashboards in parallel.")
    parser.add_argument("files", nargs="*", help="Specific JSON files to deploy (default: all)")
    parser.add_argument("--folder",  default=DEFAULT_FOLDER_UID, help="Target folder UID")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="Parallel workers (default: 8)")
    parser.add_argument("--dry-run", action="store_true", help="Schema-detect only, no push")
    args = parser.parse_args()

    # Resolve file list
    if args.files:
        paths = [Path(p) if Path(p).is_absolute() else SCRIPT_DIR / p for p in args.files]
        missing = [p for p in paths if not p.exists()]
        if missing:
            for p in missing:
                print(f"ERROR: file not found: {p}", file=sys.stderr)
            sys.exit(1)
    else:
        paths = sorted(
            p for p in SCRIPT_DIR.glob("*.json")
            if p.name not in SKIP_FILES
        )

    if not paths:
        print("No dashboard files found.")
        sys.exit(0)

    with DeployLock(LOCK_FILE):
        mode = "DRY RUN" if args.dry_run else f"DEPLOY → folder {args.folder}"
        print(f"{'─'*60}")
        print(f"  Grafana Dashboard Launcher")
        print(f"  Mode    : {mode}")
        print(f"  Files   : {len(paths)}")
        print(f"  Workers : {args.workers}")
        print(f"{'─'*60}")
        wall_start = time.monotonic()

        futures = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for p in paths:
                fut = pool.submit(deploy_one, p, args.folder, args.dry_run)
                futures[fut] = p

            results = []
            for fut in as_completed(futures):
                r = fut.result()
                results.append(r)
                icon = {"ok": "✓", "warn": "!", "error": "✗"}.get(r["status"], "?")
                print(f"  {icon} [{r['schema']:2}] {r['file']:<50}  {r['message']}  ({r.get('elapsed_s', 0):.2f}s)")

    wall = round(time.monotonic() - wall_start, 2)
    errors = [r for r in results if r["status"] == "error"]
    warns  = [r for r in results if r["status"] == "warn"]

    print(f"{'─'*60}")
    print(f"  Done: {len(results)} files in {wall}s  |  errors={len(errors)}  warnings={len(warns)}")
    if errors:
        print("\n  Failed files:")
        for r in errors:
            print(f"    ✗ {r['file']}: {r['message']}")
    print(f"{'─'*60}")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()

"""Unsheduled v2 daily entry point with deadline-aware one-shard admission."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.ndx_dynamic_shadow_daily as v1
from backtest.ndx_dynamic_shadow_daily import NdxDynamicShadowDailyError
from scripts.ndx_dynamic_shadow_fresh_search_v2 import run_process_tree


def _budgeted_command(decision_date: str, *, max_jobs: int = 0) -> list[str]:
    del max_jobs
    snapshot = v1.INPUT_ROOT / decision_date / "manifest.json"
    return [
        sys.executable, "-B", str(ROOT / "scripts/ndx_dynamic_shadow_fresh_search_v2.py"),
        "--execute", "--snapshot-manifest", str(snapshot),
    ]


def execute() -> dict:
    from backtest.ndx_dynamic_shadow_activation_v3 import (
        verify_activation_v3_manifest, verify_activation_v3_static_sources,
    )
    activation = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v3/manifest.json"
    original = v1.fresh_search_command
    original_run_checked = v1._run_checked
    original_refresh_calendar = v1._refresh_calendar

    def budgeted_run_checked(command: list[str], *, timeout_seconds: float | None = None) -> None:
        if any(str(part).endswith("ndx_dynamic_shadow_fresh_search_v2.py") for part in command):
            if timeout_seconds is None:
                raise NdxDynamicShadowDailyError("budgeted controller requires an outer deadline")
            try:
                return_code = run_process_tree(command, timeout_seconds=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                raise NdxDynamicShadowDailyError(
                    "fresh search exceeded the pre-open seal deadline; process tree terminated"
                ) from exc
            if return_code != 0:
                raise NdxDynamicShadowDailyError(
                    f"budgeted fresh-search controller failed rc={return_code}"
                )
            return
        original_run_checked(command, timeout_seconds=timeout_seconds)
    try:
        with v1.single_instance_lock():
            before = v1._protected_hashes()
            verify_activation_v3_static_sources(activation, repository_root=ROOT)
            original_refresh_calendar()
            calendar_payload = json.loads(v1.CALENDAR_MANIFEST.read_text(encoding="utf-8"))
            if calendar_payload.get("status") == "PROSPECTIVE_OBSERVED_SESSION_APPENDED":
                original_run_checked([
                    sys.executable, "-B",
                    str(ROOT / "scripts/ndx_observed_session_calendar.py"), "--execute",
                ])
            verify_activation_v3_manifest(activation, repository_root=ROOT)
            v1.fresh_search_command = _budgeted_command
            v1._run_checked = budgeted_run_checked
            v1._refresh_calendar = lambda: None
            result = v1.execute(max_search_jobs=1)
            if v1._protected_hashes() != before:
                raise NdxDynamicShadowDailyError("protected live files changed")
            return result
    finally:
        v1.fresh_search_command = original
        v1._run_checked = original_run_checked
        v1._refresh_calendar = original_refresh_calendar


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("only --execute is supported")
    execute()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

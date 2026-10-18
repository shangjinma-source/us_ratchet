"""Reviewed-calendar runtime adapter; requires a separately verified v4 activation.

This module preserves the mathematical v1 state machine and append-only output
namespace, but never requires the now-invalid mutable v1 calendar.  The module
is not a task installer and cannot initialize a replacement calendar implicitly.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import ndx_dynamic_shadow_daily as engine
from scripts.ndx_dynamic_shadow_fresh_search_v2 import run_process_tree
from backtest.ndx_dynamic_shadow_daily import NdxDynamicShadowDailyError
from data.versioning import file_sha256

CALENDAR = ROOT / "data/cache/research/ndx_observed_us_session_calendar_v2/manifest.json"
ACTIVATION = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v4/manifest.json"
FRESH_SCRIPT = ROOT / "scripts/ndx_dynamic_shadow_fresh_search_v3.py"
GENERATOR_SCRIPT = ROOT / "scripts/ndx_dynamic_shadow_candidate_generator_v2.py"
CALENDAR_SCRIPT = ROOT / "scripts/ndx_observed_session_calendar_v2.py"


class ResearchStageFailure(NdxDynamicShadowDailyError):
    def __init__(self, message: str, exit_code: int):
        super().__init__(message)
        self.exit_code = exit_code


@contextmanager
def scoped_engine_bindings(bindings: Mapping[str, Any]) -> Iterator[None]:
    """Restore every borrowed module binding even when a research stage fails."""
    previous = {name: getattr(engine, name) for name in bindings}
    try:
        for name, value in bindings.items():
            setattr(engine, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(engine, name, value)


def _verify_activation(*, static_only: bool) -> dict[str, Any]:
    # Missing new lineage is a hard failure, never a fallback to old activation.
    from backtest.ndx_dynamic_shadow_activation_v4 import (
        verify_activation_v4_manifest, verify_activation_v4_static_sources,
    )
    verifier = verify_activation_v4_static_sources if static_only else verify_activation_v4_manifest
    return verifier(ACTIVATION, repository_root=ROOT)


def _run_checked(command: list[str], *, timeout_seconds: float | None = None) -> None:
    if timeout_seconds is None:
        completed = subprocess.run(command, cwd=ROOT, check=False)
        code = completed.returncode
    else:
        try:
            code = run_process_tree(command, timeout_seconds=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            # The outer budget is the hard pre-open deadline, not a shard retry.
            raise NdxDynamicShadowDailyError(
                "fresh search exceeded the pre-open seal deadline; process tree terminated"
            ) from exc
    if code:
        raise ResearchStageFailure(f"research stage failed with exit code {code}", code)


def _refresh_calendar() -> None:
    if not CALENDAR.is_file():
        raise NdxDynamicShadowDailyError("reviewed calendar v2 must be initialized explicitly")
    config = engine.load_config(ROOT / "config/config.yaml")
    for ticker in ("QQQ", "SPY"):
        engine.get_bars(ticker, config)
    _run_checked([sys.executable, "-B", str(CALENDAR_SCRIPT), "--execute"])


def _fresh_command(decision_date: str, *, max_jobs: int = 0) -> list[str]:
    del max_jobs
    return [sys.executable, "-B", str(FRESH_SCRIPT), "--execute",
            "--snapshot-manifest", str(engine.INPUT_ROOT / decision_date / "manifest.json")]


def _generator_command(decision_date: str) -> list[str]:
    return [
        sys.executable, "-B", str(GENERATOR_SCRIPT), "--seal",
        "--decision-date", decision_date, "--session-calendar-manifest", str(CALENDAR),
        "--refresh-official", "--refresh-membership", "--rebuild-taxonomy",
        "--refresh-prices", "--refresh-nominal-prices", "--refresh-target",
        "--allow-degraded-reviewed-taxonomy-subset",
    ]


def _verify_input_seal(decision_date: str) -> None:
    _run_checked([sys.executable, "-B", str(GENERATOR_SCRIPT), "--verify",
                  str(engine.INPUT_ROOT / decision_date / "manifest.json")])


def _adapter_bindings() -> dict[str, Any]:
    from backtest import ndx_dynamic_shadow_daily_v2 as reviewed
    original_inventory = engine._daily_artifact_inventory

    def calendar_sessions():
        manifest, _, projection = reviewed.load_reviewed_calendar_projection(
            CALENDAR, repository_root=ROOT,
        )
        projection = projection.copy()
        if "source_price_replay_available" not in projection:
            raise NdxDynamicShadowDailyError("reviewed projection lacks source evidence mode")
        projection["decision_eligible"] = (
            projection["decision_eligible"].eq(True)
            & projection["source_price_replay_available"].eq(True)
        )
        return manifest, engine.normalize_observed_sessions(projection)

    def inventory(path_update):
        result = original_inventory(path_update)
        for key, path in (
            ("daily_script", Path(__file__).resolve()),
            ("daily_engine", ROOT / "backtest/ndx_dynamic_shadow_daily_v2.py"),
        ):
            result[key] = {"path": path.as_posix(), "sha256": file_sha256(path)}
        return result

    return {
        "CALENDAR_MANIFEST": CALENDAR,
        "_verify_activation_before_execute": lambda: _verify_activation(static_only=False),
        "_refresh_calendar": lambda: None,
        "_calendar_sessions": calendar_sessions,
        "_run_checked": _run_checked,
        "candidate_generator_command": _generator_command,
        "fresh_search_command": _fresh_command,
        "_verify_input_seal": _verify_input_seal,
        "_daily_artifact_inventory": inventory,
        "write_three_way_calendar_manifest": reviewed.write_three_way_calendar_manifest,
        "verify_three_way_calendar_manifest": reviewed.verify_three_way_calendar_manifest,
        "verify_daily_run_manifest": reviewed.verify_daily_run_manifest,
    }


def execute() -> dict[str, Any]:
    with engine.single_instance_lock():
        before = engine._protected_hashes()
        try:
            _verify_activation(static_only=True)
            _refresh_calendar()
            _verify_activation(static_only=False)
            with scoped_engine_bindings(_adapter_bindings()):
                return engine.execute(max_search_jobs=0)
        finally:
            if engine._protected_hashes() != before:
                raise NdxDynamicShadowDailyError("protected live files changed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("--execute is required")
    try:
        result = execute()
    except ResearchStageFailure as exc:
        print(f"daily v3 research stage stopped: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        print(f"daily v3 fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

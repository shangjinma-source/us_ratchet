"""Fail-closed post-close refresh and monthly cohort registration boundary."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import atomic_write_text  # noqa: E402
from data.versioning import file_sha256  # noqa: E402

NEW_YORK = ZoneInfo("America/New_York")
DEFAULT_OUTPUT = ROOT / "data" / "cache" / "research" / "ndx_challenger_forward_v3"
DEFAULT_SPEC = "config/ndx_challenger_forward_v3.yaml"
DEFAULT_REGISTRY = "data/cache/research/ndx_challenger_forward_registry_v3/manifest.json"
DEFAULT_SHADOW_SPEC = "config/ndx_challenger_shadow_v1.yaml"
DEFAULT_PRICE_CACHE = "data/cache"
DEFAULT_TARGET_NAV = "data/cache/funds/012922.csv"


def is_safe_post_close_window(now: datetime | None = None) -> bool:
    local = (now or datetime.now(timezone.utc)).astimezone(NEW_YORK)
    return local.weekday() < 5 and 18 <= local.hour < 24


def _run(command: list[str], timeout: float) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    return {"command": command, "returncode": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]}


def _append(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def run_daily(
    *, output: Path, timeout: float = 1200.0,
    spec: str = DEFAULT_SPEC, registry_manifest: str = DEFAULT_REGISTRY,
    shadow_spec: str = DEFAULT_SHADOW_SPEC, price_cache_dir: str = DEFAULT_PRICE_CACHE,
    target_nav: str = DEFAULT_TARGET_NAV,
    runner: Callable[[list[str], float], dict[str, Any]] = _run,
) -> tuple[dict[str, Any], int]:
    config = ROOT / "config" / "config.yaml"
    state = ROOT / "data" / "state.json"
    before = {"config": file_sha256(config), "state": file_sha256(state)}
    steps = []
    error = None
    registered = False
    observation = None
    retry_needed = False
    missing_close_tickers: list[str] = []
    try:
        commands = [
            [
                sys.executable, "-B", str(ROOT / "scripts" / "ndx_challenger_forward_refresh.py"), "--execute",
                "--registry-manifest", registry_manifest,
                "--output-dir", str(output / "latest_refresh"),
            ],
            [
                sys.executable, "-B", str(ROOT / "scripts" / "ndx_challenger_forward_cohort.py"), "plan",
                "--spec", spec, "--registry-manifest", registry_manifest,
                "--price-cache-dir", price_cache_dir, "--output-dir", str(output),
            ],
        ]
        for command in commands:
            result = runner(command, timeout)
            steps.append(result)
            if int(result.get("returncode", 1)) != 0:
                raise RuntimeError(f"child command failed with exit {result.get('returncode')}")
        readiness = json.loads((output / "readiness.json").read_text(encoding="utf-8"))
        if readiness.get("status") == "WAITING_FOR_COMPLETE_OBSERVATION_CLOSE_COVERAGE":
            retry_needed = True
            observation = str(readiness.get("next_expected_observation_if_already_cached") or "") or None
            missing_close_tickers = sorted(str(value) for value in readiness.get("missing_observation_close_tickers") or [])
        if readiness.get("status") == "READY_FOR_SAME_DAY_POST_CLOSE_REGISTRATION":
            observation = str(readiness["next_expected_observation_if_already_cached"])
            command = [
                sys.executable, "-B", str(ROOT / "scripts" / "ndx_challenger_forward_cohort.py"), "register",
                "--observation-date", observation,
                "--spec", spec, "--registry-manifest", registry_manifest,
                "--price-cache-dir", price_cache_dir, "--output-dir", str(output),
            ]
            result = runner(command, timeout)
            steps.append(result)
            if int(result.get("returncode", 1)) != 0:
                raise RuntimeError(f"cohort registration failed with exit {result.get('returncode')}")
            registered = True
        command = [
            sys.executable, "-B", str(ROOT / "scripts" / "ndx_challenger_forward_evaluate.py"),
            "--spec", spec, "--registry-manifest", registry_manifest,
            "--shadow-spec", shadow_spec, "--price-cache-dir", price_cache_dir,
            "--target-nav", target_nav, "--output-dir", str(output),
        ]
        result = runner(command, timeout)
        steps.append(result)
        if int(result.get("returncode", 1)) != 0:
            raise RuntimeError(f"cohort evaluation failed with exit {result.get('returncode')}")
        command = [sys.executable, "-B", str(ROOT / "scripts" / "portfolio_pullback_pooled_reserve_audit.py")]
        result = runner(command, timeout)
        steps.append(result)
        if int(result.get("returncode", 1)) != 0:
            raise RuntimeError(f"pullback pooled-reserve shadow failed with exit {result.get('returncode')}")
    except subprocess.TimeoutExpired as exc:
        error = f"child command timed out after {exc.timeout}s"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    after = {"config": file_sha256(config), "state": file_sha256(state)}
    if before != after:
        error = "live config/state hash changed during challenger forward maintenance"
    payload = {
        "ok": error is None and not retry_needed,
        "retry_needed": retry_needed,
        "missing_observation_close_tickers": missing_close_tickers,
        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "steps": steps, "error": error, "cohort_registration_performed": registered,
        "observation_date": observation, "promotion_allowed": False,
        "forward_spec": spec, "forward_registry_manifest": registry_manifest,
        "pullback_pooled_reserve_shadow_performed": bool(
            steps and "portfolio_pullback_pooled_reserve_audit.py" in " ".join(steps[-1].get("command") or [])
            and int(steps[-1].get("returncode", 1)) == 0
        ),
        "config_sha256_before": before["config"], "config_sha256_after": after["config"],
        "state_sha256_before": before["state"], "state_sha256_after": after["state"],
        "live_config_changed": before["config"] != after["config"], "state_changed": before["state"] != after["state"],
        "today_advice_changed": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    _append(output / "daily_audit.jsonl", payload)
    atomic_write_text(output / "daily_status.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    if error is not None:
        return payload, 2
    return payload, 3 if retry_needed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="challenger 盘后刷新及月度 cohort 登记")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ignore-refresh-window", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--spec", default=DEFAULT_SPEC)
    parser.add_argument("--registry-manifest", default=DEFAULT_REGISTRY)
    parser.add_argument("--shadow-spec", default=DEFAULT_SHADOW_SPEC)
    parser.add_argument("--price-cache-dir", default=DEFAULT_PRICE_CACHE)
    parser.add_argument("--target-nav", default=DEFAULT_TARGET_NAV)
    parser.add_argument("--timeout", type=float, default=1200.0)
    args = parser.parse_args()
    if not args.execute:
        parser.error("add --execute to permit market-cache refresh and eligible cohort registration")
    if not args.ignore_refresh_window and not is_safe_post_close_window():
        print(json.dumps({"ok": True, "skipped": True, "reason": "OUTSIDE_SAFE_US_POST_CLOSE_WINDOW"}, ensure_ascii=False))
        return 0
    payload, code = run_daily(
        output=Path(args.output_dir), timeout=float(args.timeout), spec=args.spec,
        registry_manifest=args.registry_manifest, shadow_spec=args.shadow_spec,
        price_cache_dir=args.price_cache_dir, target_nav=args.target_nav,
    )
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), file=sys.stdout if code == 0 else sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

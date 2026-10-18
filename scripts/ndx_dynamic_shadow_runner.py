r"""Audit future dynamic-shadow readiness without changing live state.

PowerShell:
    python -B scripts\ndx_dynamic_shadow_runner.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_runner import (  # noqa: E402
    NdxDynamicShadowRunnerError,
    build_dynamic_shadow_readiness,
)
from core.helpers import atomic_write_text  # noqa: E402
from data.versioning import file_sha256  # noqa: E402


def _resolve(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="未来一年 dynamic shadow readiness/fail-closed runner"
    )
    parser.add_argument("--contract", default="config/ndx_dynamic_shadow_runner_v1.yaml")
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument(
        "--output-dir", default="data/cache/research/ndx_dynamic_shadow_runner_v1"
    )
    parser.add_argument(
        "--readiness", action="store_true",
        help="显式执行只读 readiness；当前版本唯一允许的运行模式。",
    )
    parser.add_argument("--require-ready", action="store_true")
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict:
    contract_path = _resolve(args.contract)
    output = _resolve(args.output_dir)
    protected = [
        _resolve("config/config.yaml"),
        _resolve("data/state.json"),
        _resolve("data/broker_positions.json"),
    ]
    protected_before = {
        path.as_posix(): file_sha256(path) if path.is_file() else None for path in protected
    }
    readiness = build_dynamic_shadow_readiness(
        contract_path, as_of_date=args.as_of_date
    )
    output.mkdir(parents=True, exist_ok=True)
    readiness_path = output / "readiness.json"
    atomic_write_text(
        readiness_path,
        json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    protected_after = {
        path.as_posix(): file_sha256(path) if path.is_file() else None for path in protected
    }
    if protected_before != protected_after:
        raise NdxDynamicShadowRunnerError("protected live files changed")
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_runner_readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": readiness["status"],
        "ready_for_decision_registration": False,
        "ready_for_path_evaluation": False,
        "historical_consumed_used": False,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "live_mutation": False,
        "inputs": {
            "runner_script": {
                "path": Path(__file__).resolve().as_posix(),
                "sha256": file_sha256(Path(__file__).resolve()),
            },
            "runner_contract": {
                "path": contract_path.as_posix(),
                "sha256": file_sha256(contract_path),
            },
        },
        "artifacts": {
            "readiness": {
                "path": readiness_path.as_posix(),
                "sha256": file_sha256(readiness_path),
                "blocker_count": len(readiness["blockers"]),
            }
        },
        "protected_hashes_unchanged": True,
    }
    atomic_write_text(
        output / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    if args.require_ready and not readiness["ready_for_decision_registration"]:
        raise NdxDynamicShadowRunnerError(
            f"future shadow is not ready; blockers={len(readiness['blockers'])}"
        )
    return manifest


def main() -> int:
    args = parse_args()
    try:
        manifest = run(args)
    except NdxDynamicShadowRunnerError as exc:
        print(f"dynamic shadow runner fail-closed: {exc}", file=sys.stderr)
        return 2
    print(
        "dynamic shadow readiness | "
        f"status={manifest['status']} | "
        f"blockers={manifest['artifacts']['readiness']['blocker_count']} | "
        "decision_registration=False | promotion=False | live_mutation=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

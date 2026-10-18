"""Versioned exit-status adapter for the immutable budgeted v2 controller.

The controller and checkpoint namespace remain unchanged.  This entry point
does not activate itself or register a task.  A future daily/activation lineage
must bind this file before use.  Exit zero means a verified final role seal,
never merely a resumable partial search.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ndx_dynamic_shadow_fresh_search_v2 import execute as execute_budgeted

SUCCESS = 0
INTEGRITY_FAILURE = 2
DEADLINE_EXHAUSTED = 4
RETRYABLE_TIMEOUT = 75


def classify_completion(result: Mapping[str, Any]) -> dict[str, Any]:
    """Map verified controller outcomes without broadening admission rules."""
    reason = result.get("controller_stop_reason")
    final = result.get("final_role_seal_verified")
    pending = result.get("pending_shard_count")
    if final is True:
        if (
            reason != "FINAL_ROLE_SEAL_VERIFIED"
            or result.get("controller_status") != "FINAL_ROLE_SEAL_VERIFIED"
            or type(pending) is not int or pending != 0
            or type(result.get("planned_shard_count")) is not int
            or result["planned_shard_count"] <= 0
            or result.get("verified_completed_shard_count") != result["planned_shard_count"]
            or result.get("aggregation_allowed") is not True
        ):
            raise ValueError("final role seal and controller completion disagree")
        code = SUCCESS
    elif final is not False:
        raise ValueError("final role seal verification must be explicit")
    elif reason == "SHARD_TIMEOUT_PROCESS_TREE_TERMINATED":
        remaining = result.get("seconds_to_role_seal_deadline")
        if (
            result.get("shard_timed_out") is not True
            or result.get("controller_status") != "SHARD_TIMEOUT_INCOMPLETE_RESUMABLE"
            or type(remaining) not in (int, float)
            or not (-float("inf") < remaining < float("inf"))
        ):
            raise ValueError("timeout outcome lacks verified timing")
        code = RETRYABLE_TIMEOUT if remaining > 0 else DEADLINE_EXHAUSTED
    elif reason in {
        "DEADLINE_BUDGET_DID_NOT_ADMIT_NEXT_SHARD",
        "NEXT_SHARD_NOT_ADMITTED_BEFORE_ROLE_SEAL_RESERVE",
    }:
        code = DEADLINE_EXHAUSTED
    elif reason in {
        "NO_VERIFIED_PROGRESS_FAIL_CLOSED", "ITERATION_BOUND_REACHED_FAIL_CLOSED",
    }:
        code = INTEGRITY_FAILURE
    else:
        raise ValueError(f"unknown controller stop reason: {reason}")
    return {
        "exit_code": code,
        "retryable": code == RETRYABLE_TIMEOUT,
        "completed": code == SUCCESS,
        "stop_reason": reason,
        "backfill_allowed": False,
        "partial_result_promotion_allowed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--snapshot-manifest", required=True)
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("--execute is required")
    try:
        result = execute_budgeted(Path(args.snapshot_manifest))
        completion = classify_completion(result)
    except Exception as exc:
        print(f"fresh-search v3 fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return INTEGRITY_FAILURE
    print(json.dumps({
        **result, "v3_completion": completion,
        "v3_adapter_only_not_automatic_activation": True,
    }, ensure_ascii=False, sort_keys=True))
    return completion["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())

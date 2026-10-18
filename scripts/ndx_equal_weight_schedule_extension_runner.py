r"""Plan or execute the locked 323-row equal-weight schedule-extension replay.

PowerShell smoke (one historical candidate only):
    python -B scripts\ndx_equal_weight_schedule_extension_runner.py --execute --max-candidates 1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_equal_weight_schedule_extension_runner import (
    NdxEqualWeightScheduleExtensionRunnerError,
    OUTPUT_RELATIVE,
    build_locked_replay_plan,
    execute_locked_replay,
    verify_locked_replay_output,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the one preregistered 21-session schedule extension for the "
            "locked 2024-06-03 exact equal-weight candidates."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="verify and print the fixed scope")
    mode.add_argument("--execute", action="store_true", help="execute or resume checkpoints")
    mode.add_argument(
        "--verify", action="store_true",
        help="rebuild the complete 323-row output from canonical sources",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument("--output-root", type=Path, default=ROOT / OUTPUT_RELATIVE)
    return parser


def run(args: argparse.Namespace) -> dict:
    if args.plan:
        if args.resume or args.fail_fast or args.max_candidates is not None:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "execution controls are invalid in plan mode"
            )
        plan = build_locked_replay_plan(repository_root=ROOT)
        return {
            "status": plan["status"],
            "plan_fingerprint": plan["plan_fingerprint"],
            "selection_date": plan["selection_date"],
            "job_search_class": plan["job_search_class"],
            "evaluation_semantics_sha256": plan["evaluation_semantics_sha256"],
            "track_load_count_clean_full_run": plan[
                "track_load_count_clean_full_run"
            ],
            "counts": plan["counts"],
            "groups": [
                {
                    "universe_track": group["universe_track"],
                    "counts": group["counts"],
                }
                for group in plan["groups"]
            ],
            "candidate_set_or_weight_search_run": False,
            "artifact_written": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        }
    if args.verify:
        if args.resume or args.fail_fast or args.max_candidates is not None:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "execution controls are invalid in verify mode"
            )
        return verify_locked_replay_output(
            repository_root=ROOT,
            output_root=args.output_root,
        )
    return execute_locked_replay(
        repository_root=ROOT,
        output_root=args.output_root,
        resume=args.resume,
        fail_fast=args.fail_fast,
        max_candidates=args.max_candidates,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(_parser().parse_args(argv))
    except (NdxEqualWeightScheduleExtensionRunnerError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "FAILED_CLOSED", "reason": f"{type(exc).__name__}:{exc}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("failed_batch_count", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

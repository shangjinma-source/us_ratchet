"""Plan, execute, resume, or verify the fixed 323-row repair batch."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_conditional_repair_batch import (
    NdxConditionalRepairBatchError,
    OUTPUT_RELATIVE,
    build_conditional_repair_plan,
    execute_conditional_repair_batch,
    verify_conditional_repair_batch,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the locked research-only conditional whole-lot repair batch."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument("--output-root", type=Path, default=ROOT / OUTPUT_RELATIVE)
    return parser


def run(args: argparse.Namespace) -> dict:
    if args.plan:
        if args.resume or args.fail_fast or args.max_candidates is not None:
            raise NdxConditionalRepairBatchError("plan controls are invalid")
        plan = build_conditional_repair_plan(repository_root=ROOT)
        return {
            "status": plan["status"],
            "plan_fingerprint": plan["plan_fingerprint"],
            "counts": plan["counts"],
            "source_plan_fingerprint": plan["source_plan_fingerprint"],
            "candidate_set_or_weight_search_run": False,
            "artifact_written": False,
            "admission_claimed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        }
    if args.verify:
        if args.resume or args.fail_fast or args.max_candidates is not None:
            raise NdxConditionalRepairBatchError("verify controls are invalid")
        return verify_conditional_repair_batch(
            repository_root=ROOT, output_root=args.output_root
        )
    return execute_conditional_repair_batch(
        repository_root=ROOT,
        output_root=args.output_root,
        resume=args.resume,
        fail_fast=args.fail_fast,
        max_candidates=args.max_candidates,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(_parser().parse_args(argv))
    except (NdxConditionalRepairBatchError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "FAILED_CLOSED", "reason": f"{type(exc).__name__}:{exc}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("failed_candidate_count", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

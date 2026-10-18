"""Plan, build, or verify the repair-C same-calendar benchmark bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_conditional_repair_benchmark import (  # noqa: E402
    NdxConditionalRepairBenchmarkError,
    OUTPUT_RELATIVE,
    build_conditional_repair_benchmark_plan,
    verify_conditional_repair_benchmark,
    write_conditional_repair_benchmark,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the research-only original-eight/012922 repair-C benchmark."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--output-root", type=Path, default=ROOT / OUTPUT_RELATIVE)
    return parser


def run(args: argparse.Namespace) -> dict:
    if args.plan:
        plan = build_conditional_repair_benchmark_plan(repository_root=ROOT)
        return {
            "status": plan["status"],
            "plan_fingerprint": plan["plan_fingerprint"],
            "session_window": plan["session_window"],
            "artifact_written": False,
            "admission_claimed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        }
    if args.build:
        return write_conditional_repair_benchmark(
            repository_root=ROOT, output_root=args.output_root
        )
    return verify_conditional_repair_benchmark(
        repository_root=ROOT, output_root=args.output_root
    )


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(_parser().parse_args(argv))
    except (NdxConditionalRepairBenchmarkError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "FAILED_CLOSED", "reason": f"{type(exc).__name__}:{exc}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

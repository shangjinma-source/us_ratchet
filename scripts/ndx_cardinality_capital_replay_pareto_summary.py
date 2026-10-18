from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_capital_replay_pareto_summary import (
    NdxCardinalityCapitalReplayParetoSummaryError,
    OUTPUT_RELATIVE,
    SOURCE_V1_RELATIVE,
    build_capital_replay_pareto_summary,
    verify_pareto_bundle,
    write_pareto_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="重建或验证历史 $25k 回放的逐坐标六轴 Pareto 全量报告（不运行回测）"
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--build", action="store_true", help="从已发布 v1 bundle 重建 v2")
    action.add_argument("--dry-run", action="store_true", help="完整重建并核验，但不写产物")
    action.add_argument("--verify", action="store_true", help="只读验证现有 v2 bundle")
    parser.add_argument(
        "--source-v1-manifest",
        type=Path,
        default=ROOT / SOURCE_V1_RELATIVE,
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / OUTPUT_RELATIVE)
    args = parser.parse_args()
    try:
        if args.build or args.dry_run:
            summary = build_capital_replay_pareto_summary(
                args.source_v1_manifest, repository_root=ROOT
            )
            if args.dry_run:
                print(
                    json.dumps(
                        {
                            "status": summary["status"],
                            "verified_child_job_count": summary[
                                "verified_child_job_count"
                            ],
                            "evaluator_group_count": summary["evaluator_group_count"],
                            "pareto_candidate_rows": sum(
                                group["pareto_candidate_rows"]
                                for group in summary["evaluator_groups"]
                            ),
                            "artifact_written": False,
                            "new_backtest_run": False,
                            "promotion_allowed": False,
                            "live_mutation_allowed": False,
                        },
                        ensure_ascii=False,
                    )
                )
                return 0
            manifest = write_pareto_bundle(summary, output_dir=args.output_dir)
        else:
            manifest = verify_pareto_bundle(
                args.output_dir / "manifest.json", repository_root=ROOT
            )
    except (NdxCardinalityCapitalReplayParetoSummaryError, OSError) as exc:
        print(json.dumps({"status": "FAILED_CLOSED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "verified_child_job_count": manifest["verified_child_job_count"],
                "manifest_sha256": manifest["manifest_sha256"],
                "output_dir": args.output_dir.resolve().as_posix(),
                "new_backtest_run": False,
                "promotion_allowed": False,
                "live_mutation_allowed": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

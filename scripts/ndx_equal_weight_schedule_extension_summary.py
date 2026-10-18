from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_equal_weight_schedule_extension_summary import (
    NdxEqualWeightScheduleExtensionSummaryError,
    OUTPUT_RELATIVE,
    build_extension_summary,
    verify_summary_bundle,
    write_summary_bundle,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="生成或验证323个等权候选的21会话日程延续历史A/B摘要"
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--build", action="store_true")
    action.add_argument("--verify", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / OUTPUT_RELATIVE)
    args = parser.parse_args(argv)
    try:
        if args.build:
            if args.output_dir.resolve() != (ROOT / OUTPUT_RELATIVE).resolve():
                raise NdxEqualWeightScheduleExtensionSummaryError(
                    "CLI output directory is not canonical"
                )
            summary = build_extension_summary(repository_root=ROOT)
            manifest = write_summary_bundle(summary, output_dir=args.output_dir)
        else:
            manifest = verify_summary_bundle(
                args.output_dir / "manifest.json", repository_root=ROOT
            )
    except (NdxEqualWeightScheduleExtensionSummaryError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "FAILED_CLOSED", "reason": f"{type(exc).__name__}:{exc}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "candidate_rows": manifest["candidate_rows"],
                "source_results_file_sha256": manifest[
                    "source_results_file_sha256"
                ],
                "manifest_sha256": manifest["manifest_sha256"],
                "ranking_or_winner_selected": False,
                "admission_claimed": False,
                "promotion_allowed": False,
                "live_mutation_allowed": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

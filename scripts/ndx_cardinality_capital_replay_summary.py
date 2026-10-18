r"""Build or verify the immutable $25k historical replay summary bundle.

This command only reads completed historical research artifacts.  It does not
run a search/backtest, consume fresh OOS data, grant admission, or touch live
configuration/state/advice/orders.

PowerShell:
    python -B scripts\ndx_cardinality_capital_replay_summary.py --dry-run
    python -B scripts\ndx_cardinality_capital_replay_summary.py --build
    python -B scripts\ndx_cardinality_capital_replay_summary.py --verify
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_capital_replay_summary import (
    NdxCardinalityCapitalReplaySummaryError,
    OUTPUT_RELATIVE,
    TOP_MANIFEST_RELATIVE,
    build_capital_replay_summary,
    verify_summary_bundle,
    write_summary_bundle,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild a review-only summary from completed $25k replay evidence."
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true", help="print JSON; write nothing")
    modes.add_argument("--build", action="store_true", help="publish immutable bundle")
    modes.add_argument("--verify", action="store_true", help="verify canonical bundle")
    parser.add_argument(
        "--manifest", default=str(TOP_MANIFEST_RELATIVE),
        help="canonical completed replay manifest (canonical path is enforced)",
    )
    parser.add_argument(
        "--output-dir", default=str(OUTPUT_RELATIVE),
        help="research-only bundle directory",
    )
    return parser


def run(args: argparse.Namespace) -> dict:
    manifest_path = (ROOT / args.manifest).resolve()
    output_dir = (ROOT / args.output_dir).resolve()
    try:
        output_dir.relative_to(ROOT)
    except ValueError as exc:
        raise NdxCardinalityCapitalReplaySummaryError(
            "output directory escapes repository root"
        ) from exc
    if args.verify:
        manifest = verify_summary_bundle(output_dir / "manifest.json")
        return {
            "status": "VERIFIED",
            "bundle_manifest": (output_dir / "manifest.json").as_posix(),
            "verified_child_job_count": manifest["verified_child_job_count"],
        }
    summary = build_capital_replay_summary(manifest_path, repository_root=ROOT)
    if args.dry_run:
        return summary
    # Rebuild twice before publishing.  A source mutation during the read pass
    # cannot silently become a mixed, signed bundle.
    confirmation = build_capital_replay_summary(manifest_path, repository_root=ROOT)
    if summary != confirmation:
        raise NdxCardinalityCapitalReplaySummaryError(
            "source evidence changed while rebuilding the summary"
        )
    manifest = write_summary_bundle(summary, output_dir=output_dir)
    return {
        "status": "BUILT_AND_VERIFIED",
        "bundle_manifest": (output_dir / "manifest.json").as_posix(),
        "verified_child_job_count": manifest["verified_child_job_count"],
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run(args)
    except (NdxCardinalityCapitalReplaySummaryError, OSError, ValueError) as exc:
        print(f"historical replay summary failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

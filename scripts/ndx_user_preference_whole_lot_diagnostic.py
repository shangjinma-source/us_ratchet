r"""Build/verify the research-only four-name equal-weight A/B diagnostic.

PowerShell:
    python -B scripts\ndx_user_preference_whole_lot_diagnostic.py --dry-run
    python -B scripts\ndx_user_preference_whole_lot_diagnostic.py --build
    python -B scripts\ndx_user_preference_whole_lot_diagnostic.py --verify
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_user_preference_whole_lot_diagnostic import (
    NdxUserPreferenceWholeLotDiagnosticError,
    OUTPUT_RELATIVE,
    build_canonical_user_preference_diagnostic,
    verify_canonical_diagnostic_bundle,
    write_diagnostic_bundle,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose the stored four-name equal-weight whole-lot path."
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--build", action="store_true")
    modes.add_argument("--verify", action="store_true")
    parser.add_argument("--output-dir", default=str(OUTPUT_RELATIVE))
    return parser


def run(args: argparse.Namespace) -> dict:
    output = (ROOT / args.output_dir).resolve()
    try:
        output.relative_to(ROOT)
    except ValueError as exc:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "output directory escapes repository root"
        ) from exc
    if args.verify:
        manifest = verify_canonical_diagnostic_bundle(
            output / "manifest.json", repository_root=ROOT
        )
        return {"status": "VERIFIED", "manifest": (output / "manifest.json").as_posix(), **manifest}
    result = build_canonical_user_preference_diagnostic(repository_root=ROOT)
    if args.dry_run:
        return result
    confirmation = build_canonical_user_preference_diagnostic(repository_root=ROOT)
    if result != confirmation:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "source evidence changed during diagnostic build"
        )
    write_diagnostic_bundle(result, output_dir=output)
    manifest = verify_canonical_diagnostic_bundle(
        output / "manifest.json", repository_root=ROOT
    )
    return {"status": "BUILT_AND_VERIFIED", "manifest": (output / "manifest.json").as_posix(), **manifest}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run(args)
    except (NdxUserPreferenceWholeLotDiagnosticError, OSError, ValueError) as exc:
        print(f"whole-lot diagnostic failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

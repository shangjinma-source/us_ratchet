"""Read-only CLI for the versioned runtime-v3 disabled-task recovery."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_runtime_v3_recovery import (  # noqa: E402
    build_recovery_authority,
    build_recovery_readiness,
    verify_recovery_authority,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--readiness", action="store_true")
    mode.add_argument("--authority", action="store_true")
    mode.add_argument("--verify-authority", type=Path)
    args = parser.parse_args()
    try:
        if args.readiness:
            result = build_recovery_readiness(repository_root=ROOT)
        elif args.authority:
            result = build_recovery_authority(repository_root=ROOT)
        else:
            result = verify_recovery_authority(args.verify_authority, repository_root=ROOT)
    except Exception as exc:
        print(f"runtime-v3 recovery fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if not args.readiness or result["status"].startswith("READY_") else 2


if __name__ == "__main__":
    raise SystemExit(main())

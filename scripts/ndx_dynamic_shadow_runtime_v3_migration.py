"""Read-only CLI for the research runtime-v3 Scheduled Task migration gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_runtime_v3_migration import (  # noqa: E402
    build_runtime_v3_migration_authority,
    build_runtime_v3_migration_readiness,
    verify_runtime_v3_migration_authority,
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
            result = build_runtime_v3_migration_readiness(repository_root=ROOT)
        elif args.authority:
            result = build_runtime_v3_migration_authority(repository_root=ROOT)
        else:
            result = verify_runtime_v3_migration_authority(
                args.verify_authority,
                repository_root=ROOT,
            )
    except Exception as exc:
        print(
            f"runtime-v3 migration readiness fail-closed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.readiness:
        return 0 if result["status"].startswith("READY_") else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

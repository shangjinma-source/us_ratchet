"""Print read-only runtime4 migration readiness; no build, register or apply mode."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtest.ndx_dynamic_shadow_runtime_v4_migration import build_runtime_v4_migration_readiness


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", action="store_true", required=True)
    parser.parse_args(argv)
    result = build_runtime_v4_migration_readiness(ROOT)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["status"] == "READY_FOR_V4_MIGRATION_REVIEW_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())

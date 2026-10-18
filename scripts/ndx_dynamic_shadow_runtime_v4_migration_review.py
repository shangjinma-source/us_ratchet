"""Print a migration review draft; never save an authority or mutate a task."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtest.ndx_dynamic_shadow_runtime_v4_migration_review import build_review_draft, verify_review_draft


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--draft", action="store_true")
    mode.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_review_draft(ROOT) if args.draft else verify_review_draft(args.verify, repository_root=ROOT)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"migration review failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

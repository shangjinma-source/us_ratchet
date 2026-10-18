"""Build/verify research activation5 evidence; does not register or migrate tasks."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtest.ndx_dynamic_shadow_activation_v5 import (
    MANIFEST, build_activation_v5_manifest, verify_activation_v5_manifest,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = (build_activation_v5_manifest(ROOT) if args.build
                  else verify_activation_v5_manifest(ROOT / MANIFEST, repository_root=ROOT))
    except Exception as exc:
        print(f"activation v5 fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

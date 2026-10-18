from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_activation_v3 import (
    build_activation_v3_manifest, verify_activation_v3_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--build-activation-manifest", action="store_true")
    group.add_argument("--verify-activation-manifest", action="store_true")
    args = parser.parse_args()
    path = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v3/manifest.json"
    result = (
        build_activation_v3_manifest(ROOT) if args.build_activation_manifest
        else verify_activation_v3_manifest(path, repository_root=ROOT)
    )
    print(json.dumps({"status": result["status"], "manifest_sha256": result["manifest_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

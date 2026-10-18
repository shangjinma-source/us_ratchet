"""Read-only CLI for independently rebuilding the canonical P4 gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_p4_evidence import (  # noqa: E402
    verify_p4_evaluation_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the canonical immutable v5 P4 evaluation gate",
    )
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.verify:
        parser.error("only --verify is supported")
    result = verify_p4_evaluation_evidence(
        ROOT / "data/cache/research/ndx_challenger_forward_v5/latest_evaluation/manifest.json",
        repository_root=ROOT,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

r"""Print the read-only dynamic-shadow identity evidence gap inventory.

PowerShell:
    python -B scripts\ndx_dynamic_shadow_identity_evidence_inventory.py --decision-date 2026-10-01
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_identity_evidence_inventory import (  # noqa: E402
    build_identity_evidence_inventory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild the read-only identity evidence inventory")
    parser.add_argument("--decision-date", default="2026-10-01")
    parser.add_argument("--valid-on-date")
    args = parser.parse_args()
    result = build_identity_evidence_inventory(
        ROOT,
        decision_date=args.decision_date,
        valid_on_date=args.valid_on_date,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"identity evidence inventory failed closed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)

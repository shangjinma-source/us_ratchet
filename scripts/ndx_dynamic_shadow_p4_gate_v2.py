r"""Assess the proposed dynamic P4 gate without granting registration authority.

PowerShell:
    python -B scripts\ndx_dynamic_shadow_p4_gate_v2.py --readiness
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_p4_gate_v2 import (  # noqa: E402
    assess_proposed_dynamic_p4_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the proposed dynamic P4 research gate",
    )
    parser.add_argument("--readiness", action="store_true")
    args = parser.parse_args()
    if not args.readiness:
        parser.error("only --readiness is supported")
    result = assess_proposed_dynamic_p4_gate(
        ROOT / "config/ndx_dynamic_shadow_p4_gate_v2.yaml",
        repository_root=ROOT,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"dynamic P4 v2 assessment failed closed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)

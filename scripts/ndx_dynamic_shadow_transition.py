"""Read-only CLI for the P5 gradual new-money transition preregistration."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_transition import assess_transition_readiness, load_transition_contract


def main() -> int:
    contract_path = ROOT / "config/ndx_dynamic_shadow_transition_v1.yaml"
    result = assess_transition_readiness(
        load_transition_contract(contract_path), repository_root=ROOT,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

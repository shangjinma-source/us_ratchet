from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIG_PATH = ROOT / "config" / "ndx_dynamic_shadow_search_budget_v1.yaml"
MODULE_PATH = ROOT / "backtest" / "ndx_dynamic_shadow_search_budget.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_readiness() -> dict[str, object]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if config.get("status") != "VERSIONED_V2_CONTROLLER_INTEGRATED_NOT_SCHEDULED":
        raise ValueError("search budget policy must remain unscheduled before task migration")
    activation = config.get("activation", {})
    if (
        activation.get("active_executor_integration") is not True
        or activation.get("activation_version_migration_required") is not True
        or activation.get("promotion_allowed") is not False
        or activation.get("live_allowed") is not False
    ):
        raise ValueError("search budget activation boundary changed")
    return {
        "manifest_type": "ndx_dynamic_shadow_search_budget_readiness",
        "schema_version": 1,
        "status": "READY_FOR_VERSIONED_V2_ACTIVATION_MIGRATION_PLAN_ONLY",
        "active_executor_integration": True,
        "activation_version_migration_required": True,
        "current_registered_task_unchanged": True,
        "enforcement_claimed": True,
        "promotion_allowed": False,
        "live_allowed": False,
        "canonical_inputs": {
            "policy": {"path": str(CONFIG_PATH), "sha256": _sha256(CONFIG_PATH)},
            "module": {"path": str(MODULE_PATH), "sha256": _sha256(MODULE_PATH)},
            "script": {"path": str(Path(__file__).resolve()), "sha256": _sha256(Path(__file__).resolve())},
        },
        "next_required_action": (
            "CREATE_NEW_VERSIONED_FRESH_SEARCH_AND_ACTIVATION_LINEAGE_THEN_BIND_SCHEDULED_DAILY"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness", action="store_true")
    args = parser.parse_args()
    if not args.readiness:
        parser.error("only --readiness is supported; this module does not execute search")
    print(json.dumps(build_readiness(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

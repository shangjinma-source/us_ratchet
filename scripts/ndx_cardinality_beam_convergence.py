"""Run preregistered synthetic beam-width convergence diagnostics."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_beam_convergence import audit_beam_width_convergence
from backtest.ndx_cardinality_discovery import synthetic_fixture
from core.helpers import atomic_write_text
from data.versioning import file_sha256


class NdxCardinalityBeamConvergenceError(ValueError):
    pass


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run(args: argparse.Namespace) -> dict:
    config_path = _resolve(args.config)
    output = _resolve(args.output_dir)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if (
        config.get("research_track") != "portfolio_optimization"
        or config.get("migration_control_included") is not False
        or config.get("promotion_allowed") is not False
    ):
        raise NdxCardinalityBeamConvergenceError("beam convergence contract is unsafe")
    contract = config["diagnostic_contract"]
    frames: list[pd.DataFrame] = []
    audits: list[dict] = []
    for seed in contract["fixture_seeds"]:
        universe, returns, target, incumbent = synthetic_fixture(
            seed=int(seed), business_days=int(contract["business_days"])
        )
        frame, audit = audit_beam_width_convergence(
            universe,
            returns,
            target,
            incumbent,
            holding_count=int(contract["holding_count"]),
            beam_widths=contract["beam_widths"],
            search_kwargs={
                "window_days": int(contract["window_days"]),
                "step_days": int(contract["step_days"]),
                "fit_days": int(contract["fit_days"]),
                "transaction_cost_bps": float(contract["transaction_cost_bps"]),
                "weight_specs": tuple(contract["weight_specifications"]),
            },
        )
        frame.insert(0, "fixture_seed", int(seed))
        frames.append(frame)
        audits.append({"fixture_seed": int(seed), **audit})
    result = pd.concat(frames, ignore_index=True)
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "beam_width_convergence.csv"
    _atomic_csv(result, result_path)
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_beam_convergence",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "SYNTHETIC_DIAGNOSTIC_COMPLETE_NOT_REAL_ADMISSION",
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "mathematical_bound_certificate_available": False,
        "all_fixture_max_widths_recall_four_objective_winners": all(
            bool(group.sort_values("beam_width").iloc[-1]["all_four_objective_winners_recalled"])
            for _, group in result.groupby("fixture_seed")
        ),
        "all_fixture_max_widths_equal_exact_candidate_set": all(
            bool(group.sort_values("beam_width").iloc[-1]["candidate_set_equals_exact"])
            for _, group in result.groupby("fixture_seed")
        ),
        "promotion_allowed": False,
        "live_mutation": {"config": False, "state": False, "today_advice": False, "orders": False},
        "fixture_audits": audits,
        "inputs": {
            "config": {"path": config_path.as_posix(), "sha256": file_sha256(config_path)},
        },
        "artifacts": {
            "convergence": {
                "path": result_path.as_posix(),
                "rows": len(result),
                "sha256": file_sha256(result_path),
            }
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="动态持仓数多目标 beam 宽度收敛诊断")
    parser.add_argument("--config", default="config/ndx_cardinality_beam_convergence_v1.yaml")
    parser.add_argument(
        "--output-dir", default="data/cache/research/ndx_cardinality_beam_convergence_v1"
    )
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"beam 宽度收敛诊断失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        "beam 宽度收敛诊断完成 | "
        f"four_objectives={payload['all_fixture_max_widths_recall_four_objective_winners']} | "
        f"exact_sets={payload['all_fixture_max_widths_equal_exact_candidate_set']} | "
        "promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

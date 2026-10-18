"""Apply research fills to current broker cost exposure without creating orders."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.broker_account_reconciliation import normalize_broker_positions
from core.helpers import atomic_write_text, resolve
from data.versioning import file_sha256


def _shape(values: dict[str, float]) -> tuple[float, float, float]:
    total = sum(values.values())
    weights = sorted((value / total for value in values.values() if value > 0), reverse=True)
    return weights[0], sum(weights[:3]), 1.0 / sum(weight * weight for weight in weights)


def build_bundle(args) -> dict:
    source_path, fills_path, output_dir = resolve(args.broker_source), resolve(args.fills), resolve(args.output_dir)
    source = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    positions = normalize_broker_positions(source.get("positions") or [])
    fills = pd.read_csv(fills_path)
    base_cost = {row["ticker"]: float(row["cost_basis"]) for row in positions}
    base_top1, base_top3, base_en = _shape(base_cost)
    rows = []
    for (candidate_id, mechanism_id), group in fills.groupby(["candidate_id", "mechanism_id"], sort=True):
        post = dict(base_cost)
        for fill in group.to_dict("records"):
            ticker = str(fill["ticker"])
            post[ticker] = post.get(ticker, 0.0) + float(fill["fill_total_cost_usd"])
        top1, top3, effective_n = _shape(post)
        rows.append({
            "candidate_id": candidate_id, "selection_role": group.iloc[0]["selection_role"],
            "mechanism_id": mechanism_id, "filled_tickers": ",".join(group["ticker"].astype(str)),
            "filled_order_count": len(group), "research_deployed_cost_usd": float(group["fill_total_cost_usd"].sum()),
            "broker_cost_basis_before_usd": sum(base_cost.values()), "broker_cost_basis_after_usd": sum(post.values()),
            "cost_top1_before": base_top1, "cost_top1_after": top1,
            "cost_top3_before": base_top3, "cost_top3_after": top3,
            "effective_n_before": base_en, "effective_n_after": effective_n,
            "broker_only_positions_included": "AVGO,DRAM",
            "portfolio_optimization_track": "VARIABLE_CARDINALITY",
            "migration_control_included": False,
            "historical_research_fill_only": True,
            "promotion_allowed": False,
        })
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "broker_account_cost_concentration_overlay.csv"
    workbook_path = output_dir / "回调候选与汇丰实际账户集中度叠加.xlsx"
    frame = pd.DataFrame(rows)
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    temporary = workbook_path.with_suffix(".tmp.xlsx")
    with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="账户成本集中度叠加", index=False)
        pd.DataFrame(positions).to_excel(writer, sheet_name="券商截图持仓", index=False)
        fills.to_excel(writer, sheet_name="历史研究成交", index=False)
    temporary.replace(workbook_path)
    manifest = {
        "schema_version": 1, "manifest_type": "portfolio_pullback_broker_account_overlay",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "method": "current broker cost basis plus historical research fill cost; not a historical broker-path reconstruction",
        "inputs": {
            "broker_source": {"path": source_path.as_posix(), "sha256": file_sha256(source_path)},
            "fills": {"path": fills_path.as_posix(), "sha256": file_sha256(fills_path)},
        },
        "summary": {"scenario_count": len(frame), "broker_position_count": len(positions), "broker_only_positions_included": ["AVGO", "DRAM"], "promotion_allowed": False},
        "artifacts": {
            "overlay": {"path": csv_path.as_posix(), "rows": len(frame), "sha256": file_sha256(csv_path)},
            "workbook": {"path": workbook_path.as_posix(), "sha256": file_sha256(workbook_path)},
        },
        "guards": {"return_data_read": False, "fresh_oos_consumed": False, "config_changed": False, "state_changed": False, "today_advice_changed": False, "orders_created": False},
    }
    atomic_write_text(output_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="历史回调候选对汇丰实际账户成本集中度叠加（只读）")
    parser.add_argument("--broker-source", default="data/cache/research/broker_account_reconciliation_v1/broker_snapshot_source.yaml")
    parser.add_argument("--fills", default="data/cache/research/portfolio_pullback_pooled_reserve_audit_v1/next_session_fill_replay.csv")
    parser.add_argument("--output-dir", default="data/cache/research/portfolio_pullback_broker_overlay_v1")
    args = parser.parse_args()
    try:
        manifest = build_bundle(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"账户集中度叠加失败: {exc}", file=sys.stderr)
        return 2
    print(f"账户集中度叠加完成 | scenarios={manifest['summary']['scenario_count']} | promotion_allowed=False | live_changed=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

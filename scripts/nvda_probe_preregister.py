"""Create the read-only NVDA control/probe preregistration bundle."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.nvda_probe import NvdaProbePlanError, arm_rows, load_probe_plan, metric_rows
from core.config import load_config
from core.helpers import atomic_write_text, resolve
from core.persist import load_portfolio
from data.versioning import file_sha256


def _artifact(path: Path, rows: int | None = None) -> dict:
    return {"path": path.as_posix(), "rows": rows, "sha256": file_sha256(path), "bytes": path.stat().st_size}


def build_bundle(spec_path: Path, config_path: Path, state_path: Path, audit_path: Path, output_dir: Path) -> dict:
    cfg = load_config(config_path)
    state = load_portfolio(state_path)
    if state is None:
        raise NvdaProbePlanError("portfolio state is required")
    plan, constraints = load_probe_plan(spec_path, cfg=cfg, state=state)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    arms = arm_rows(plan, audit)
    metrics = metric_rows(plan)
    constraint_rows = pd.DataFrame([{"constraint": key, "value": value, "passed": True} for key, value in constraints.items()])
    decision = pd.DataFrame([{
        "研究状态": "FORWARD_WATCH_ONLY",
        "控制臂": plan["control_arm"]["arm_id"],
        "试探臂": plan["probe_arm"]["arm_id"],
        "历史审计区间": json.dumps(audit.get("window"), ensure_ascii=False),
        "历史收益读取": False,
        "fresh_OOS已消费": False,
        "配置已改变": False,
        "state已改变": False,
        "今日建议已改变": False,
        "未晋级原因": "尚无注册日后的6个月/12个独立信号队列；收益和回撤分位不可计算",
    }])

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "arms": output_dir / "arms.csv",
        "metrics": output_dir / "metric_readiness.csv",
        "constraints": output_dir / "constraint_audit.csv",
        "decision": output_dir / "decision.csv",
        "workbook": output_dir / "nvda_probe_preregistration.xlsx",
    }
    arms.to_csv(paths["arms"], index=False, encoding="utf-8-sig")
    metrics.to_csv(paths["metrics"], index=False, encoding="utf-8-sig")
    constraint_rows.to_csv(paths["constraints"], index=False, encoding="utf-8-sig")
    decision.to_csv(paths["decision"], index=False, encoding="utf-8-sig")
    temporary = paths["workbook"].with_name(paths["workbook"].stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            arms.rename(columns={"arm_id":"臂ID","arm_role":"角色","budget_source":"预算来源","bear_action":"熊市动作","order_lots":"单次手数","single_order_cap":"单次上限","cycle_total_cap":"周期总额上限","cooldown_trading_days":"冷却交易日","order_lifetime_sessions":"订单有效交易日","promotion_status":"晋级状态"}).to_excel(writer, sheet_name="两臂固定规格", index=False)
            constraint_rows.rename(columns={"constraint":"约束","value":"值","passed":"通过"}).to_excel(writer, sheet_name="约束审计", index=False)
            metrics.rename(columns={"metric":"指标","value":"值","status":"状态","reason":"原因"}).to_excel(writer, sheet_name="指标就绪", index=False)
            decision.to_excel(writer, sheet_name="结论", index=False)
        os.replace(temporary, paths["workbook"])
    finally:
        if temporary.exists():
            temporary.unlink()

    inputs = {name: {"path": path.as_posix(), "sha256": file_sha256(path)} for name, path in {
        "spec": spec_path, "config": config_path, "state": state_path, "production_audit": audit_path
    }.items()}
    manifest = {
        "schema_version": 1,
        "manifest_type": "nvda_probe_preregistration",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "FORWARD_WATCH_ONLY",
        "plan_id": plan["plan_id"],
        "plan_sha256": constraints["plan_sha256"],
        "return_data_read": False,
        "price_ohlc_read": False,
        "fresh_oos_consumed": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "future_data_guard": "仅登记2026-07-15之后的逐信号日前缀；本命令不计算结果",
        "inputs": inputs,
        "constraints": constraints,
        "artifacts": {name: _artifact(path, None if name == "workbook" else len({"arms":arms,"metrics":metrics,"constraints":constraint_rows,"decision":decision}[name])) for name, path in paths.items()},
    }
    manifest_path = output_dir / "manifest.json"
    atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="NVDA熊市固定小额试探层预注册（只读）")
    parser.add_argument("--spec", default="config/nvda_probe_layer_v1_plan.yaml")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--audit", default="data/cache/research/nvda_tactical_audit_v1/summary.json")
    parser.add_argument("--output-dir", default="data/cache/research/nvda_probe_preregistration_v1")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if not args.plan_only:
        parser.error("add --plan-only; this command never executes an order")
    try:
        manifest = build_bundle(*(resolve(value) for value in (args.spec, args.config, args.state, args.audit, args.output_dir)))
    except (NvdaProbePlanError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"NVDA试探层预注册失败: {exc}", file=sys.stderr)
        return 2
    print(f"NVDA试探层预注册完成 | status={manifest['status']} | return_data_read=False | live_changed=False")
    print(f"Manifest: {resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

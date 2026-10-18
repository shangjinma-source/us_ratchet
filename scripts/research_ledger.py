"""Print the read-only strategy research ledger.

PowerShell / PyCharm terminal:
    python scripts/research_ledger.py
    python scripts/research_ledger.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.candidate_registry import build_static_candidate_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="只读策略研发台账（不写 config/state）")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    parser.add_argument("--top", type=int, default=20, help="文本模式最多显示条目数")
    args = parser.parse_args()

    ledger = build_static_candidate_registry()
    if args.json:
        print(json.dumps(ledger, ensure_ascii=False, indent=2))
        return 0

    summary = ledger.get("summary") or {}
    governance = summary.get("governance") or {}
    print("\n策略研发台账（read-only）")
    print(f"ledger_id: {summary.get('ledger_id') or '-'}")
    print(
        f"条目 {summary.get('candidate_count') or 0} | "
        f"治理降级 {governance.get('downgraded_count') or 0} | "
        f"配置就绪 {governance.get('config_ready_count') or 0} | "
        f"实盘就绪 {governance.get('live_ready_count') or 0} | "
        f"允许应用 {governance.get('apply_allowed_count') or 0}"
    )
    for entry in (ledger.get("candidates") or [])[:max(0, int(args.top))]:
        promotion = entry.get("promotion") or {}
        blockers = promotion.get("blockers") or []
        print(
            f"- {entry.get('name')}: {entry.get('source_stage')} -> {entry.get('stage')} | "
            f"证据 {promotion.get('evidence_grade')} "
            f"({float(promotion.get('evidence_score') or 0):.0%}) | "
            f"apply={promotion.get('apply_allowed')}"
        )
        print(f"  假设: {entry.get('hypothesis') or '-'}")
        print(f"  下一缺口: {', '.join(blockers) if blockers else '无'}")
    print("说明: 台账不接入 /api/state，不写 config.yaml；用户确认前禁止应用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

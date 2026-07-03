"""状态持久化：Portfolio ⇄ JSON（Windows 原子写）。重启不丢，可手动 patch。

落盘内容：每标的 H、各档 armed、已投放储备、累计注资、成本基础、pending 分批、
冻结状态、触发记录；现金流账；以及实盘交易日序号（day_index/last_run_date）。
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from core.helpers import atomic_write_text, resolve
from core.state import CashFlow, Portfolio, SymbolState

AUDIT_PATH = "data/audit.jsonl"


def save_portfolio(pf: Portfolio, path: str | Path) -> None:
    data = {
        "symbols": {t: s.to_dict() for t, s in pf.symbols.items()},
        "flows": [vars(f) for f in pf.flows],
        "day_index": pf.day_index,
        "last_run_date": pf.last_run_date,
        "safe_ticker": pf.safe_ticker,
        "safe_shares": pf.safe_shares,
        "target_safe_weight": pf.target_safe_weight,
    }
    atomic_write_text(resolve(path), json.dumps(data, ensure_ascii=False, indent=2))


def load_portfolio(path: str | Path) -> Portfolio | None:
    p = resolve(path)
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    symbols = {t: SymbolState.from_dict(d) for t, d in data.get("symbols", {}).items()}
    flows = [CashFlow(**fl) for fl in data.get("flows", [])]
    return Portfolio(symbols=symbols, flows=flows,
                     day_index=int(data.get("day_index", 0)),
                     last_run_date=str(data.get("last_run_date", "")),
                     safe_ticker=str(data.get("safe_ticker", "SGOV")),
                     safe_shares=float(data.get("safe_shares", 0.0)),
                     target_safe_weight=float(data.get("target_safe_weight", 0.0)))


def backup_state(path: str | Path) -> Path | None:
    """改动前把 state 备份到 .bak，patch 失误可恢复。"""
    p = resolve(path)
    if not p.exists():
        return None
    bak = p.with_suffix(p.suffix + ".bak")
    shutil.copy2(p, bak)
    return bak


def audit_log(action: str, detail: dict, note: str = "",
              path: str | Path = AUDIT_PATH) -> None:
    """所有人工改动留痕（who 恒为用户 / when / what / why），追加 JSONL。"""
    rec = {"ts": datetime.now().isoformat(timespec="seconds"),
           "action": action, "detail": detail, "note": note}
    p = resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
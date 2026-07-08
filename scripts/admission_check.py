"""Small self-check for the research admission gate.

Run:
    python scripts/admission_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.admission import AdmissionProfile, evaluate_admission
from backtest.live_gate import evaluate_preference_live_gate


def _row(**overrides):
    base = {
        "xirr_vs_current": 0.012,
        "dd_relief_vs_current": 0.018,
        "rolling": {
            "candidate_rate": 0.67,
            "win_rate": 0.75,
            "dd_win_rate": 0.70,
            "xirr_vs_current": {"p10": -0.006, "p50": 0.004, "p90": 0.020},
            "dd_relief_vs_current": {"p10": -0.004, "p50": 0.006, "p90": 0.030},
        },
    }
    base.update(overrides)
    return base


def main() -> None:
    market = {"regime": "NEUTRAL", "label": "震荡"}
    profile = AdmissionProfile(
        name="check",
        benchmark="当前参数",
        x_field="xirr_vs_current",
        dd_field="dd_relief_vs_current",
        market_mode="structural",
    )

    assert evaluate_admission(_row(), profile, market)["stage"] == "candidate"
    assert evaluate_admission(_row(is_current=True), profile, market)["stage"] == "show"

    weak_roll = _row(rolling={
        "candidate_rate": 0.25,
        "win_rate": 0.40,
        "dd_win_rate": 0.70,
        "xirr_vs_current": {"p10": -0.020, "p50": -0.002, "p90": 0.010},
        "dd_relief_vs_current": {"p10": 0.001, "p50": 0.006, "p90": 0.020},
    })
    assert evaluate_admission(weak_roll, profile, market)["stage"] == "defer"

    blocked = AdmissionProfile(
        name="blocked",
        benchmark="长期持有",
        x_field="xirr_vs_current",
        dd_field="dd_relief_vs_current",
        live_block="主动卖出类规则不进今日建议。",
    )
    assert evaluate_admission(_row(), blocked, market)["stage"] == "defer"

    pref_research = {
        "summary": {"target_benchmark": "012922", "total_cap": 10000},
        "rows": [{
            "basket": "top6_attack_score_risk",
            "defense_mode": "static_safe_weight",
            "safe_weight": 0.14,
            "tickers": ["NVDA", "AVGO"],
            "weights": {"NVDA": 0.55, "AVGO": 0.45},
            "windows": 8,
            "win_rate": 0.75,
            "dd_win_rate": 0.25,
            "excess_p50": 0.04,
            "dd_relief_p50": -0.10,
            "admission": {"stage": "candidate", "label": "收益候选",
                          "reason": "回撤仍深于目标。"},
        }],
    }
    gate = evaluate_preference_live_gate(pref_research, market=market)
    assert gate["decision"] == "BLOCKED_BY_ADMISSION"
    assert gate["does_change_today_advice"] is False

    pref_research["rows"][0]["dd_relief_p50"] = 0.01
    pref_research["rows"][0]["xirr_p50"] = 0.16
    pref_research["rows"][0]["maxdd_p50"] = 0.30
    pref_research["rows"][0]["admission"] = {"stage": "eligible", "label": "可继续验证"}
    pref_research["summary"]["incumbent_guard"] = {
        "available": True,
        "xirr_p50": 0.15,
        "maxdd_p50": 0.31,
    }
    gate = evaluate_preference_live_gate(pref_research, market=market)
    assert gate["decision"] == "RESEARCH_CANDIDATE_ONLY"
    assert gate["live_connected"] is False

    pref_research["summary"]["incumbent_guard"] = {
        "available": True,
        "xirr_p50": 0.17,
        "maxdd_p50": 0.28,
    }
    gate = evaluate_preference_live_gate(pref_research, market=market)
    assert gate["decision"] == "BLOCKED_BY_INCUMBENT"
    print("admission_check ok")


if __name__ == "__main__":
    main()

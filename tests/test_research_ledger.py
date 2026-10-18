from __future__ import annotations

import unittest

from backtest.candidate_registry import build_candidate_registry
from backtest.research_ledger import enrich_ledger_entry, finalize_research_ledger


def _candidate(stage: str = "config_candidate", **overrides) -> dict:
    candidate = {
        "name": "dynamic candidate",
        "source": "dynamic_basket_live_gate",
        "candidate_key": "dynamic_preference_basket",
        "stage": stage,
        "stage_label": stage,
        "historical_result": {"summary": "相对 012922 有正超额"},
        "rolling_result": {
            "windows": 18,
            "range": ["2022-01-11", "2023-06-01"],
            "summary": "18 个滚动窗口",
        },
        "vs_012922": {
            "summary": "相对012922 XIRR +3.00pct；回撤更浅 1.0pct",
            "target_benchmark": "012922",
        },
        "vs_current_config": {
            "passed": True,
            "summary": "paired incumbent guard passed",
        },
        "drawdown_tradeoff": "风险包络通过",
        "today_advice_impact": {
            "evaluated": True,
            "would_change": True,
            "summary": "已生成 today diff",
            "changes": [{"ticker": "NVDA", "action": "resize"}],
        },
        "detail": {
            "risk_envelope": {"passed": True, "stage": "RISK_SCREEN_PASSED"},
            "data_versions": {
                "fund": {"version_id": "fund_nav:012922:test"},
                "prices": {"version_id": "normalized_close:test"},
            },
        },
        "governance_evidence": {
            "point_in_time": {
                "status": "validated",
                "passed": True,
                "evidence": "walk-forward selection",
            },
            "sample_out": {
                "status": "validated",
                "passed": True,
                "evidence": "held-out regime",
            },
        },
        "rollback_protocol": {
            "prepared": True,
            "old_config_snapshot_id": "config:test-old",
            "replacement_reason": "validated improvement",
            "old_vs_new_today_available": True,
        },
        "user_confirmation": {"confirmed": False},
    }
    candidate.update(overrides)
    return candidate


class ResearchLedgerTests(unittest.TestCase):
    def test_missing_evidence_downgrades_source_config_candidate(self):
        candidate = _candidate(
            detail={"risk_envelope": {"passed": True}},
            governance_evidence={},
            rollback_protocol={},
            today_advice_impact={"evaluated": False, "would_change": False},
        )

        entry = enrich_ledger_entry(candidate, computed=True)

        self.assertEqual(entry["source_stage"], "config_candidate")
        self.assertEqual(entry["stage"], "watch")
        self.assertTrue(entry["promotion"]["downgraded"])
        self.assertIn("data_version", entry["promotion"]["next_required_checks"])
        self.assertIn("sample_out", entry["promotion"]["next_required_checks"])
        self.assertFalse(entry["promotion"]["apply_allowed"])

    def test_live_eligible_still_requires_explicit_user_confirmation_to_apply(self):
        entry = enrich_ledger_entry(_candidate(stage="live_eligible"), computed=True)

        self.assertEqual(entry["stage"], "live_eligible")
        self.assertTrue(entry["promotion"]["live_ready"])
        self.assertFalse(entry["promotion"]["apply_allowed"])

        incomplete_confirmation = enrich_ledger_entry(
            _candidate(stage="live_eligible", user_confirmation={"confirmed": True}),
            computed=True,
        )
        self.assertFalse(incomplete_confirmation["promotion"]["apply_allowed"])

        confirmed = _candidate(
            stage="live_eligible",
            user_confirmation={
                "confirmed": True,
                "confirmed_at": "2026-07-10T12:00:00+08:00",
                "confirmation_id": "user:test",
            },
        )
        confirmed_entry = enrich_ledger_entry(confirmed, computed=True)
        self.assertTrue(confirmed_entry["promotion"]["apply_allowed"])

    def test_governance_never_promotes_a_watch_source(self):
        entry = enrich_ledger_entry(_candidate(stage="watch"), computed=True)

        self.assertEqual(entry["source_stage"], "watch")
        self.assertEqual(entry["stage"], "watch")
        self.assertFalse(entry["promotion"]["downgraded"])

    def test_incomplete_rollback_caps_live_source_at_config_candidate(self):
        entry = enrich_ledger_entry(
            _candidate(
                stage="live_eligible",
                rollback_protocol={
                    "prepared": True,
                    "old_vs_new_today_available": True,
                },
            ),
            computed=True,
        )

        self.assertEqual(entry["stage"], "config_candidate")
        self.assertFalse(entry["promotion"]["live_ready"])
        self.assertIn("rollback", entry["promotion"]["next_required_checks"])

    def test_ledger_ids_are_stable_for_identical_evidence(self):
        first_entries, first_summary = finalize_research_ledger(
            [_candidate()], computed=True
        )
        second_entries, second_summary = finalize_research_ledger(
            [_candidate()], computed=True
        )

        self.assertEqual(
            first_entries[0]["ledger"]["entry_id"],
            second_entries[0]["ledger"]["entry_id"],
        )
        self.assertEqual(first_summary["ledger_id"], second_summary["ledger_id"])
        self.assertEqual(first_summary["apply_allowed_count"], 0)

    def test_registry_forwards_existing_range_and_downgrades_missing_oos(self):
        param_scan = {
            "range": ["2015-01-02", "2026-07-09"],
            "data_versions": {"prices": {"version_id": "prices:test"}},
            "rows": [{
                "is_current": False,
                "label": "candidate params",
                "xirr_vs_current": 0.01,
                "dd_relief_vs_current": 0.01,
                "verdict": "候选：优于当前参数",
                "admission": {"stage": "eligible", "reason": "passed"},
                "metrics": {"xirr": 0.2, "maxdd": 0.2},
                "rolling": {
                    "windows": 12,
                    "candidate_rate": 0.75,
                    "xirr_vs_current": {"p50": 0.01},
                    "dd_relief_vs_current": {"p50": 0.01},
                },
            }],
        }

        ledger = build_candidate_registry(param_scan=param_scan)
        entry = ledger["candidates"][0]

        self.assertEqual(entry["source_stage"], "config_candidate")
        self.assertEqual(entry["stage"], "watch")
        self.assertTrue(entry["research_window"]["documented"])
        self.assertIn("prices:test", entry["data_provenance"]["version_ids"])
        self.assertEqual(entry["promotion"]["next_required_checks"], [
            "sample_out", "today_diff", "rollback"
        ])

    def test_ndx_individual_stock_competition_is_rejected_when_validation_fails(self):
        ndx_result = {
            "summary": {
                "qqq_role": "benchmark_only_not_candidate",
                "best_qqq": {
                    "basket": "top10_source_weight",
                    "lookback_years": 2.0,
                    "top_n": 10,
                    "rebalance_months": 6,
                    "max_weight": 0.35,
                    "windows": 37,
                    "range": ["2022-01-11", "2025-01-02"],
                    "win_rate": 0.0,
                    "dd_win_rate": 0.0,
                    "excess_p50": -0.46,
                    "dd_relief_p50": -0.065,
                    "qqq_win_rate": 0.51,
                    "qqq_excess_p50": 0.001,
                    "qqq_dd_relief_p50": -0.035,
                    "target_envelope": {
                        "passed": False,
                        "reason": "relative target return failed",
                    },
                    "incumbent_guard": {
                        "passed": False,
                        "reason": "incumbent guard failed",
                        "margins": {"xirr_p50_vs_incumbent": -0.17},
                    },
                    "admission_passed": False,
                },
            },
            "data_manifest": {
                "ndx_history": {
                    "version_id": "ndx_point_in_time_constituents:test",
                },
                "price_universe": {
                    "version_id": "ndx_price_universe:test",
                },
                "future_data_guard": "available_date <= selection_date",
            },
            "current_selection_best_qqq": {
                "available": True,
                "holdings": [{"ticker": "AAPL", "portfolio_weight": 1.0}],
            },
        }

        ledger = build_candidate_registry(
            ndx_competition=ndx_result,
            include_heavy=True,
        )
        entry = next(
            row for row in ledger["candidates"]
            if row["source"] == "ndx_competition"
        )

        self.assertEqual(entry["source_stage"], "rejected")
        self.assertEqual(entry["stage"], "rejected")
        self.assertTrue(entry["point_in_time"]["passed"])
        self.assertFalse(entry["sample_out"]["passed"])
        self.assertFalse(entry["vs_012922"]["passed"])
        self.assertIn("ndx_price_universe:test", entry["data_provenance"]["version_ids"])
        self.assertIn("sample_out", entry["promotion"]["next_required_checks"])
        self.assertIn("vs_012922", entry["promotion"]["next_required_checks"])
        self.assertIn("risk_gate", entry["promotion"]["next_required_checks"])
        self.assertEqual(
            entry["research_lifecycle"]["direction_status"], "active_iteration"
        )
        self.assertFalse(
            entry["research_lifecycle"]["terminal_direction_decision"]
        )


if __name__ == "__main__":
    unittest.main()

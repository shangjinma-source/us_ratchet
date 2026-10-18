from __future__ import annotations

import copy
import unittest
from pathlib import Path

import pandas as pd
import yaml

from data.ndx_event_gap_disposition import (
    NdxEventGapDispositionError,
    build_scope_rows,
    disposition_summary,
    validate_config,
)


ROOT = Path(__file__).resolve().parents[1]


class NdxEventGapDispositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = yaml.safe_load(
            (ROOT / "config" / "ndx_event_gap_dispositions.yaml").read_text(
                encoding="utf-8"
            )
        )
        base = ROOT / "data" / "cache" / "candidate_pools" / "ndx_history"
        cls.exact = base / "exact_events"
        cls.proxy = base / "event_proxy_audit"

    def test_verified_gap_scope_contains_ceg_and_gral_without_promotion(self):
        scope = build_scope_rows(
            self.config,
            exact_gaps=pd.read_csv(self.exact / "unresolved_gaps.csv", dtype=str),
            exact_source_audit=pd.read_csv(self.exact / "source_audit.csv", dtype=str),
            proxy_gaps=pd.read_csv(self.proxy / "unresolved_proxy_gaps.csv", dtype=str),
        )
        self.assertEqual(set(scope["ticker"]), {"CEG", "GRAL"})
        self.assertTrue(scope["evidence_match"].astype(bool).all())
        self.assertFalse(scope["promotion_allowed"].astype(bool).any())
        gral = scope.loc[scope["ticker"].eq("GRAL")].iloc[0]
        self.assertEqual(gral["status"], "partial_exact_event_locked")
        self.assertTrue(gral["exact_addition_supported"])
        self.assertFalse(gral["exact_removal_date_supported"])
        self.assertEqual(gral["blocked_selection_start"], "2024-06-24")
        self.assertEqual(gral["blocked_selection_end"], "2026-03-31")
        summary = disposition_summary(scope)
        self.assertTrue(summary["scope_lock_complete"])
        self.assertFalse(summary["historical_backtest_allowed"])
        self.assertTrue(summary["v11_plan_registration_allowed"])
        self.assertFalse(summary["v11_execution_allowed"])
        self.assertEqual(summary["partial_exact_addition_count"], 1)
        self.assertEqual(summary["unresolved_removal_date_count"], 1)

    def test_proxy_weight_mismatch_fails_closed(self):
        invalid = copy.deepcopy(self.config)
        invalid["cases"][1]["expected_proxy_weight"] = 0.1
        with self.assertRaisesRegex(NdxEventGapDispositionError, "evidence mismatch"):
            build_scope_rows(
                invalid,
                exact_gaps=pd.read_csv(self.exact / "unresolved_gaps.csv", dtype=str),
                exact_source_audit=pd.read_csv(self.exact / "source_audit.csv", dtype=str),
                proxy_gaps=pd.read_csv(self.proxy / "unresolved_proxy_gaps.csv", dtype=str),
            )

    def test_config_remains_research_only_and_backtest_blocked(self):
        normalized = validate_config(self.config)
        self.assertTrue(normalized["research_only"])
        self.assertFalse(normalized["historical_backtest_allowed"])
        self.assertFalse(normalized["v11_execution_allowed"])


if __name__ == "__main__":
    unittest.main()

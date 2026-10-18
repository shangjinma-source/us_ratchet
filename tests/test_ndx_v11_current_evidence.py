from __future__ import annotations

import unittest

import pandas as pd

from data.ndx_v11_current_evidence import (
    build_quality_input_readiness,
    build_security_evidence_gate,
    build_valuation_gate_summary,
)


class NdxV11CurrentEvidenceTests(unittest.TestCase):
    def _factor_inputs(self, *, missing_factor: str | None = None) -> pd.DataFrame:
        factors = [
            "revenue_growth",
            "operating_margin",
            "free_cash_flow_margin",
            "operating_cash_flow_to_assets",
            "equity_to_assets",
            "cash_to_assets",
            "net_margin",
            "research_and_development_intensity",
        ]
        row = {
            "selection_date": "2026-07-13",
            "ticker": "AAA",
            "cik": 1001,
        }
        for factor in factors:
            row[f"{factor}_status"] = (
                "missing_component" if factor == missing_factor else "ready"
            )
        return pd.DataFrame([row])

    def test_quality_input_readiness_is_unranked_and_fail_closed(self):
        ready, coverage = build_quality_input_readiness(self._factor_inputs())

        self.assertTrue(bool(ready.loc[0, "quality_factor_input_ready"]))
        self.assertFalse(bool(ready.loc[0, "quality_score_generated"]))
        self.assertFalse(bool(ready.loc[0, "quality_score_allowed"]))
        self.assertEqual(float(coverage.loc[0, "quality_factor_input_coverage"]), 1.0)

        incomplete_input = self._factor_inputs(missing_factor="operating_margin")
        incomplete_input["free_cash_flow_margin_status"] = "missing_component"
        incomplete, _ = build_quality_input_readiness(incomplete_input)
        self.assertFalse(bool(incomplete.loc[0, "quality_factor_input_ready"]))
        self.assertIn("profitability_factor_count", incomplete.loc[0, "quality_factor_blockers"])

    def test_security_gate_keeps_unclassified_and_candidate_closed(self):
        quality, _ = build_quality_input_readiness(self._factor_inputs())
        valuation_raw = pd.DataFrame([{
            "selection_date": "2026-07-13",
            "ticker": "AAA",
            "cik": 1001,
            "fcf_yield_ready": False,
            "ev_sales_ready": False,
            "fcf_yield_accounting_ready": False,
            "ev_sales_accounting_ready": False,
            "fcf_yield_blockers": "shares:missing",
            "ev_sales_blockers": "debt:missing",
            "valuation_scoring_allowed": False,
            "shares_ready": False,
            "debt_ready": False,
            "price_ready": True,
        }])
        valuation, _ = build_valuation_gate_summary(valuation_raw)
        observations = pd.DataFrame([{
            "observation_date": "2026-07-13",
            "ticker": "AAA",
            "cik": 1001,
            "security_id": "security:AAA",
            "issuer_id": "issuer:AAA",
            "risk_chain": "unclassified",
            "taxonomy_status": "unclassified",
        }])

        result = build_security_evidence_gate(observations, quality, valuation)

        self.assertEqual(result.loc[0, "evidence_gate_status"], "blocked")
        self.assertFalse(bool(result.loc[0, "candidate_admission_allowed"]))
        self.assertIn("taxonomy_current_evidence_missing_or_unclassified", result.loc[0, "evidence_gate_blockers"])
        self.assertIn("valuation_accounting_evidence_incomplete", result.loc[0, "evidence_gate_blockers"])

    def test_qqq_is_rejected_from_current_evidence(self):
        quality, _ = build_quality_input_readiness(self._factor_inputs())
        valuation_raw = pd.DataFrame([{
            "selection_date": "2026-07-13",
            "ticker": "QQQ",
            "cik": 1001,
            "fcf_yield_ready": False,
            "ev_sales_ready": False,
            "fcf_yield_accounting_ready": False,
            "ev_sales_accounting_ready": False,
            "fcf_yield_blockers": "candidate_excluded",
            "ev_sales_blockers": "candidate_excluded",
            "valuation_scoring_allowed": False,
            "shares_ready": False,
            "debt_ready": False,
            "price_ready": False,
        }])
        valuation, _ = build_valuation_gate_summary(valuation_raw)
        observations = pd.DataFrame([{
            "observation_date": "2026-07-13",
            "ticker": "QQQ",
            "cik": 1001,
            "security_id": "security:QQQ",
            "issuer_id": "issuer:QQQ",
            "risk_chain": "unclassified",
            "taxonomy_status": "unclassified",
        }])

        with self.assertRaises(ValueError):
            build_security_evidence_gate(observations, quality, valuation)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.ndx_cardinality_input_readiness import (
    audit_membership_inputs,
    lifecycle_identity_audit,
    rebuild_job_readiness,
)
from data.versioning import file_sha256


class NdxCardinalityInputReadinessTests(unittest.TestCase):
    def test_worker_training_history_requirement_is_audited_before_queueing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dates = pd.date_range("2021-01-01", periods=400, freq="B")
            selection = dates[180]
            maturity = dates[319]
            pd.DataFrame({"Date": dates, "Close": range(100, 500)}).to_csv(
                root / "A.csv", index=False
            )
            memberships = pd.DataFrame([{
                "universe_track": "strict_technology",
                "selection_date": selection.date().isoformat(),
                "maturity_date": maturity.date().isoformat(),
                "ticker": "A", "security_id": "s1", "issuer_id": "i1",
                "membership_window_eligible": True,
            }])
            target = pd.Series(range(400), index=dates, dtype=float)
            result = audit_membership_inputs(
                memberships, return_cache_dir=root, target_nav=target,
                identity_audit=pd.DataFrame(), fit_days=126, horizon_days=126,
                target_endpoint_tolerance_days=10,
            )
        self.assertEqual(int(result.iloc[0]["minimum_training_price_rows"]), 253)
        self.assertFalse(bool(result.iloc[0]["training_price_ready"]))
        self.assertEqual(result.iloc[0]["readiness_reason"], "PRICE_COVERAGE_INSUFFICIENT")

    def test_target_training_history_is_required_before_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dates = pd.date_range("2021-01-01", periods=500, freq="B")
            pd.DataFrame({"Date": dates, "Close": range(100, 600)}).to_csv(
                root / "A.csv", index=False
            )
            selection = dates[300]
            maturity = dates[439]
            memberships = pd.DataFrame([{
                "universe_track": "strict_technology",
                "selection_date": selection.date().isoformat(),
                "maturity_date": maturity.date().isoformat(),
                "ticker": "A", "security_id": "s1", "issuer_id": "i1",
                "membership_window_eligible": True,
            }])
            target = pd.Series(
                range(240), index=dates[200:440], dtype=float,
            )
            result = audit_membership_inputs(
                memberships, return_cache_dir=root, target_nav=target,
                identity_audit=pd.DataFrame(), fit_days=126, horizon_days=126,
                target_endpoint_tolerance_days=10,
            )
        self.assertFalse(bool(result.iloc[0]["target_training_ready"]))
        self.assertEqual(
            result.iloc[0]["readiness_reason"],
            "TARGET_NAV_TRAINING_HISTORY_INSUFFICIENT",
        )

    def test_lifecycle_identity_mismatch_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            returns = root / "returns"
            evidence = root / "evidence"
            returns.mkdir()
            evidence.mkdir()
            pd.DataFrame({"Date": ["2022-06-08"], "Close": [40.0]}).to_csv(
                returns / "FB.csv", index=False
            )
            evidence_path = evidence / "FB.csv"
            pd.DataFrame({"Date": ["2022-06-08"], "Close": [200.0]}).to_csv(
                evidence_path, index=False
            )
            Path(f"{evidence_path}.manifest.json").write_text(json.dumps({
                "content_sha256": file_sha256(evidence_path),
                "price_basis": "unadjusted_nominal_trade_price",
            }), encoding="utf-8")
            memberships = pd.DataFrame([{
                "ticker": "FB", "issuer_id": "issuer:meta",
                "price_ticker_resolution": "reviewed_ticker_lifecycle",
            }])
            result = lifecycle_identity_audit(
                memberships,
                return_cache_dir=returns,
                identity_evidence_dir=evidence,
                relative_tolerance=0.02,
            )
            self.assertEqual(result.iloc[0]["identity_status"], "RETURN_CACHE_IDENTITY_MISMATCH")
            self.assertFalse(bool(result.iloc[0]["return_usage_of_identity_evidence"]))

    def test_degraded_jobs_recompute_feasible_space_after_exclusion(self):
        jobs = pd.DataFrame([
            {
                "universe_track": "strict_technology", "selection_date": "2022-03-01",
                "holding_count": k, "shard_id": "0000", "promotion_allowed": False,
            }
            for k in (1, 2)
        ])
        audit = pd.DataFrame([
            {
                "universe_track": "strict_technology", "selection_date": "2022-03-01",
                "ticker": "A", "security_id": "s1", "issuer_id": "i1",
                "input_ready": True, "target_nav_ready": True, "readiness_reason": "READY",
            },
            {
                "universe_track": "strict_technology", "selection_date": "2022-03-01",
                "ticker": "FB", "security_id": "s2", "issuer_id": "i2",
                "input_ready": False, "target_nav_ready": True,
                "readiness_reason": "ISSUER_LIFECYCLE_IDENTITY_CHAIN_INCOMPLETE",
            },
        ])
        result = rebuild_job_readiness(jobs, audit, exact_limit=50_000)
        by_k = result.set_index("holding_count")
        self.assertFalse(bool(by_k.loc[1, "complete_universe_job_ready"]))
        self.assertTrue(bool(by_k.loc[1, "degraded_research_job_ready"]))
        self.assertEqual(by_k.loc[1, "degraded_issuer_dedup_feasible_combinations"], 1)
        self.assertFalse(bool(by_k.loc[2, "degraded_research_job_ready"]))
        self.assertIn("i2", by_k.loc[1, "excluded_issuer_ids"])


if __name__ == "__main__":
    unittest.main()

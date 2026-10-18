from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from data.ndx_event_proxy_audit import (
    audit_event_actions,
    audit_metrics,
    build_unresolved_proxy_gaps,
    load_alias_registry,
    load_verified_proxy,
)


ROOT = Path(__file__).resolve().parents[1]


class NdxEventProxyAuditTests(unittest.TestCase):
    def test_verified_local_qqq_proxy_is_point_in_time(self) -> None:
        path = ROOT / "data" / "cache" / "candidate_pools" / "ndx_history" / "qqq_nport_constituents.csv"
        frame, manifest = load_verified_proxy(path)
        self.assertEqual(manifest["dataset_key"], "qqq_nport_public_filings")
        self.assertEqual(frame["report_date"].nunique(), 27)

    def test_alias_is_used_without_counting_ticker_transition_as_error(self) -> None:
        proxy = pd.DataFrame([
            {"report_date": "2020-03-31", "available_date": "2020-05-01", "ticker": "SYMC", "accession_number": "a"},
            {"report_date": "2020-06-30", "available_date": "2020-08-01", "ticker": "AAPL", "accession_number": "b"},
        ])
        events = pd.DataFrame([
            {
                "event_id": "rename",
                "event_type": "corporate_action_replacement",
                "effective_date": "2020-03-01",
                "source_available_date": "2020-03-01",
                "action": "remove",
                "ticker": "SYMC",
                "future_data_guard": True,
                "notes": "",
            },
        ])
        aliases = {
            "groups": [
                {
                    "group_id": "symc_nlok",
                    "tickers": ["SYMC", "NLOK"],
                    "canonical_ticker": "SYMC",
                    "evidence_source": "test",
                    "evidence_available_date": "2020-04-01",
                    "notes": "",
                }
            ]
        }
        actions, _, _ = audit_event_actions(events, proxy, aliases)
        self.assertEqual(actions.iloc[0]["proxy_status"], "quarterly_proxy_lag_until_correct_snapshot")
        self.assertFalse(bool(actions.iloc[0]["first_post_event_correct"]))
        self.assertEqual(actions.iloc[0]["first_correct_report_date"], "2020-06-30")

    def test_metrics_report_first_snapshot_mismatch_and_lag(self) -> None:
        proxy = pd.DataFrame([
            {"report_date": "2020-03-31", "available_date": "2020-05-01", "ticker": "AAPL", "accession_number": "a"},
            {"report_date": "2020-06-30", "available_date": "2020-08-01", "ticker": "AAPL", "accession_number": "b"},
            {"report_date": "2020-09-30", "available_date": "2020-11-01", "ticker": "AAPL", "accession_number": "c"},
        ])
        events = pd.DataFrame([
            {
                "event_id": "add_b",
                "event_type": "interim_replacement",
                "effective_date": "2020-04-01",
                "source_available_date": "2020-04-01",
                "action": "add",
                "ticker": "B",
                "future_data_guard": True,
                "notes": "",
            },
        ])
        aliases = {
            "groups": [],
        }
        actions, summary, reports = audit_event_actions(events, proxy, aliases)
        self.assertEqual(actions.iloc[0]["proxy_status"], "proxy_not_corrected_in_scope")
        metrics = audit_metrics(actions, summary, reports)
        self.assertEqual(metrics["first_post_event_mismatch_count"], 1)
        self.assertEqual(metrics["proxy_not_corrected_action_count"], 1)
        self.assertEqual(metrics["report_state_mismatch_count"], 2)

    def test_proxy_extra_details_are_quantified_without_promotion(self) -> None:
        proxy = pd.DataFrame([
            {"report_date": "2020-03-31", "available_date": "2020-05-01", "ticker": "A", "name": "A", "weight": "0.0001", "value_usd": "10", "cusip": "1", "mapping_method": "test", "accession_number": "a"},
            {"report_date": "2020-06-30", "available_date": "2020-08-01", "ticker": "A", "name": "A", "weight": "0.0001", "value_usd": "10", "cusip": "1", "mapping_method": "test", "accession_number": "b"},
            {"report_date": "2020-06-30", "available_date": "2020-08-01", "ticker": "X", "name": "Extra Corp.", "weight": "0.0002", "value_usd": "25", "cusip": "2", "mapping_method": "sec_company_name_exact", "accession_number": "b"},
        ])
        events = pd.DataFrame([
            {"event_id": "add_b", "event_type": "interim_replacement", "effective_date": "2020-04-01", "source_available_date": "2020-04-01", "action": "add", "ticker": "B", "future_data_guard": True, "notes": ""},
        ])
        aliases = {"groups": []}
        actions, summary, reports = audit_event_actions(events, proxy, aliases)
        self.assertIn("proxy_extra_details", reports.columns)
        details = json.loads(reports.loc[reports["report_date"].eq("2020-06-30"), "proxy_extra_details"].iloc[0])
        self.assertEqual(details[0]["ticker"], "X")
        self.assertEqual(details[0]["name"], "Extra Corp.")
        metrics = audit_metrics(actions, summary, reports)
        self.assertEqual(metrics["proxy_extra_occurrence_count"], 1)
        self.assertEqual(metrics["proxy_extra_ticker_count"], 1)
        self.assertAlmostEqual(metrics["proxy_extra_weight_total"], 0.0002)
        self.assertAlmostEqual(metrics["proxy_extra_value_usd_total"], 25.0)
        gaps = build_unresolved_proxy_gaps(reports)
        extra_gap = gaps.loc[gaps["ticker"].eq("X")].iloc[0]
        self.assertEqual(extra_gap["evidence_status"], "not_promoted_to_exact_event")
        self.assertEqual(extra_gap["proxy_weight"], "0.0002")
        self.assertEqual(extra_gap["proxy_cusip"], "2")


if __name__ == "__main__":
    unittest.main()

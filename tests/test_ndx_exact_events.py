from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data.ndx_exact_events import (
    SOURCE_AUDIT_COLUMNS,
    NdxExactEventsError,
    build_effective_event_rows,
    load_event_registry,
    verify_source_content,
)


ROOT = Path(__file__).resolve().parents[1]


class NdxExactEventsTests(unittest.TestCase):
    def test_real_registry_is_versioned_and_preserves_on_ticker(self) -> None:
        registry = load_event_registry(ROOT / "config" / "ndx_exact_event_sources.yaml")
        self.assertEqual(registry["registry_id"], "ndx_official_nasdaq_events_v1")
        self.assertEqual(len(registry["events"]), 32)
        on_events = [
            event for event in registry["events"]
            if "ON" in event["added_tickers"] or "ON" in event["removed_tickers"]
        ]
        self.assertEqual(len(on_events), 2)
        self.assertEqual(
            registry["scope"],
            {"start": "2019-09-30", "end": "2026-03-31"},
        )

    def test_source_markers_are_case_insensitive_but_ticker_bounded(self) -> None:
        event = {
            "required_tickers": ["ON"],
            "required_phrases": ["June 20, 2023"],
        }
        verified = verify_source_content(
            event,
            b"<html>ON Semiconductor, effective June 20, 2023</html>",
        )
        self.assertTrue(verified["source_verified"])
        not_verified = verify_source_content(
            event,
            b"<html>ONLY, effective June 20, 2023</html>",
        )
        self.assertFalse(not_verified["source_verified"])
        self.assertEqual(not_verified["missing_tickers"], ["ON"])

    def test_registry_rejects_non_nasdaq_source(self) -> None:
        text = """
schema_version: 1
registry_id: test
index: NDX
scope: {start: '2020-01-01', end: '2020-12-31'}
events:
  - event_id: test_event
    event_type: interim_replacement
    event_status: effective
    announcement_date: '2020-01-01'
    effective_date: '2020-01-02'
    source_locator: https://example.com/event
    added_tickers: [AAPL]
    removed_tickers: [MSFT]
    required_phrases: [January]
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.yaml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(NdxExactEventsError):
                load_event_registry(path)

    def test_amended_event_inherits_baseline_and_adds_delta(self) -> None:
        text = """
schema_version: 1
registry_id: test
index: NDX
scope: {start: '2020-01-01', end: '2020-12-31'}
events:
  - event_id: base_event
    event_type: annual_reconstitution
    event_status: superseded_reference
    announcement_date: '2020-01-01'
    effective_date: '2020-01-02'
    source_locator: https://www.nasdaq.com/press-release/base
    added_tickers: [AAPL, MSFT]
    removed_tickers: [XYZ]
    required_phrases: [January]
  - event_id: amended_event
    event_type: annual_reconstitution_update
    event_status: effective
    announcement_date: '2020-01-03'
    effective_date: '2020-01-04'
    source_locator: https://www.nasdaq.com/press-release/amended
    added_tickers: [GOOG]
    removed_tickers: [XYZ]
    required_tickers: [GOOG, XYZ]
    required_phrases: [January]
    base_event_id: base_event
    remove_from_base: []
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.yaml"
            path.write_text(text, encoding="utf-8")
            registry = load_event_registry(path)
        audit = pd.DataFrame([
            {
                "event_id": "base_event",
                "source_verified": True,
            },
            {
                "event_id": "amended_event",
                "source_verified": True,
            },
        ])
        for column in SOURCE_AUDIT_COLUMNS:
            if column not in audit:
                audit[column] = ""
        audit = audit[SOURCE_AUDIT_COLUMNS]
        rows = build_effective_event_rows(registry, audit)
        self.assertEqual(
            set(zip(rows["action"], rows["ticker"])),
            {("add", "AAPL"), ("add", "MSFT"), ("add", "GOOG"), ("remove", "XYZ")},
        )
        self.assertEqual(rows["event_id"].unique().tolist(), ["amended_event"])

    def test_real_registry_marks_post_effective_source_as_guard_gap(self) -> None:
        registry = load_event_registry(ROOT / "config" / "ndx_exact_event_sources.yaml")
        event = next(
            item for item in registry["events"]
            if item["event_id"] == "ndx_interim_constellation_energy_spin_off_2022"
        )
        self.assertEqual(event["source_available_date"], "2022-02-03")
        self.assertGreater(event["source_available_date"], event["effective_date"])


if __name__ == "__main__":
    unittest.main()

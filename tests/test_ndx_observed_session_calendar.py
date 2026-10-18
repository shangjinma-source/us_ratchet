from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest


from backtest.ndx_observed_session_calendar import (
    BOOTSTRAP_ORIGIN,
    NdxObservedSessionCalendarError,
    PROSPECTIVE_ORIGIN,
    append_records_durable,
    load_ledger,
    load_ohlc_rows,
    observed_common_dates,
    prepare_update,
    projection_rows,
    session_timestamps,
    validate_ledger,
)


class NdxObservedSessionCalendarTests(unittest.TestCase):
    def _source(self, root: Path, ticker: str, dates: list[str]) -> Path:
        path = root / f"{ticker}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["Date", "Open", "High", "Low", "Close", "Volume"]
            )
            writer.writeheader()
            for index, value in enumerate(dates, start=1):
                writer.writerow(
                    {
                        "Date": value,
                        "Open": 100 + index,
                        "High": 101 + index,
                        "Low": 99 + index,
                        "Close": 100.5 + index,
                        "Volume": 1_000_000 + index,
                    }
                )
        return path

    def _inputs(self, root: Path, dates: list[str]):
        paths = {ticker: self._source(root, ticker, dates) for ticker in ("QQQ", "SPY")}
        rows = {ticker: load_ohlc_rows(path, ticker=ticker) for ticker, path in paths.items()}
        hashes = {ticker: "a" * 64 if ticker == "QQQ" else "b" * 64 for ticker in paths}
        return paths, rows, hashes

    def test_new_york_timestamps_reflect_dst_without_future_calendar_guess(self) -> None:
        before = session_timestamps("2026-03-06")
        after = session_timestamps("2026-03-09")
        self.assertEqual(before["open_timestamp_ny"], "2026-03-06T09:30:00-05:00")
        self.assertEqual(before["open_timestamp_utc"], "2026-03-06T14:30:00+00:00")
        self.assertEqual(after["open_timestamp_ny"], "2026-03-09T09:30:00-04:00")
        self.assertEqual(after["open_timestamp_utc"], "2026-03-09T13:30:00+00:00")

    def test_in_progress_source_date_is_not_observed_completed_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, rows, _ = self._inputs(Path(directory), ["2026-09-03", "2026-09-04"])
            completed, pending = observed_common_dates(
                rows,
                start_date="2026-09-01",
                observed_at_utc=datetime.fromisoformat("2026-09-04T18:00:00+00:00"),
            )
        self.assertEqual(completed, ["2026-09-03"])
        self.assertEqual(pending, ["2026-09-04"])

    def test_bootstrap_is_sealed_but_never_fresh_decision_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, rows, hashes = self._inputs(Path(directory), ["2026-09-01", "2026-09-02"])
            additions = prepare_update(
                [],
                completed_dates=["2026-09-01", "2026-09-02"],
                tickers=["QQQ", "SPY"],
                source_rows=rows,
                source_snapshot_sha256=hashes,
                prospective_start_date="2026-10-01",
                recorded_at_utc=datetime.fromisoformat("2026-09-03T21:00:00+00:00"),
                bootstrap=True,
            )
            ledger = Path(directory) / "sessions.jsonl"
            append_records_durable(ledger, additions)
            sealed = load_ledger(ledger)
            validate_ledger(
                sealed,
                tickers=["QQQ", "SPY"],
                prospective_start_date="2026-10-01",
                current_source_rows=rows,
            )
        self.assertEqual([row["origin"] for row in sealed], [BOOTSTRAP_ORIGIN] * 2)
        self.assertFalse(any(row["decision_eligible"] for row in sealed))
        self.assertEqual(sealed[1]["previous_record_sha256"], sealed[0]["record_sha256"])

    def test_one_new_observed_session_appends_without_rewriting_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, first_rows, hashes = self._inputs(root, ["2026-09-30"])
            initial = prepare_update(
                [], completed_dates=["2026-09-30"], tickers=["QQQ", "SPY"],
                source_rows=first_rows, source_snapshot_sha256=hashes,
                prospective_start_date="2026-10-01",
                recorded_at_utc=datetime.fromisoformat("2026-10-01T01:00:00+00:00"), bootstrap=True,
            )
            ledger = root / "sessions.jsonl"
            append_records_durable(ledger, initial)
            prefix = ledger.read_bytes()
            _, second_rows, hashes = self._inputs(root, ["2026-09-30", "2026-10-01"])
            additions = prepare_update(
                load_ledger(ledger), completed_dates=["2026-09-30", "2026-10-01"],
                tickers=["QQQ", "SPY"], source_rows=second_rows,
                source_snapshot_sha256=hashes, prospective_start_date="2026-10-01",
                recorded_at_utc=datetime.fromisoformat("2026-10-01T21:00:00+00:00"), bootstrap=False,
            )
            append_records_durable(ledger, additions)
            final = load_ledger(ledger)
            final_bytes = ledger.read_bytes()
        self.assertTrue(final_bytes.startswith(prefix))
        self.assertEqual(len(additions), 1)
        self.assertEqual(final[-1]["origin"], PROSPECTIVE_ORIGIN)
        self.assertTrue(final[-1]["decision_eligible"])

    def test_multiple_missed_sessions_are_not_backfilled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, rows, hashes = self._inputs(
                Path(directory), ["2026-09-30", "2026-10-01", "2026-10-02"]
            )
            existing = prepare_update(
                [], completed_dates=["2026-09-30"], tickers=["QQQ", "SPY"],
                source_rows=rows, source_snapshot_sha256=hashes,
                prospective_start_date="2026-10-01",
                recorded_at_utc=datetime.fromisoformat("2026-10-01T01:00:00+00:00"), bootstrap=True,
            )
            with self.assertRaisesRegex(NdxObservedSessionCalendarError, "backfill is forbidden"):
                prepare_update(
                    existing,
                    completed_dates=["2026-09-30", "2026-10-01", "2026-10-02"],
                    tickers=["QQQ", "SPY"], source_rows=rows,
                    source_snapshot_sha256=hashes, prospective_start_date="2026-10-01",
                    recorded_at_utc=datetime.fromisoformat("2026-10-02T21:00:00+00:00"), bootstrap=False,
                )

    def test_historical_ohlc_revision_and_chain_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, rows, hashes = self._inputs(root, ["2026-09-30"])
            records = prepare_update(
                [], completed_dates=["2026-09-30"], tickers=["QQQ", "SPY"],
                source_rows=rows, source_snapshot_sha256=hashes,
                prospective_start_date="2026-10-01",
                recorded_at_utc=datetime.fromisoformat("2026-10-01T01:00:00+00:00"), bootstrap=True,
            )
            text = paths["QQQ"].read_text(encoding="utf-8")
            paths["QQQ"].write_text(text.replace("101,102", "999,102"), encoding="utf-8")
            revised = {ticker: load_ohlc_rows(path, ticker=ticker) for ticker, path in paths.items()}
            with self.assertRaisesRegex(NdxObservedSessionCalendarError, "OHLC history changed"):
                validate_ledger(
                    records, tickers=["QQQ", "SPY"], prospective_start_date="2026-10-01",
                    current_source_rows=revised,
                )
            tampered = json.loads(json.dumps(records))
            tampered[0]["decision_eligible"] = True
            with self.assertRaisesRegex(NdxObservedSessionCalendarError, "record hash mismatch"):
                validate_ledger(
                    tampered, tickers=["QQQ", "SPY"], prospective_start_date="2026-10-01"
                )

    def test_projection_proves_month_first_and_observed_next_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, rows, hashes = self._inputs(
                Path(directory), ["2026-09-30", "2026-10-01", "2026-10-02"]
            )
            records = prepare_update(
                [], completed_dates=["2026-09-30", "2026-10-01", "2026-10-02"],
                tickers=["QQQ", "SPY"], source_rows=rows, source_snapshot_sha256=hashes,
                prospective_start_date="2026-10-01",
                recorded_at_utc=datetime.fromisoformat("2026-10-03T01:00:00+00:00"), bootstrap=True,
            )
            projection = projection_rows(records)
        self.assertTrue(projection[0]["is_first_observed_session_of_month"])
        self.assertTrue(projection[1]["is_first_observed_session_of_month"])
        self.assertFalse(projection[2]["is_first_observed_session_of_month"])
        self.assertEqual(projection[1]["next_observed_session_date"], "2026-10-02")


if __name__ == "__main__":
    unittest.main()

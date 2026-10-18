from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from backtest.ndx_observed_session_calendar import (
    canonical_sha256,
    file_sha256,
    load_ohlc_rows,
    prepare_update as prepare_v1_update,
)
from backtest.ndx_observed_session_calendar_v2 import (
    NdxObservedSessionCalendarV2Error,
    capture_source_snapshot,
    import_v1_legacy_records,
    load_legacy_v1_evidence,
    prepare_reviewed_update,
    validate_event_ledger,
)


TICKERS = ["QQQ", "SPY"]
CALENDAR_START = "2026-09-30"
PROSPECTIVE_START = "2026-10-01"


class NdxObservedSessionCalendarV2AdversarialTests(unittest.TestCase):
    def _write_sources(self, root: Path, dates: list[str]) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        for ticker_index, ticker in enumerate(TICKERS):
            path = root / f"{ticker}.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["Date", "Open", "High", "Low", "Close", "Volume"],
                )
                writer.writeheader()
                for date_index, session_date in enumerate(dates):
                    base = 100 + ticker_index * 10 + date_index
                    writer.writerow(
                        {
                            "Date": session_date,
                            "Open": base,
                            "High": base + 2,
                            "Low": base - 2,
                            "Close": base + 1,
                            "Volume": 1_000_000 + date_index,
                        }
                    )
            paths[ticker] = path
        return paths

    def _legacy_fixture(
        self, root: Path, paths: dict[str, Path]
    ) -> tuple[object, list[dict]]:
        source_rows = {
            ticker: load_ohlc_rows(path, ticker=ticker)
            for ticker, path in paths.items()
        }
        source_hashes = {ticker: file_sha256(path) for ticker, path in paths.items()}
        records = prepare_v1_update(
            [],
            completed_dates=[CALENDAR_START],
            tickers=TICKERS,
            source_rows=source_rows,
            source_snapshot_sha256=source_hashes,
            prospective_start_date=PROSPECTIVE_START,
            recorded_at_utc=datetime.fromisoformat("2026-10-01T01:00:00+00:00"),
            bootstrap=True,
        )
        ledger_path = root / "legacy-v1.jsonl"
        ledger_path.write_text(
            "".join(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )
        evidence = load_legacy_v1_evidence(
            ledger_path,
            tickers=TICKERS,
            prospective_start_date=PROSPECTIVE_START,
        )
        events = import_v1_legacy_records(
            evidence,
            tickers=TICKERS,
            prospective_start_date=PROSPECTIVE_START,
            imported_at_utc=datetime.fromisoformat("2026-10-01T02:00:00+00:00"),
        )
        return evidence, events

    def test_caller_cannot_omit_an_intermediate_common_completed_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._write_sources(
                root, [CALENDAR_START, "2026-10-01", "2026-10-02"]
            )
            evidence, events = self._legacy_fixture(root, paths)
            snapshot = capture_source_snapshot(
                paths,
                tickers=TICKERS,
                start_date=CALENDAR_START,
                observed_at_utc=datetime.fromisoformat("2026-10-03T21:00:00+00:00"),
            )

            omitted = replace(
                snapshot,
                completed_dates=(CALENDAR_START, "2026-10-02"),
            )
            with self.assertRaisesRegex(
                NdxObservedSessionCalendarV2Error,
                "captured common completed dates changed",
            ):
                prepare_reviewed_update(
                    events,
                    snapshot=omitted,
                    tickers=TICKERS,
                    calendar_start_date=CALENDAR_START,
                    prospective_start_date=PROSPECTIVE_START,
                    legacy_v1_evidence=evidence,
                )

            shifted_boundary = capture_source_snapshot(
                paths,
                tickers=TICKERS,
                start_date="2026-10-02",
                observed_at_utc=datetime.fromisoformat("2026-10-03T21:00:00+00:00"),
            )
            with self.assertRaisesRegex(
                NdxObservedSessionCalendarV2Error,
                "captured source start boundary changed",
            ):
                prepare_reviewed_update(
                    events,
                    snapshot=shifted_boundary,
                    tickers=TICKERS,
                    calendar_start_date=CALENDAR_START,
                    prospective_start_date=PROSPECTIVE_START,
                    legacy_v1_evidence=evidence,
                )

    def test_caller_cannot_pair_rows_with_unrelated_snapshot_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._write_sources(root, [CALENDAR_START, "2026-10-01"])
            evidence, events = self._legacy_fixture(root, paths)
            snapshot = capture_source_snapshot(
                paths,
                tickers=TICKERS,
                start_date=CALENDAR_START,
                observed_at_utc=datetime.fromisoformat("2026-10-02T21:00:00+00:00"),
            )
            forged = replace(
                snapshot,
                source_sha256={"QQQ": "f" * 64, "SPY": "e" * 64},
            )
            with self.assertRaisesRegex(
                NdxObservedSessionCalendarV2Error,
                "captured source snapshot hash changed",
            ):
                prepare_reviewed_update(
                    events,
                    snapshot=forged,
                    tickers=TICKERS,
                    calendar_start_date=CALENDAR_START,
                    prospective_start_date=PROSPECTIVE_START,
                    legacy_v1_evidence=evidence,
                )

    def test_legacy_snapshot_metadata_must_match_canonical_v1_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._write_sources(root, [CALENDAR_START])
            evidence, events = self._legacy_fixture(root, paths)
            tampered = json.loads(json.dumps(events))
            tampered[0]["source_snapshot_sha256"] = {
                "QQQ": "1" * 64,
                "SPY": "2" * 64,
            }
            without_hash = dict(tampered[0])
            without_hash.pop("event_sha256")
            tampered[0]["event_sha256"] = canonical_sha256(without_hash)

            with self.assertRaisesRegex(
                NdxObservedSessionCalendarV2Error,
                "legacy import differs from canonical v1",
            ):
                validate_event_ledger(
                    tampered,
                    tickers=TICKERS,
                    prospective_start_date=PROSPECTIVE_START,
                    legacy_v1_evidence=evidence,
                )


if __name__ == "__main__":
    unittest.main()

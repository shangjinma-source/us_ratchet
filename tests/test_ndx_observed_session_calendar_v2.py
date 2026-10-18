from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest.ndx_observed_session_calendar import (
    canonical_sha256, file_sha256, load_ohlc_rows,
    prepare_update as prepare_v1_update,
)
from backtest.ndx_observed_session_calendar_v2 import (
    LEGACY_EVIDENCE_MODE, NdxObservedSessionCalendarV2Error,
    SOURCE_REVISION_EVENT, build_migration_readiness,
    capture_source_snapshot, import_v1_legacy_records,
    load_legacy_v1_evidence, prepare_reviewed_update, projection_rows,
    validate_event_ledger, load_verified_decision_sessions_v2,
    verify_canonical_reviewed_calendar_v2, write_canonical_reviewed_calendar_v2,
)


TICKERS = ["QQQ", "SPY"]
PROSPECTIVE_START = "2026-10-01"


class NdxObservedSessionCalendarV2Tests(unittest.TestCase):
    def _write_source(self, path: Path, dates: list[str], *, offset: int = 0) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["Date", "Open", "High", "Low", "Close", "Volume"],
            )
            writer.writeheader()
            for index, session in enumerate(dates, start=1):
                base = 100 + offset + index
                writer.writerow({
                    "Date": session, "Open": base, "High": base + 2,
                    "Low": base - 2, "Close": base + 1,
                    "Volume": 1_000_000 + offset + index,
                })

    def _sources(self, root: Path, dates: list[str]):
        paths: dict[str, Path] = {}
        rows: dict[str, dict] = {}
        for offset, ticker in enumerate(TICKERS):
            path = root / f"{ticker}.csv"
            self._write_source(path, dates, offset=offset * 10)
            paths[ticker] = path
            rows[ticker] = load_ohlc_rows(path, ticker=ticker)
        hashes = {ticker: file_sha256(path) for ticker, path in paths.items()}
        return paths, rows, hashes

    def _v1_records(
        self, rows: dict, hashes: dict, dates: list[str], *, recorded_at: str,
    ) -> list[dict]:
        return prepare_v1_update(
            [], completed_dates=dates, tickers=TICKERS, source_rows=rows,
            source_snapshot_sha256=hashes, prospective_start_date=PROSPECTIVE_START,
            recorded_at_utc=datetime.fromisoformat(recorded_at), bootstrap=True,
        )

    def _legacy(self, root: Path, records: list[dict], *, imported_at: str):
        path = root / "v1_sessions.jsonl"
        path.write_text(
            "".join(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                for record in records
            ), encoding="utf-8", newline="\n",
        )
        evidence = load_legacy_v1_evidence(
            path, tickers=TICKERS, prospective_start_date=PROSPECTIVE_START,
        )
        events = import_v1_legacy_records(
            evidence, tickers=TICKERS, prospective_start_date=PROSPECTIVE_START,
            imported_at_utc=datetime.fromisoformat(imported_at),
        )
        return evidence, events

    def _snapshot(self, paths: dict[str, Path], *, start_date: str, observed_at: str):
        return capture_source_snapshot(
            paths, tickers=TICKERS, start_date=start_date,
            observed_at_utc=datetime.fromisoformat(observed_at),
        )

    def _rewrite(self, path: Path, session: str, **changes: str) -> None:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if row["Date"] == session:
                row.update(changes)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["Date", "Open", "High", "Low", "Close", "Volume"],
            )
            writer.writeheader()
            writer.writerows(rows)

    def test_legacy_import_never_invents_original_normalized_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, rows, hashes = self._sources(root, ["2026-09-30"])
            records = self._v1_records(
                rows, hashes, ["2026-09-30"], recorded_at="2026-10-01T01:00:00+00:00",
            )
            evidence, events = self._legacy(
                root, records, imported_at="2026-10-01T02:00:00+00:00",
            )
        observation = events[0]["source_observations"][0]
        self.assertEqual(observation["evidence_mode"], LEGACY_EVIDENCE_MODE)
        self.assertIsNone(observation["normalized_ohlc"])
        self.assertFalse(observation["price_replay_available"])
        tampered = json.loads(json.dumps(events))
        tampered[0]["source_observations"][0]["normalized_ohlc"] = rows["QQQ"]["2026-09-30"]["normalized"]
        unsigned = dict(tampered[0])
        unsigned.pop("event_sha256")
        tampered[0]["event_sha256"] = canonical_sha256(unsigned)
        with self.assertRaisesRegex(NdxObservedSessionCalendarV2Error, "legacy OHLC evidence was fabricated"):
            validate_event_ledger(
                tampered, tickers=TICKERS, prospective_start_date=PROSPECTIVE_START,
                legacy_v1_evidence=evidence,
            )

    def test_legacy_snapshot_metadata_is_strictly_bound_to_v1_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, rows, hashes = self._sources(root, ["2026-09-30"])
            records = self._v1_records(
                rows, hashes, ["2026-09-30"], recorded_at="2026-10-01T01:00:00+00:00",
            )
            evidence, events = self._legacy(root, records, imported_at="2026-10-01T02:00:00+00:00")
        tampered = json.loads(json.dumps(events))
        tampered[0]["source_snapshot_sha256"]["QQQ"] = "f" * 64
        unsigned = dict(tampered[0])
        unsigned.pop("event_sha256")
        tampered[0]["event_sha256"] = canonical_sha256(unsigned)
        with self.assertRaisesRegex(NdxObservedSessionCalendarV2Error, "legacy import differs"):
            validate_event_ledger(
                tampered, tickers=TICKERS, prospective_start_date=PROSPECTIVE_START,
                legacy_v1_evidence=evidence,
            )

    def test_snapshot_derives_common_dates_and_hashes_from_same_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, rows, hashes = self._sources(
                root, ["2026-09-30", "2026-10-01", "2026-10-02"],
            )
            records = self._v1_records(
                rows, hashes, ["2026-09-30"], recorded_at="2026-10-01T01:00:00+00:00",
            )
            evidence, events = self._legacy(root, records, imported_at="2026-10-01T02:00:00+00:00")
            snapshot = self._snapshot(
                paths, start_date="2026-09-30", observed_at="2026-10-03T21:00:00+00:00",
            )
            omitted = replace(snapshot, completed_dates=("2026-09-30", "2026-10-02"))
            with self.assertRaisesRegex(NdxObservedSessionCalendarV2Error, "common completed dates changed"):
                prepare_reviewed_update(
                    events, snapshot=omitted, tickers=TICKERS,
                    calendar_start_date="2026-09-30", prospective_start_date=PROSPECTIVE_START,
                    legacy_v1_evidence=evidence,
                )
            forged_hashes = dict(snapshot.source_sha256)
            forged_hashes["QQQ"] = "f" * 64
            with self.assertRaisesRegex(NdxObservedSessionCalendarV2Error, "snapshot hash changed"):
                prepare_reviewed_update(
                    events, snapshot=replace(snapshot, source_sha256=forged_hashes),
                    tickers=TICKERS, calendar_start_date="2026-09-30",
                    prospective_start_date=PROSPECTIVE_START, legacy_v1_evidence=evidence,
                )
            hidden_start = self._snapshot(
                paths, start_date="2026-10-02", observed_at="2026-10-03T21:00:00+00:00",
            )
            with self.assertRaisesRegex(NdxObservedSessionCalendarV2Error, "start boundary changed"):
                prepare_reviewed_update(
                    events, snapshot=hidden_start, tickers=TICKERS,
                    calendar_start_date="2026-09-30", prospective_start_date=PROSPECTIVE_START,
                    legacy_v1_evidence=evidence,
                )

    def test_vendor_revision_state_machine_never_rewrites_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, rows, hashes = self._sources(root, ["2026-09-30"])
            records = self._v1_records(
                rows, hashes, ["2026-09-30"], recorded_at="2026-10-01T01:00:00+00:00",
            )
            evidence, events = self._legacy(root, records, imported_at="2026-10-01T02:00:00+00:00")
            original = json.loads(json.dumps(events[0]))
            self._rewrite(paths["QQQ"], "2026-09-30", High="105", Close="104")
            revised_snapshot = self._snapshot(
                paths, start_date="2026-09-30", observed_at="2026-10-02T01:00:00+00:00",
            )
            away = prepare_reviewed_update(
                events, snapshot=revised_snapshot, tickers=TICKERS,
                calendar_start_date="2026-09-30", prospective_start_date=PROSPECTIVE_START,
                legacy_v1_evidence=evidence,
            )
            combined = [*events, *away]
            self.assertEqual(prepare_reviewed_update(
                combined, snapshot=revised_snapshot, tickers=TICKERS,
                calendar_start_date="2026-09-30", prospective_start_date=PROSPECTIVE_START,
                legacy_v1_evidence=evidence,
            ), [])
            self._write_source(paths["QQQ"], ["2026-09-30"])
            restored = prepare_reviewed_update(
                combined,
                snapshot=self._snapshot(
                    paths, start_date="2026-09-30", observed_at="2026-10-03T01:00:00+00:00",
                ),
                tickers=TICKERS, calendar_start_date="2026-09-30",
                prospective_start_date=PROSPECTIVE_START, legacy_v1_evidence=evidence,
            )
        self.assertEqual(events[0], original)
        self.assertEqual(away[0]["event_type"], SOURCE_REVISION_EVENT)
        self.assertEqual(away[0]["revision_kind"], "REVISED_AWAY_FROM_SEALED_HASH")
        self.assertEqual(restored[0]["revision_kind"], "RESTORED_TO_SEALED_HASH")
        self.assertEqual(len(projection_rows([*combined, *restored])), 1)

    def test_pre_policy_session_is_observed_but_not_decision_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, rows, hashes = self._sources(root, ["2026-09-07", "2026-09-08", "2026-10-01"])
            records = self._v1_records(
                rows, hashes, ["2026-09-07"], recorded_at="2026-09-08T01:00:00+00:00",
            )
            evidence, events = self._legacy(root, records, imported_at="2026-09-08T02:00:00+00:00")
            pre = prepare_reviewed_update(
                events,
                snapshot=self._snapshot(paths, start_date="2026-09-07", observed_at="2026-09-09T01:00:00+00:00"),
                tickers=TICKERS, calendar_start_date="2026-09-07",
                prospective_start_date=PROSPECTIVE_START, legacy_v1_evidence=evidence,
            )
            self.assertFalse(pre[-1]["decision_eligible"])
            eligible = prepare_reviewed_update(
                [*events, *pre],
                snapshot=self._snapshot(paths, start_date="2026-09-07", observed_at="2026-10-02T01:00:00+00:00"),
                tickers=TICKERS, calendar_start_date="2026-09-07",
                prospective_start_date=PROSPECTIVE_START, legacy_v1_evidence=evidence,
            )
        self.assertTrue(eligible[-1]["decision_eligible"])

    def test_missing_source_and_multiple_pending_sessions_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, rows, hashes = self._sources(root, ["2026-09-30", "2026-10-01", "2026-10-02"])
            records = self._v1_records(
                rows, hashes, ["2026-09-30"], recorded_at="2026-10-01T01:00:00+00:00",
            )
            evidence, events = self._legacy(root, records, imported_at="2026-10-01T02:00:00+00:00")
            with self.assertRaisesRegex(NdxObservedSessionCalendarV2Error, "multiple completed sessions"):
                prepare_reviewed_update(
                    events,
                    snapshot=self._snapshot(paths, start_date="2026-09-30", observed_at="2026-10-03T21:00:00+00:00"),
                    tickers=TICKERS, calendar_start_date="2026-09-30",
                    prospective_start_date=PROSPECTIVE_START, legacy_v1_evidence=evidence,
                )
            self._write_source(paths["SPY"], ["2026-10-01", "2026-10-02"], offset=10)
            with self.assertRaisesRegex(NdxObservedSessionCalendarV2Error, "session-date prefix changed"):
                prepare_reviewed_update(
                    events,
                    snapshot=self._snapshot(paths, start_date="2026-09-30", observed_at="2026-10-03T21:00:00+00:00"),
                    tickers=TICKERS, calendar_start_date="2026-09-30",
                    prospective_start_date=PROSPECTIVE_START, legacy_v1_evidence=evidence,
                )

    def test_readiness_reports_real_drift_but_never_unlocks_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, rows, hashes = self._sources(root, ["2026-09-30"])
            records = self._v1_records(
                rows, hashes, ["2026-09-30"], recorded_at="2026-10-01T01:00:00+00:00",
            )
            evidence, _ = self._legacy(root, records, imported_at="2026-10-01T02:00:00+00:00")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "manifest_type": "ndx_observed_us_session_calendar",
                "start_date": "2026-09-30", "prospective_start_date": PROSPECTIVE_START,
                "artifacts": {"append_only_ledger": {
                    "path": evidence.path.as_posix(), "sha256": evidence.sha256,
                    "rows": len(evidence.records),
                }},
            }), encoding="utf-8")
            self._rewrite(paths["QQQ"], "2026-09-30", High="105", Close="104")
            readiness = build_migration_readiness(
                v1_manifest_path=manifest, v1_ledger_path=evidence.path,
                current_snapshot=self._snapshot(
                    paths, start_date="2026-09-30", observed_at="2026-10-02T01:00:00+00:00",
                ),
                tickers=TICKERS, calendar_start_date="2026-09-30",
                prospective_start_date=PROSPECTIVE_START,
            )
        self.assertEqual(readiness["status"], "BLOCKED_REVIEWED_CALENDAR_V2_NOT_ACTIVATED")
        self.assertFalse(readiness["automation_registration_allowed"])
        self.assertFalse(readiness["legacy_normalized_ohlc_recoverable"])
        self.assertEqual(readiness["source_revision_count"], 1)

    def _canonical_repository(self, root: Path, dates: list[str]):
        (root / "backtest").mkdir(parents=True)
        (root / "scripts").mkdir(parents=True)
        (root / "backtest/ndx_observed_session_calendar_v2.py").write_text("engine-v2\n", encoding="utf-8")
        (root / "scripts/ndx_observed_session_calendar_v2.py").write_text("runner-v2\n", encoding="utf-8")
        cache = root / "data/cache"
        cache.mkdir(parents=True)
        paths, rows, hashes = self._sources(cache, dates)
        records = self._v1_records(
            rows, hashes, [dates[0]], recorded_at="2026-10-01T01:00:00+00:00",
        )
        v1_root = root / "data/cache/research/ndx_observed_us_session_calendar_v1"
        v1_root.mkdir(parents=True)
        ledger = v1_root / "sessions.jsonl"
        ledger.write_text(
            "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records),
            encoding="utf-8", newline="\n",
        )
        manifest = {
            "manifest_type": "ndx_observed_us_session_calendar",
            "start_date": dates[0], "prospective_start_date": PROSPECTIVE_START,
            "artifacts": {"append_only_ledger": {
                "path": ledger.resolve().as_posix(), "sha256": file_sha256(ledger),
                "rows": len(records),
            }},
        }
        (v1_root / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        return paths

    def test_canonical_writer_verifier_and_decision_loader_use_only_full_v2_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._canonical_repository(root, ["2026-09-30", "2026-10-01"])
            snapshot = self._snapshot(
                paths, start_date="2026-09-30", observed_at="2026-10-02T01:00:00+00:00",
            )
            written = write_canonical_reviewed_calendar_v2(
                repository_root=root, snapshot=snapshot,
                calendar_start_date="2026-09-30", prospective_start_date=PROSPECTIVE_START,
                initialize_reviewed_v1=True,
            )
            manifest_path = root / "data/cache/research/ndx_observed_us_session_calendar_v2/manifest.json"
            verified = verify_canonical_reviewed_calendar_v2(
                manifest_path, repository_root=root,
            )
            decisions = load_verified_decision_sessions_v2(
                manifest_path, repository_root=root,
            )
        self.assertEqual(written.manifest["session_count"], 2)
        self.assertEqual(verified.manifest["decision_eligible_session_count"], 1)
        self.assertEqual(decisions["session_date"].tolist(), ["2026-10-01"])
        self.assertTrue(decisions["source_price_replay_available"].all())

    def test_canonical_writer_requires_explicit_initialization_and_frozen_snapshot_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._canonical_repository(root, ["2026-09-30", "2026-10-01"])
            snapshot = self._snapshot(
                paths, start_date="2026-09-30", observed_at="2026-10-02T01:00:00+00:00",
            )
            with self.assertRaisesRegex(NdxObservedSessionCalendarV2Error, "explicit reviewed v1 initialization"):
                write_canonical_reviewed_calendar_v2(
                    repository_root=root, snapshot=snapshot,
                    calendar_start_date="2026-09-30", prospective_start_date=PROSPECTIVE_START,
                    initialize_reviewed_v1=False,
                )
            written = write_canonical_reviewed_calendar_v2(
                repository_root=root, snapshot=snapshot,
                calendar_start_date="2026-09-30", prospective_start_date=PROSPECTIVE_START,
                initialize_reviewed_v1=True,
            )
            snapshot_id = written.manifest["source_snapshots"][0]["snapshot_id"]
            frozen = (
                root / "data/cache/research/ndx_observed_us_session_calendar_v2"
                / "source_snapshots" / snapshot_id / "QQQ.csv"
            )
            frozen.write_text("Date,Open,High,Low,Close,Volume\n2026-10-01,1,2,1,2,1\n", encoding="utf-8")
            with self.assertRaisesRegex(NdxObservedSessionCalendarV2Error, "frozen source snapshot bytes changed"):
                verify_canonical_reviewed_calendar_v2(
                    written.manifest_path, repository_root=root,
                )

    def test_canonical_writer_resumes_each_commit_boundary_without_rewriting_prefix(self) -> None:
        fault_labels = (
            "AFTER_PENDING_RECEIPT",
            "AFTER_EVENT_LEDGER",
            "AFTER_SESSION_PROJECTION",
            "AFTER_CURRENT_MANIFEST",
        )
        for fault_label in fault_labels:
            with self.subTest(fault_label=fault_label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                paths = self._canonical_repository(root, ["2026-09-30", "2026-10-01"])
                initial_snapshot = self._snapshot(
                    paths, start_date="2026-09-30",
                    observed_at="2026-10-02T01:00:00+00:00",
                )
                initialized = write_canonical_reviewed_calendar_v2(
                    repository_root=root, snapshot=initial_snapshot,
                    calendar_start_date="2026-09-30",
                    prospective_start_date=PROSPECTIVE_START,
                    initialize_reviewed_v1=True,
                )
                ledger_path = initialized.manifest_path.parent / "events.jsonl"
                committed_prefix = ledger_path.read_bytes()
                for ticker, offset in (("QQQ", 0), ("SPY", 10)):
                    self._write_source(
                        paths[ticker], ["2026-09-30", "2026-10-01", "2026-10-02"],
                        offset=offset,
                    )
                update_snapshot = self._snapshot(
                    paths, start_date="2026-09-30",
                    observed_at="2026-10-03T01:00:00+00:00",
                )

                def fail_at_boundary(label: str) -> None:
                    if label == fault_label:
                        raise RuntimeError(f"simulated crash at {label}")

                with patch(
                    "backtest.ndx_observed_session_calendar_v2._fault_point",
                    side_effect=fail_at_boundary,
                ):
                    with self.assertRaisesRegex(RuntimeError, fault_label):
                        write_canonical_reviewed_calendar_v2(
                            repository_root=root, snapshot=update_snapshot,
                            calendar_start_date="2026-09-30",
                            prospective_start_date=PROSPECTIVE_START,
                            initialize_reviewed_v1=False,
                        )
                crashed_ledger = ledger_path.read_bytes()
                self.assertTrue(crashed_ledger.startswith(committed_prefix))

                recovered = write_canonical_reviewed_calendar_v2(
                    repository_root=root, snapshot=update_snapshot,
                    calendar_start_date="2026-09-30",
                    prospective_start_date=PROSPECTIVE_START,
                    initialize_reviewed_v1=False,
                )
                self.assertTrue(ledger_path.read_bytes().startswith(committed_prefix))
                self.assertEqual(recovered.manifest["session_count"], 3)
                self.assertEqual(
                    [row["session_date"] for row in recovered.session_projection],
                    ["2026-09-30", "2026-10-01", "2026-10-02"],
                )
                self.assertFalse((recovered.manifest_path.parent / "pending_transaction.json").exists())
                committed_receipt = (
                    recovered.manifest_path.parent / "committed_transactions"
                    / f"{recovered.manifest['commit_transaction_id']}.json"
                )
                self.assertTrue(committed_receipt.is_file())

    def test_canonical_verifier_rejects_resigned_committed_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._canonical_repository(root, ["2026-09-30", "2026-10-01"])
            snapshot = self._snapshot(
                paths, start_date="2026-09-30", observed_at="2026-10-02T01:00:00+00:00",
            )
            written = write_canonical_reviewed_calendar_v2(
                repository_root=root, snapshot=snapshot,
                calendar_start_date="2026-09-30", prospective_start_date=PROSPECTIVE_START,
                initialize_reviewed_v1=True,
            )
            receipt_path = (
                written.manifest_path.parent / "committed_transactions"
                / f"{written.manifest['commit_transaction_id']}.json"
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["old_event_count"] = 99
            unsigned = dict(receipt)
            unsigned.pop("receipt_sha256")
            receipt["receipt_sha256"] = canonical_sha256(unsigned)
            receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                NdxObservedSessionCalendarV2Error,
                "ledger proof changed|old event",
            ):
                verify_canonical_reviewed_calendar_v2(
                    written.manifest_path, repository_root=root,
                )


if __name__ == "__main__":
    unittest.main()

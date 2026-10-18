from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

import backtest.ndx_dynamic_shadow_candidate_calendar_v2 as calendar_v2
import backtest.ndx_observed_session_calendar_v2 as reviewed_calendar_v2
import scripts.ndx_dynamic_shadow_candidate_generator as generator_v1
import scripts.ndx_dynamic_shadow_candidate_generator_v2 as generator_v2
from backtest.ndx_dynamic_shadow_candidate_snapshot import (
    NdxDynamicShadowCandidateSnapshotError,
)
from data.versioning import file_sha256


DECISION_DATE = "2026-10-01"


def _sessions() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "session_date": DECISION_DATE,
            "open_timestamp_utc": "2026-10-01T13:30:00+00:00",
            "close_timestamp_utc": "2026-10-01T20:00:00+00:00",
            "is_first_observed_session_of_month": True,
            "origin": "PROSPECTIVE_OBSERVED_APPEND",
            "decision_eligible": True,
            "source_price_replay_available": True,
            "session_event_sha256": "a" * 64,
        }
    ])


class CandidateCalendarV2Tests(unittest.TestCase):
    def _root(self, directory: str) -> tuple[Path, Path, Path]:
        root = Path(directory).resolve()
        manifest = root / calendar_v2.CALENDAR_RELATIVE
        ledger = root / calendar_v2.EVENT_LEDGER_RELATIVE
        projection = root / calendar_v2.SESSION_PROJECTION_RELATIVE
        manifest.parent.mkdir(parents=True)
        event = {"event_sha256": "a" * 64}
        event_bytes = reviewed_calendar_v2._event_ledger_bytes([event])
        ledger.write_bytes(event_bytes)
        transaction_id = "d" * 64
        manifest_payload = {
            "schema_version": 1,
            "manifest_type": "ndx_observed_us_session_calendar_v2",
            "generated_at_utc": "2026-10-01T21:00:00+00:00",
            "status": "REVIEWED_CALENDAR_V2_RESEARCH_ONLY_NOT_ACTIVATED",
            "calendar_start_date": "2026-10-01",
            "prospective_start_date": "2026-10-01",
            "tickers": ["QQQ", "SPY"],
            "session_count": 1,
            "event_count": 1,
            "revision_event_count": 0,
            "decision_eligible_session_count": 1,
            "latest_session_date": DECISION_DATE,
            "latest_event_sha256": "a" * 64,
            "inputs": {},
            "legacy_boundary": {},
            "source_snapshots": [],
            "commit_transaction_id": transaction_id,
            "artifacts": {"event_ledger": {
                "rows": 1,
                "sha256": __import__("hashlib").sha256(event_bytes).hexdigest(),
                "latest_event_sha256": "a" * 64,
            }, "session_projection": {}},
            "boundaries": {},
            "protected_hashes_before": {},
            "protected_hashes_after": {},
        }
        manifest_payload["manifest_sha256"] = reviewed_calendar_v2._manifest_hash(
            manifest_payload
        )
        manifest.write_text(
            json.dumps(manifest_payload, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        receipt = manifest.parent / "committed_transactions" / f"{transaction_id}.json"
        receipt.parent.mkdir()
        receipt_payload = {
            "schema_version": 1,
            "manifest_type": "ndx_observed_session_calendar_v2_pending_transaction",
            "transaction_id": transaction_id,
            "created_at_utc": "2026-10-01T21:00:00+00:00",
            "old_ledger_size": 0,
            "old_ledger_sha256": __import__("hashlib").sha256(b"").hexdigest(),
            "old_event_count": 0,
            "old_event_head_sha256": None,
            "additions": [event],
            "planned_manifest": manifest_payload,
        }
        receipt_payload["receipt_sha256"] = reviewed_calendar_v2._transaction_receipt_hash(
            receipt_payload
        )
        receipt.write_text(
            json.dumps(receipt_payload, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        projection.write_text("session_date\n2026-10-01\n", encoding="utf-8", newline="\n")
        for relative in (
            calendar_v2.ENGINE_RELATIVE,
            calendar_v2.CALENDAR_SCRIPT_RELATIVE,
            calendar_v2.ADAPTER_RELATIVE,
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {relative.as_posix()}\n", encoding="utf-8", newline="\n")
        return root, manifest, ledger

    def _capture(self, root: Path, manifest: Path):
        with (
            patch.object(calendar_v2, "_public_calendar_verifier", return_value=object()),
            patch.object(calendar_v2, "_public_decision_sessions", return_value=_sessions()),
        ):
            return calendar_v2.capture_candidate_calendar_evidence_v2(
                manifest, decision_date=DECISION_DATE, repository_root=root,
            )

    def _verify(self, root: Path, evidence: Path, *, sessions: pd.DataFrame | None = None):
        with (
            patch.object(calendar_v2, "_public_calendar_verifier", return_value=object()),
            patch.object(
                calendar_v2, "_public_decision_sessions",
                return_value=_sessions() if sessions is None else sessions,
            ),
        ):
            return calendar_v2.verify_candidate_calendar_evidence_v2(
                evidence, repository_root=root,
            )

    def test_prefix_proof_survives_normal_later_append(self) -> None:
        with TemporaryDirectory() as directory:
            root, manifest, ledger = self._root(directory)
            sessions, _, _ = self._capture(root, manifest)
            self.assertEqual(sessions.iloc[-1]["session_date"], DECISION_DATE)
            evidence = calendar_v2.candidate_calendar_evidence_path(
                DECISION_DATE, repository_root=root,
            )
            with ledger.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({"event_sha256": "b" * 64}, sort_keys=True) + "\n")
            later = pd.concat([
                _sessions(),
                _sessions().assign(
                    session_date="2026-11-02",
                    open_timestamp_utc="2026-11-02T14:30:00+00:00",
                    close_timestamp_utc="2026-11-02T21:00:00+00:00",
                    session_event_sha256="b" * 64,
                ),
            ], ignore_index=True)
            verified = self._verify(root, evidence, sessions=later)
            self.assertEqual(len(verified), 1)

    def test_old_event_prefix_tampering_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root, manifest, ledger = self._root(directory)
            self._capture(root, manifest)
            ledger.write_text(
                json.dumps({"event_sha256": "c" * 64}, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n",
            )
            evidence = calendar_v2.candidate_calendar_evidence_path(
                DECISION_DATE, repository_root=root,
            )
            with self.assertRaisesRegex(Exception, "event prefix changed"):
                self._verify(root, evidence)

    def test_projection_and_source_path_masquerade_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root, manifest, _ = self._root(directory)
            self._capture(root, manifest)
            evidence = calendar_v2.candidate_calendar_evidence_path(
                DECISION_DATE, repository_root=root,
            )
            projection = evidence.parent / "decision_sessions_prefix.csv"
            projection.write_text(projection.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(Exception, "session prefix artifact changed"):
                self._verify(root, evidence)

            # Restore a valid bundle and then re-sign a malicious source path.
        with TemporaryDirectory() as directory:
            root, manifest, _ = self._root(directory)
            self._capture(root, manifest)
            evidence = calendar_v2.candidate_calendar_evidence_path(
                DECISION_DATE, repository_root=root,
            )
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            payload["source_code"]["calendar_engine"]["path"] = (root / "README.md").as_posix()
            payload["manifest_sha256"] = calendar_v2._canonical_sha256(payload)
            evidence.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(Exception, "source code binding changed"):
                self._verify(root, evidence)

    def test_resigned_bogus_capture_and_source_hashes_are_rejected(self) -> None:
        for field in ("calendar", "engine"):
            with self.subTest(field=field), TemporaryDirectory() as directory:
                root, manifest, _ = self._root(directory)
                self._capture(root, manifest)
                evidence = calendar_v2.candidate_calendar_evidence_path(
                    DECISION_DATE, repository_root=root,
                )
                payload = json.loads(evidence.read_text(encoding="utf-8"))
                if field == "calendar":
                    payload["calendar_manifest"]["sha256_at_capture"] = "e" * 64
                else:
                    payload["source_code"]["calendar_engine"]["sha256_at_capture"] = "f" * 64
                payload["manifest_sha256"] = calendar_v2._canonical_sha256(payload)
                evidence.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
                with self.assertRaises(Exception):
                    self._verify(root, evidence)

    def test_minimal_resigned_historical_receipt_and_manifest_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root, manifest, _ = self._root(directory)
            self._capture(root, manifest)
            evidence = calendar_v2.candidate_calendar_evidence_path(
                DECISION_DATE, repository_root=root,
            )
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            calendar_item = payload["calendar_manifest"]
            transaction_id = calendar_item["committed_transaction_id"]
            frozen_manifest = evidence.parent / calendar_item["frozen_filename"]
            frozen_receipt = evidence.parent / calendar_item["committed_receipt_filename"]
            canonical_receipt = Path(calendar_item["committed_receipt_canonical_path"])
            forged_manifest = {
                "commit_transaction_id": transaction_id,
                "artifacts": {"event_ledger": {
                    "rows": payload["event_ledger_prefix"]["prefix_rows"],
                    "sha256": payload["event_ledger_prefix"]["prefix_bytes_sha256"],
                    "latest_event_sha256": payload["event_ledger_prefix"]["terminal_event_sha256"],
                }},
                "forged_unknown_policy": True,
            }
            forged_receipt = {
                "transaction_id": transaction_id,
                "planned_manifest": forged_manifest,
            }
            frozen_manifest.write_text(json.dumps(forged_manifest) + "\n", encoding="utf-8")
            receipt_text = json.dumps(forged_receipt) + "\n"
            frozen_receipt.write_text(receipt_text, encoding="utf-8")
            canonical_receipt.write_text(receipt_text, encoding="utf-8")
            payload["calendar_manifest"]["sha256_at_capture"] = file_sha256(frozen_manifest)
            payload["calendar_manifest"]["committed_receipt_sha256"] = file_sha256(frozen_receipt)
            payload["manifest_sha256"] = calendar_v2._canonical_sha256(payload)
            evidence.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(Exception, "historical committed receipt is invalid"):
                self._verify(root, evidence)

    def test_later_decision_session_prevents_late_seal(self) -> None:
        later = pd.concat([
            _sessions(),
            _sessions().assign(
                session_date="2026-11-02",
                open_timestamp_utc="2026-11-02T14:30:00+00:00",
                close_timestamp_utc="2026-11-02T21:00:00+00:00",
                session_event_sha256="b" * 64,
            ),
        ], ignore_index=True)
        with self.assertRaisesRegex(Exception, "later decision-eligible sessions"):
            calendar_v2._strict_decision_sessions(later, DECISION_DATE)

    def test_interrupted_build_leaves_no_final_partial_and_retry_succeeds(self) -> None:
        with TemporaryDirectory() as directory:
            root, manifest, _ = self._root(directory)
            original = calendar_v2._atomic_text

            def fail_manifest(path: Path, content: str) -> None:
                if path.name == "manifest.json" and path.parent.name.startswith(f".{DECISION_DATE}."):
                    raise OSError("injected before atomic directory publish")
                original(path, content)

            with (
                patch.object(calendar_v2, "_public_calendar_verifier", return_value=object()),
                patch.object(calendar_v2, "_public_decision_sessions", return_value=_sessions()),
                patch.object(calendar_v2, "_atomic_text", side_effect=fail_manifest),
                self.assertRaises(OSError),
            ):
                calendar_v2.capture_candidate_calendar_evidence_v2(
                    manifest, decision_date=DECISION_DATE, repository_root=root,
                )
            evidence = calendar_v2.candidate_calendar_evidence_path(
                DECISION_DATE, repository_root=root,
            )
            self.assertFalse(evidence.parent.exists())
            sessions, _, _ = self._capture(root, manifest)
            self.assertEqual(len(sessions), 1)


class CandidateGeneratorV2AdapterTests(unittest.TestCase):
    def test_patch_uses_v2_calendar_and_restores_v1_globals(self) -> None:
        old_calendar = generator_v1.DEFAULT_CALENDAR
        old_loader = generator_v1._load_calendar
        old_append = generator_v1._append_decision_seal
        old_file = generator_v1.__file__
        with patch.object(
            generator_v2,
            "capture_candidate_calendar_evidence_v2",
            return_value=(_sessions(), {"x": "a" * 64}, {"x": "C:/x"}),
        ):
            with generator_v2._patched_v1_calendar(DECISION_DATE):
                self.assertEqual(generator_v1.DEFAULT_CALENDAR, generator_v2.CALENDAR_V2)
                self.assertEqual(Path(generator_v1.__file__).resolve(), generator_v2.WRAPPER_PATH)
                sessions, versions, paths = generator_v1._load_calendar(generator_v2.CALENDAR_V2)
                self.assertTrue(sessions["completed"].all())
                self.assertEqual(versions["x"], "a" * 64)
                self.assertEqual(paths["x"], "C:/x")
        self.assertEqual(generator_v1.DEFAULT_CALENDAR, old_calendar)
        self.assertIs(generator_v1._load_calendar, old_loader)
        self.assertIs(generator_v1._append_decision_seal, old_append)
        self.assertEqual(generator_v1.__file__, old_file)

    def test_v2_provenance_failure_happens_before_decision_seal_append(self) -> None:
        old_append = generator_v1._append_decision_seal
        with (
            patch.object(generator_v2, "_require_v2_snapshot_provenance", side_effect=ValueError("bad v2")),
            patch.object(generator_v1, "_append_decision_seal") as append,
        ):
            with generator_v2._patched_v1_calendar(DECISION_DATE):
                with self.assertRaisesRegex(ValueError, "bad v2"):
                    generator_v1._append_decision_seal(
                        Path("ledger"), Path("manifest"), {"decision_date": DECISION_DATE},
                    )
                append.assert_not_called()
        self.assertIs(generator_v1._append_decision_seal, old_append)

    def test_snapshot_provenance_rejects_v1_only_and_forged_evidence(self) -> None:
        manifest = {
            "decision_date": DECISION_DATE,
            "source_versions": {"generator_script_sha256": file_sha256(generator_v2.WRAPPER_PATH)},
            "source_paths": {"generator_script_sha256": generator_v2.WRAPPER_PATH.as_posix()},
        }
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateSnapshotError,
            "lacks complete calendar-v2 provenance",
        ):
            generator_v2._require_v2_snapshot_provenance(
                generator_v1.DEFAULT_ROOT / DECISION_DATE / "manifest.json", manifest,
            )


if __name__ == "__main__":
    unittest.main()

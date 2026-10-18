from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backtest.ndx_dynamic_shadow_selection_task_observation import (
    SelectionTaskObservationError,
    append_observation,
    build_observation_record,
    canonical_sha256,
    load_observation_ledger,
    verify_observation_ledger,
)


TASK_XML = """<?xml version="1.0"?><Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Settings><DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>true</StopIfGoingOnBatteries><UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine></Settings></Task>"""


def _snapshot(*, arguments: str = '-B "daily.py" --execute') -> dict:
    return {
        "state": "Ready",
        "enabled": True,
        "task_xml": TASK_XML,
        "action": {
            "execute": "D:/python/python.exe",
            "arguments": arguments,
            "working_directory": "E:/Git/us_ratchet",
        },
        "trigger": {
            "start_boundary": "2026-09-05T11:20:00+08:00",
            "days_of_week_bitmask": 124,
            "weeks_interval": 1,
            "timezone": "Asia/Shanghai",
        },
        "settings": {
            "start_when_available": True,
            "multiple_instances": "IGNORENEW",
            "restart_count": 3,
            "restart_interval": "PT10M",
            "execution_time_limit": "PT11H",
            "disallow_start_if_on_batteries": True,
            "stop_if_going_on_batteries": True,
            "use_unified_scheduling_engine": True,
        },
        "principal": {
            "user_id": "Administrator",
            "logon_type": "Interactive",
            "run_level": "Limited",
        },
    }


def _fixture(directory: str) -> tuple[Path, Path, Path]:
    root = Path(directory)
    registration = root / "selection_task_registration.json"
    activation = root / "activation.json"
    installer = root / "installer.ps1"
    snapshot = _snapshot()
    evidence = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_selection_task_registration",
        "task_name": "us_ratchet_ndx_dynamic_shadow_selection_daily",
        "immutable": True,
        "overwrite_allowed": False,
        "registration_record_sha256": "1" * 64,
        "task_snapshot": {
            "task_xml": TASK_XML,
            "task_xml_sha256": hashlib.sha256(TASK_XML.encode()).hexdigest(),
            "action": snapshot["action"],
            "trigger": snapshot["trigger"],
            "settings": {
                key: value
                for key, value in snapshot["settings"].items()
                if key not in {
                    "disallow_start_if_on_batteries",
                    "stop_if_going_on_batteries",
                    "use_unified_scheduling_engine",
                }
            },
            "principal": snapshot["principal"],
        },
    }
    registration.write_text(json.dumps(evidence), encoding="utf-8")
    activation.write_text(json.dumps({"manifest_sha256": "2" * 64}), encoding="utf-8")
    installer.write_text("# reviewed installer\n", encoding="utf-8")
    return registration, activation, installer


class SelectionTaskObservationTests(unittest.TestCase):
    def _record(
        self, registration: Path, activation: Path, installer: Path,
        *, sequence: int = 1, previous: str | None = None, snapshot: dict | None = None,
        observed_at_utc: str = "2026-09-05T00:00:00+00:00",
    ) -> dict:
        return build_observation_record(
            sequence=sequence,
            previous_record_sha256=previous,
            observed_at_utc=observed_at_utc,
            registration_evidence_path=registration,
            activation_manifest_path=activation,
            installer_path=installer,
            current_task_snapshot=snapshot or _snapshot(),
            installer_registration_verifier_passed=True,
        )

    def test_append_and_rebuild_two_record_chain(self) -> None:
        with TemporaryDirectory() as directory:
            registration, activation, installer = _fixture(directory)
            ledger = Path(directory) / "observations.jsonl"
            first = self._record(registration, activation, installer)
            append_observation(ledger, first)
            second = self._record(
                registration, activation, installer,
                sequence=2, previous=first["record_sha256"],
                observed_at_utc="2026-09-05T00:01:00+00:00",
            )
            append_observation(ledger, second)
            result = verify_observation_ledger(
                ledger,
                registration_evidence_path=registration,
                latest_current_task_snapshot=_snapshot(),
            )

        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["terminal_record_sha256"], second["record_sha256"])
        self.assertFalse(result["live_mutation_performed"])

    def test_unsigned_record_tamper_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            registration, activation, installer = _fixture(directory)
            ledger = Path(directory) / "observations.jsonl"
            record = self._record(registration, activation, installer)
            record["status"] = "DRIFT_DETECTED_FAIL_CLOSED"
            ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(SelectionTaskObservationError, "record hash mismatch"):
                load_observation_ledger(ledger)

    def test_resigned_false_match_and_drift_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            registration, activation, installer = _fixture(directory)
            ledger = Path(directory) / "observations.jsonl"
            record = self._record(registration, activation, installer)
            record["current_task"]["action"]["arguments"] = "-B malicious.py --execute"
            unsigned = dict(record)
            unsigned.pop("record_sha256")
            record["record_sha256"] = canonical_sha256(unsigned)
            ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(SelectionTaskObservationError, "drift diagnosis"):
                load_observation_ledger(ledger)

    def test_resigned_previous_hash_change_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            registration, activation, installer = _fixture(directory)
            ledger = Path(directory) / "observations.jsonl"
            first = self._record(registration, activation, installer)
            second = self._record(
                registration, activation, installer,
                sequence=2, previous="f" * 64,
            )
            for record in (first, second):
                ledger.write_text(
                    ledger.read_text(encoding="utf-8") + json.dumps(record) + "\n"
                    if ledger.exists() else json.dumps(record) + "\n",
                    encoding="utf-8",
                )
            with self.assertRaisesRegex(SelectionTaskObservationError, "hash chain"):
                load_observation_ledger(ledger)

    def test_registration_source_change_and_latest_task_drift_fail(self) -> None:
        with TemporaryDirectory() as directory:
            registration, activation, installer = _fixture(directory)
            ledger = Path(directory) / "observations.jsonl"
            append_observation(ledger, self._record(registration, activation, installer))
            with self.assertRaisesRegex(SelectionTaskObservationError, "latest task differs"):
                verify_observation_ledger(
                    ledger,
                    registration_evidence_path=registration,
                    latest_current_task_snapshot=_snapshot(arguments="-B malicious.py --execute"),
                )
            registration.write_text(registration.read_text() + "\n", encoding="utf-8")
            with self.assertRaisesRegex(SelectionTaskObservationError, "evidence binding"):
                verify_observation_ledger(ledger, registration_evidence_path=registration)

    def test_latest_activation_or_installer_source_change_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            registration, activation, installer = _fixture(directory)
            ledger = Path(directory) / "observations.jsonl"
            append_observation(ledger, self._record(registration, activation, installer))
            activation.write_text(json.dumps({"manifest_sha256": "3" * 64}), encoding="utf-8")
            with self.assertRaisesRegex(SelectionTaskObservationError, "activation manifest binding"):
                verify_observation_ledger(
                    ledger,
                    registration_evidence_path=registration,
                    activation_manifest_path=activation,
                    installer_path=installer,
                )
            activation.write_text(json.dumps({"manifest_sha256": "2" * 64}), encoding="utf-8")
            installer.write_text("# malicious installer\n", encoding="utf-8")
            with self.assertRaisesRegex(SelectionTaskObservationError, "installer binding"):
                verify_observation_ledger(
                    ledger,
                    registration_evidence_path=registration,
                    activation_manifest_path=activation,
                    installer_path=installer,
                )


if __name__ == "__main__":
    unittest.main()

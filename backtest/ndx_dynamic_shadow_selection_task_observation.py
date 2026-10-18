"""Append-only evidence for the registered dynamic-shadow selection task."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree


class SelectionTaskObservationError(ValueError):
    """Raised when registration or observation evidence is invalid."""


RECORD_KEYS = {
    "schema_version", "sequence", "observed_at_utc", "task_name", "status",
    "drift_fields", "registration_evidence", "activation_manifest", "installer",
    "baseline", "current_task", "installer_registration_verifier_passed",
    "live_mutation_performed", "task_settings_mutation_performed",
    "scheduler_registration_performed", "previous_record_sha256", "record_sha256",
}


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require(value: bool, message: str) -> None:
    if not value:
        raise SelectionTaskObservationError(message)


def _xml_bool(root: ElementTree.Element, name: str) -> bool:
    node = root.find(f".//{{*}}{name}")
    _require(
        node is not None and (node.text or "").lower() in {"true", "false"},
        f"task XML missing {name}",
    )
    return (node.text or "").lower() == "true"


def load_registration_evidence(path: str | Path) -> dict[str, Any]:
    evidence_path = Path(path).resolve()
    try:
        value = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SelectionTaskObservationError("registration evidence is missing/invalid") from exc
    _require(
        value.get("schema_version") == 1
        and value.get("manifest_type") == "ndx_dynamic_shadow_selection_task_registration"
        and value.get("immutable") is True
        and value.get("overwrite_allowed") is False,
        "registration evidence boundary changed",
    )
    snapshot = value.get("task_snapshot") or {}
    xml = str(snapshot.get("task_xml") or "")
    _require(
        hashlib.sha256(xml.encode("utf-8")).hexdigest()
        == snapshot.get("task_xml_sha256"),
        "registration task XML hash changed",
    )
    _require(
        isinstance(value.get("registration_record_sha256"), str)
        and len(value["registration_record_sha256"]) == 64,
        "registration record hash is missing",
    )
    return value


def _baseline(evidence: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = dict(evidence["task_snapshot"])
    try:
        xml_root = ElementTree.fromstring(str(snapshot["task_xml"]))
    except ElementTree.ParseError as exc:
        raise SelectionTaskObservationError("registration task XML is invalid") from exc
    settings = dict(snapshot.get("settings") or {})
    settings.update({
        "disallow_start_if_on_batteries": _xml_bool(xml_root, "DisallowStartIfOnBatteries"),
        "stop_if_going_on_batteries": _xml_bool(xml_root, "StopIfGoingOnBatteries"),
        "use_unified_scheduling_engine": _xml_bool(xml_root, "UseUnifiedSchedulingEngine"),
    })
    return {
        "task_xml_sha256": snapshot["task_xml_sha256"],
        "action": snapshot["action"],
        "trigger": snapshot["trigger"],
        "settings": settings,
        "principal": snapshot["principal"],
    }


def _normalized_current(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    required = {"task_xml", "action", "trigger", "settings", "principal", "state", "enabled"}
    _require(set(snapshot) == required, "current task snapshot schema changed")
    xml = str(snapshot["task_xml"])
    return {
        "state": str(snapshot["state"]),
        "enabled": bool(snapshot["enabled"]),
        "task_xml_sha256": hashlib.sha256(xml.encode("utf-8")).hexdigest(),
        "action": dict(snapshot["action"]),
        "trigger": dict(snapshot["trigger"]),
        "settings": dict(snapshot["settings"]),
        "principal": dict(snapshot["principal"]),
    }


def _drift_fields(baseline: Mapping[str, Any], current: Mapping[str, Any]) -> list[str]:
    drift: list[str] = []
    if current.get("enabled") is not True:
        drift.append("enabled")
    for name in ("task_xml_sha256", "action", "trigger", "settings", "principal"):
        if current.get(name) != baseline.get(name):
            drift.append(name)
    return drift


def build_observation_record(
    *, sequence: int, previous_record_sha256: str | None, observed_at_utc: str,
    registration_evidence_path: str | Path, activation_manifest_path: str | Path,
    installer_path: str | Path, current_task_snapshot: Mapping[str, Any],
    installer_registration_verifier_passed: bool,
) -> dict[str, Any]:
    evidence_path = Path(registration_evidence_path).resolve()
    activation_path = Path(activation_manifest_path).resolve()
    installer = Path(installer_path).resolve()
    evidence = load_registration_evidence(evidence_path)
    activation = json.loads(activation_path.read_text(encoding="utf-8"))
    baseline = _baseline(evidence)
    current = _normalized_current(current_task_snapshot)
    drift = _drift_fields(baseline, current)
    if not installer_registration_verifier_passed:
        drift.append("installer_verifier")
    record: dict[str, Any] = {
        "schema_version": 1,
        "sequence": int(sequence),
        "observed_at_utc": datetime.fromisoformat(observed_at_utc.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(),
        "task_name": str(evidence["task_name"]),
        "status": "MATCH_REGISTERED_BASELINE" if not drift else "DRIFT_DETECTED_FAIL_CLOSED",
        "drift_fields": sorted(set(drift)),
        "registration_evidence": {
            "path": evidence_path.as_posix(),
            "file_sha256": file_sha256(evidence_path),
            "registration_record_sha256": evidence["registration_record_sha256"],
        },
        "activation_manifest": {
            "path": activation_path.as_posix(),
            "file_sha256": file_sha256(activation_path),
            "declared_manifest_sha256": activation.get("manifest_sha256"),
        },
        "installer": {"path": installer.as_posix(), "file_sha256": file_sha256(installer)},
        "baseline": baseline,
        "current_task": current,
        "installer_registration_verifier_passed": bool(installer_registration_verifier_passed),
        "live_mutation_performed": False,
        "task_settings_mutation_performed": False,
        "scheduler_registration_performed": False,
        "previous_record_sha256": previous_record_sha256,
    }
    record["record_sha256"] = canonical_sha256(record)
    return record


def load_observation_ledger(path: str | Path) -> list[dict[str, Any]]:
    ledger = Path(path)
    if not ledger.is_file():
        return []
    records: list[dict[str, Any]] = []
    previous: str | None = None
    previous_observed: datetime | None = None
    for index, raw in enumerate(ledger.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SelectionTaskObservationError("observation ledger contains invalid JSON") from exc
        _require(set(record) == RECORD_KEYS, "observation record schema changed")
        declared = str(record.pop("record_sha256"))
        _require(canonical_sha256(record) == declared, "observation record hash mismatch")
        record["record_sha256"] = declared
        _require(record["sequence"] == index, "observation sequence is not contiguous")
        _require(record["previous_record_sha256"] == previous, "observation hash chain changed")
        observed = datetime.fromisoformat(str(record["observed_at_utc"]).replace("Z", "+00:00"))
        _require(
            observed.tzinfo is not None
            and (previous_observed is None or observed > previous_observed),
            "observation timestamps are not strictly increasing",
        )
        expected_drift = _drift_fields(record["baseline"], record["current_task"])
        if not record["installer_registration_verifier_passed"]:
            expected_drift.append("installer_verifier")
        expected_drift = sorted(set(expected_drift))
        _require(record["drift_fields"] == expected_drift, "observation drift diagnosis changed")
        _require(
            record["status"] == (
                "MATCH_REGISTERED_BASELINE" if not expected_drift else "DRIFT_DETECTED_FAIL_CLOSED"
            ),
            "observation status does not match rebuilt drift",
        )
        _require(
            record["live_mutation_performed"] is False
            and record["task_settings_mutation_performed"] is False
            and record["scheduler_registration_performed"] is False,
            "observation exceeded read-only authority",
        )
        records.append(record)
        previous = declared
        previous_observed = observed
    return records


def append_observation(path: str | Path, record: Mapping[str, Any]) -> None:
    ledger = Path(path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    current = load_observation_ledger(ledger)
    expected_sequence = len(current) + 1
    expected_previous = current[-1]["record_sha256"] if current else None
    _require(record.get("sequence") == expected_sequence, "append observation sequence changed")
    _require(record.get("previous_record_sha256") == expected_previous, "append observation head changed")
    line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with ledger.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def verify_observation_ledger(
    path: str | Path, *, registration_evidence_path: str | Path,
    activation_manifest_path: str | Path | None = None,
    installer_path: str | Path | None = None,
    latest_current_task_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    records = load_observation_ledger(path)
    _require(bool(records), "observation ledger is empty")
    evidence_path = Path(registration_evidence_path).resolve()
    evidence_hash = file_sha256(evidence_path)
    _require(
        all(
            Path(item["registration_evidence"]["path"]).resolve() == evidence_path
            and item["registration_evidence"]["file_sha256"] == evidence_hash
            and item["registration_evidence"]["registration_record_sha256"]
            == load_registration_evidence(evidence_path)["registration_record_sha256"]
            for item in records
        ),
        "observation registration evidence binding changed",
    )
    if activation_manifest_path is not None:
        activation_path = Path(activation_manifest_path).resolve()
        activation = json.loads(activation_path.read_text(encoding="utf-8"))
        _require(
            all(Path(item["activation_manifest"]["path"]).resolve() == activation_path for item in records)
            and records[-1]["activation_manifest"]["file_sha256"] == file_sha256(activation_path)
            and records[-1]["activation_manifest"]["declared_manifest_sha256"]
            == activation.get("manifest_sha256"),
            "latest activation manifest binding changed",
        )
    if installer_path is not None:
        canonical_installer = Path(installer_path).resolve()
        _require(
            all(Path(item["installer"]["path"]).resolve() == canonical_installer for item in records)
            and records[-1]["installer"]["file_sha256"] == file_sha256(canonical_installer),
            "latest installer binding changed",
        )
    if latest_current_task_snapshot is not None:
        latest_current = _normalized_current(latest_current_task_snapshot)
        _require(records[-1]["current_task"] == latest_current, "latest task differs from observation head")
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_selection_task_observation_verification",
        "status": "VERIFIED" if records[-1]["status"] == "MATCH_REGISTERED_BASELINE" else "DRIFT_DETECTED_FAIL_CLOSED",
        "record_count": len(records),
        "terminal_record_sha256": records[-1]["record_sha256"],
        "latest_observed_at_utc": records[-1]["observed_at_utc"],
        "latest_drift_fields": records[-1]["drift_fields"],
        "live_mutation_performed": False,
    }


__all__ = [
    "SelectionTaskObservationError", "append_observation", "build_observation_record",
    "canonical_sha256", "load_observation_ledger", "load_registration_evidence",
    "verify_observation_ledger",
]

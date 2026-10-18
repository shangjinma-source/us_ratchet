"""Public verifier integration: real snapshot, calendar proof, and seal ledger."""
from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

import test_ndx_dynamic_shadow_candidate_generator_v3 as fixture_v3
import test_ndx_observed_session_calendar_v2 as fixture_calendar
import backtest.ndx_dynamic_shadow_candidate_calendar_v2 as calendar
from backtest.ndx_dynamic_shadow_candidate_generator_v3 import (
    OUTPUT_ROOT_RELATIVE, capture_nominal_liquidity_inputs_v3,
    NdxDynamicShadowCandidateGeneratorV3Error,
)
from backtest.ndx_dynamic_shadow_candidate_snapshot import (
    build_fresh_candidate_input_snapshot, write_snapshot_bundle,
)
from backtest.ndx_observed_session_calendar_v2 import write_canonical_reviewed_calendar_v2
from data.versioning import file_sha256
import scripts.ndx_dynamic_shadow_candidate_generator as v1
import scripts.ndx_dynamic_shadow_candidate_generator_v2 as v2
import scripts.ndx_dynamic_shadow_candidate_generator_v3 as v3


def _complete_fixture(root, *, additional_source_versions=None, additional_source_paths=None):
    helper = fixture_calendar.NdxObservedSessionCalendarV2Tests()
    calendar_sources = helper._canonical_repository(root, ["2026-09-30", "2026-10-01"])
    manifest_path, partial = fixture_v3._fixture(root)
    (root / calendar.ADAPTER_RELATIVE).write_text("fixture calendar adapter\n", encoding="utf-8")
    observed = helper._snapshot(
        calendar_sources, start_date="2026-09-30", observed_at="2026-10-02T01:00:00+00:00",
    )
    write_canonical_reviewed_calendar_v2(
        repository_root=root, snapshot=observed, calendar_start_date="2026-09-30",
        prospective_start_date=fixture_calendar.PROSPECTIVE_START, initialize_reviewed_v1=True,
    )
    _, versions, paths = calendar.capture_candidate_calendar_evidence_v2(
        root / calendar.CALENDAR_RELATIVE, decision_date="2026-10-01", repository_root=root,
    )
    partial["source_versions"].update(versions)
    partial["source_paths"].update(paths)
    # Explicit caller-provided provenance for integration fixtures only; the
    # default archive fixture does not claim to validate an original8 definition.
    extra_versions = additional_source_versions or {}
    extra_paths = additional_source_paths or {}
    if set(extra_versions) != set(extra_paths) or set(extra_versions) & set(partial["source_versions"]):
        raise ValueError("invalid additional fixture source registry")
    partial["source_versions"].update(extra_versions)
    partial["source_paths"].update(extra_paths)
    generator_path = root / "scripts/ndx_dynamic_shadow_candidate_generator_v2.py"
    partial["source_versions"]["generator_script_sha256"] = file_sha256(generator_path)
    partial["source_paths"]["generator_script_sha256"] = generator_path.resolve().as_posix()
    dates = pd.bdate_range(end="2026-10-01", periods=300)
    nominal = pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"), "Open": 100.0,
        "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1_000_000.0,
    })
    nominal_path = Path(partial["source_paths"]["nominal_price_NEW_sha256"])
    nominal_path.write_text(nominal.to_csv(index=False, lineterminator="\n"), encoding="utf-8")
    sidecar_path = Path(partial["source_paths"]["nominal_price_NEW_manifest_sha256"])
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar.update(data_start=dates[0].date().isoformat(), rows=300, content_sha256=file_sha256(nominal_path))
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    for key, source in (("nominal_price_NEW_sha256", nominal_path), ("nominal_price_NEW_manifest_sha256", sidecar_path)):
        partial["source_versions"][key] = file_sha256(source)
    eligible = pd.read_csv(manifest_path.parent / "eligible_securities.csv")
    _, _, liquidity = capture_nominal_liquidity_inputs_v3(
        eligible, partial["source_versions"], partial["source_paths"],
        decision_date="2026-10-01", snapshot_directory=manifest_path.parent,
    )
    partial["membership_evidence"]["candidate_v3_nominal_liquidity_capture"] = liquidity
    fixture_v3._attach_source_archive(manifest_path, partial)
    controls = [f"CONTROL{index}" for index in range(8)]
    nominal_frames = {ticker: nominal.copy() for ticker in ["NEW", *controls]}
    adjusted_frames = {ticker: frame[["Date", "Close"]].copy() for ticker, frame in nominal_frames.items()}
    target = pd.DataFrame({"Date": dates, "Close": 1.0})
    snapshot = build_fresh_candidate_input_snapshot(
        eligible, adjusted_frames, nominal_frames, target,
        decision_date="2026-10-01",
        decision_close_timestamp_utc=partial["decision_close_timestamp_utc"],
        seal_timestamp_utc=partial["seal_timestamp_utc"],
        conservative_seal_deadline_utc=partial["conservative_seal_deadline_utc"],
        source_versions=partial["source_versions"], source_paths=partial["source_paths"],
        frozen_original8_tickers=controls,
    )
    snapshot["membership_evidence"] = partial["membership_evidence"]
    # The small identity fixture writes a placeholder, not a published bundle.
    for filename in ("manifest.json", "eligible_securities.csv", "liquidity_exclusions.csv"):
        (manifest_path.parent / filename).unlink()
    manifest = write_snapshot_bundle(manifest_path.parent, snapshot)
    output = root / OUTPUT_ROOT_RELATIVE
    ledger = output / "decision_seals.jsonl"
    v1._append_decision_seal(ledger, manifest_path, manifest, expected_root=output)
    return manifest_path, manifest


def _temporary_public_paths(stack, root):
    output = root / OUTPUT_ROOT_RELATIVE
    for module in (v1, v2, v3):
        stack.enter_context(patch.object(module, "ROOT", root))
    stack.enter_context(patch.object(v1, "DEFAULT_ROOT", output))
    stack.enter_context(patch.object(v1, "SEAL_LEDGER", output / "decision_seals.jsonl"))
    stack.enter_context(patch.object(v2, "CALENDAR_V2", root / calendar.CALENDAR_RELATIVE))
    stack.enter_context(patch.object(v2, "WRAPPER_PATH", root / "scripts/ndx_dynamic_shadow_candidate_generator_v2.py"))
    # Change only the definition-time bound path; the actual ledger validator runs.
    defaults = dict(v1._load_and_validate_seal_ledger.__kwdefaults__)
    defaults["expected_root"] = output
    stack.enter_context(patch.object(v1._load_and_validate_seal_ledger, "__kwdefaults__", defaults))


class CandidateV3PublicVerifyTests(unittest.TestCase):
    def test_fixture_path_defaults_are_restored(self):
        original = v1._load_and_validate_seal_ledger.__kwdefaults__
        original_values = dict(original)
        original_root = v1.DEFAULT_ROOT
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory).resolve()
            _temporary_public_paths(stack, root)
            self.assertEqual(v1._load_and_validate_seal_ledger.__kwdefaults__["expected_root"], root / OUTPUT_ROOT_RELATIVE)
        self.assertIs(v1._load_and_validate_seal_ledger.__kwdefaults__, original)
        self.assertEqual(v1._load_and_validate_seal_ledger.__kwdefaults__, original_values)
        self.assertIs(v1.DEFAULT_ROOT, original_root)

    def test_public_verify_survives_canonical_drift_without_restore(self):
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory).resolve()
            manifest_path, manifest = _complete_fixture(root)
            _temporary_public_paths(stack, root)
            self.assertEqual(v3.verify(manifest_path)["decision_date"], "2026-10-01")
            changed = [Path(manifest["source_paths"][key]) for key in (
                "taxonomy_records_sha256", "security_lifecycle_sha256", "nominal_price_NEW_sha256",
            )]
            for source in changed:
                source.write_bytes(b"later canonical revision\n")
            removed = Path(manifest["source_paths"]["membership_history_sha256"])
            removed.unlink()
            self.assertEqual(v3.verify(manifest_path)["decision_date"], "2026-10-01")
            self.assertTrue(all(source.read_bytes() == b"later canonical revision\n" for source in changed))
            self.assertFalse(removed.exists())

    def test_public_verify_rejects_archive_tamper(self):
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory).resolve()
            manifest_path, manifest = _complete_fixture(root)
            _temporary_public_paths(stack, root)
            v3.verify(manifest_path)
            archive_path = Path(manifest["membership_evidence"]["candidate_v3_source_archive"]["path"])
            archive = json.loads(archive_path.read_text(encoding="utf-8"))
            source = archive_path.parent / archive["source_descriptors"][0]["archive_filename"]
            source.write_bytes(b"tampered\n")
            with self.assertRaisesRegex(NdxDynamicShadowCandidateGeneratorV3Error, "source archive bytes changed"):
                v3.verify(manifest_path)


if __name__ == "__main__":
    unittest.main()

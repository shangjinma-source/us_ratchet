"""Verify the new writer still accepts true legacy parents through V5 captures."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_observation_writer_20261009_v2 as writer
from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as capture
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as capture_reader
from scripts import ndx_prospective_observation_writer_v3_20261009 as original
from backtest import ndx_observation_runtime_registration_research_v1 as registration
from ndx_v5_physical_parent_fixture import reference
import test_ndx_registered_forward_capture_runtime_20261009_v1_independent_review as legacy
import test_ndx_registered_forward_capture_runtime_20261009_v2_independent_review as physical


class TrueLegacyParentReview(unittest.TestCase):
    def test_v3_and_v4_keep_true_parent_schema_sequence_and_full_sources(self):
        for mode, session, sequence in (("v3", "2026-10-08", 70), ("v4", "2026-10-09", 71)):
            with self.subTest(mode=mode), TemporaryDirectory(prefix="SYNTHETIC_ROOT_WRITER_LEGACY_") as folder:
                root = Path(folder); research = root / "research"; research.mkdir()
                parent = deepcopy(original.PARENT_BOUND) if mode == "v3" else legacy.compact_parent(root, research)
                current = legacy.current_files(root, parent, session)
                capargs, _ = physical.registered(root, research, parent, "legacy_capture")
                with patch.multiple(capture, RESEARCH=research, CURRENT=current), patch.object(capture, "now", side_effect=["2026-10-09T20:03:00+00:00", "2026-10-09T20:03:01+00:00"]):
                    saved = capture.run(**capargs)
                with patch.multiple(capture_reader, RESEARCH=research, CURRENT=current):
                    audit = capture_reader.readback(registration_path=capargs["registration_path"], registration_sha256=capargs["registration_sha256"], **saved, output_directory=str(research / "legacy_capture_audit"), execute=True)
                captures = dict(reference=saved["capture_reference"], publication_reference=saved["publication_reference"], readback_reference=audit, reader_reference=reference(capture_reader.SOURCE))
                value = dict(schema=registration.SCHEMA, runtime_reference=reference(writer.SOURCE), dependency_references={key: reference(path) for key, (path, _) in writer.DEPENDENCIES.items()}, parent=parent, capture=captures, output_directory=str(research / "legacy_attempt"), **registration.FLAGS)
                reg = root / "registration.json"; reg.write_bytes(writer.encode(value))
                for path in current.values(): path.write_bytes(b"changed after immutable capture")
                original_read = Path.read_bytes
                def deny_live(path):
                    self.assertNotIn(path, current.values())
                    return original_read(path)
                with patch.multiple(writer, RESEARCH=research, CURRENT=current), patch.object(writer, "now", return_value="2026-10-09T20:04:00+00:00"), patch.object(Path, "read_bytes", side_effect=deny_live, autospec=True):
                    receipt_ref = writer.run(registration_path=str(reg), registration_sha256=reference(reg)["sha256"], execute=True)
                receipt = writer.decode(Path(receipt_ref["path"]).read_bytes())
                payload = writer.decode(Path(receipt["payload_reference"]["path"]).read_bytes())
                actual_schema = writer.decode(Path(parent["reference"]["path"]).read_bytes())["history"]["schema"]
                self.assertEqual(payload["actual_parent_schema"], actual_schema)
                self.assertEqual((payload["session"], payload["sequence"]), (session, sequence))
                self.assertEqual(payload["first_actual_observed_session_of_month"], "2026-10-02")
                self.assertFalse(payload["month_first_actual_observation"])
                for ticker in ("QQQ", "SPY"):
                    self.assertEqual(payload["full_original_sources_preserved"][ticker]["sources"]["reference"], writer.decode(Path(captures["reference"]["path"]).read_bytes())["captured_artifacts"][ticker])


if __name__ == "__main__": unittest.main()

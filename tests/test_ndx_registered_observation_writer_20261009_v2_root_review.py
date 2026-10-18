"""Root review: the writer final guard covers the entire original ancestor graph."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_observation_writer_20261009_v2 as writer
from test_ndx_registered_observation_writer_20261009_v2 import physical_context


class WriterAncestorGuardReview(unittest.TestCase):
    def test_final_guard_pins_all_ancestor_starts_and_capture_namespace(self):
        with TemporaryDirectory(prefix="SYNTHETIC_ROOT_V5_WRITER_ANCESTORS_") as directory:
            context = physical_context(Path(directory))
            research, parent, capture, current, arguments = context
            with patch.multiple(writer, RESEARCH=research, CURRENT=current):
                loaded = writer.load_inputs(arguments["registration_path"], arguments["registration_sha256"])
                sources, final_guard = loaded[2], loaded[4]
                starts = [Path(name) for name in sources if Path(name).name == "started.json"]
                self.assertGreaterEqual(len(starts), 8)
                required = {Path(parent["reference"]["path"]).parent / "started.json",
                    Path(parent["readback_reference"]["path"]).parent / "started.json",
                    Path(capture["reference"]["path"]).parent / "started.json",
                    Path(capture["readback_reference"]["path"]).parent / "started.json"}
                self.assertTrue(required <= set(starts))
                expected_starts = set(research.rglob("started.json"))
                self.assertTrue(expected_starts <= set(starts), "Fixture ancestor START missing from source closure")
                final_guard()
                for target in starts:
                    with self.subTest(target=str(target)):
                        original = target.read_bytes()
                        try:
                            target.write_bytes(original + b"\n")
                            with self.assertRaises(ValueError): final_guard()
                        finally:
                            target.write_bytes(original)
                extra = Path(capture["reference"]["path"]).parent / "unexpected_side_directory"
                extra.mkdir()
                try:
                    with self.assertRaises(ValueError): final_guard()
                finally:
                    extra.rmdir()
                final_guard()
                self.assertFalse((research / "observation_v5_attempt").exists())


if __name__ == "__main__": unittest.main()

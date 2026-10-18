"""Independent regression for local registration refs lost from global guards."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import ndx_registered_compact_history_independent_readback_20261009_v2 as reader
from test_ndx_compact_reader_v2_optional_consumer_author_20261009 import host_files, pins
from ndx_registered_v5_parent_fixture_v2 import physical_registered_gap_parent


class LegacyRegistrationGuardRootReview(unittest.TestCase):
    def test_original_registration_files_exported_and_guarded(self):
        self.assertEqual(reader.LOADED_SHA, 'e6b9fb8aa8a63458eb44251b223db13e01713b032ca368dc27abc2c1b69763bd')
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_ROOT_legacy_registration_guard_') as directory:
            root = Path(directory)
            research = root / 'research'
            parent, context = physical_registered_gap_parent(root, research)
            args, _ = host_files(root)
            with patch.multiple(reader, RESEARCH=research, CURRENT=context['current'], **pins()):
                result = reader.verify_saved_parent_ancestry(parent_references=parent, **args)
            originals = [path.resolve() for path in root.rglob('*.json') if path.name in {
                'registered_gap_parent_registration.json', 'registered_gap_capture_registration.json'}]
            self.assertEqual({path.name for path in originals}, {
                'registered_gap_parent_registration.json', 'registered_gap_capture_registration.json'})
            self.assertGreaterEqual(len(originals), 2)
            result['final_guard']()
            for path in originals:
                with self.subTest(original=str(path)):
                    before = path.read_bytes()
                    self.assertEqual(result['sources'].get(str(path)), hashlib.sha256(before).hexdigest())
                    try:
                        path.write_bytes(before + b'\n')
                        with self.assertRaises(ValueError):
                            result['final_guard']()
                    finally:
                        path.write_bytes(before)
                    result['final_guard']()


if __name__ == '__main__':
    unittest.main()

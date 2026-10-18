from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_double_replacement_c_stream_independent_readback_20261008 as reader
import test_ndx_double_c_stream_independent_readback_20261008 as fixtures


class Tests(unittest.TestCase):
    def test_fixed_batch_metadata_limits_are_used_for_all_normal_roles(self):
        fixture = fixtures.Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with tempfile.TemporaryDirectory() as directory:
            registration, patches = fixture.fixture(Path(directory))
            seen = []
            original = reader.bounded_json
            def observe(reference, limit):
                seen.append((Path(reference['path']).name, limit))
                return original(reference, limit)
            with patch.object(reader, 'bounded_json', side_effect=observe):
                fixture.readback(registration, patches)
            for name in ('stream_result.json','started.json','raw_receipt.json','inspection.json','raw_byte_inspection.json'):
                limits = [limit for filename,limit in seen if filename == name]
                self.assertTrue(limits, name)
                self.assertEqual(set(limits), {8192}, name)

    def test_reader_ram_threshold_is_engineering_reserve_not_raw_multiplier(self):
        expected = 21 * 1024**3
        for available, accepted in ((expected, True), (expected-1, False)):
            def measure(pointer):
                pointer._obj.available = available
                return 1
            with patch.object(reader.ctypes.windll.kernel32, 'GlobalMemoryStatusEx', side_effect=measure):
                if accepted:
                    reader.memory_gate(1)
                    reader.memory_gate(45036633)
                else:
                    with self.assertRaisesRegex(ValueError,'RAM gate'): reader.memory_gate(1)


if __name__ == '__main__': unittest.main()

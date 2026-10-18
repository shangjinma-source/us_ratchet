from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_multidecision_holdings_supplement_20261008 as publisher
from scripts import ndx_multidecision_holdings_supplement_independent_readback_20261008 as reader
import test_ndx_multidecision_holdings_supplement_source_20261008 as publisher_fixture
import test_ndx_multidecision_holdings_supplement_reader_20261008 as reader_fixture


class Tests(unittest.TestCase):
    def test_publisher_final_output_drift_fails_and_cannot_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            env = publisher_fixture.environment(directory)
            original = publisher.save
            def tamper(path, value):
                reference = original(path, value)
                if path.name == 'publication.json': (path.parent/'supplement.json').write_text('{}')
                return reference
            with patch.multiple(publisher, **env), patch.object(publisher,'save',side_effect=tamper):
                with self.assertRaisesRegex(ValueError,'Final output bytes'): publisher.run(execute=True)
                self.assertTrue((publisher.OUTPUT/'failure.json').exists())
                with self.assertRaisesRegex(ValueError,'Create-only'): publisher.run(execute=True)

    def test_reader_late_raw_source_drift_cannot_preserve_a_clean_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            env = reader_fixture.environment(directory)
            original = reader.save
            # Only synthetic fixture sources are modified.
            raw_path = next(Path(directory).rglob('raw_result.json'))
            def tamper(path, value):
                reference = original(path, value)
                if path.name == 'independent_readback.json': raw_path.write_text('{}')
                return reference
            with patch.multiple(reader, **env), patch.object(reader,'save',side_effect=tamper):
                with self.assertRaisesRegex(ValueError,'Source closure drift'): reader.readback(execute=True)
                self.assertTrue((reader.OUTPUT/'failure.json').exists())
                self.assertTrue((reader.OUTPUT/'independent_readback.json').exists())
                with self.assertRaisesRegex(ValueError,'Create-only'): reader.readback(execute=True)


if __name__ == '__main__': unittest.main()

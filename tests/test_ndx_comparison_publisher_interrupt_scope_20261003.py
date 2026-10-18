"""A synthetic interruption at numerical dispatch must retain attempt evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_multidecision_path_comparison_20261003 as publisher
from test_ndx_multidecision_path_comparison_20261003 import configured


class InterruptScope(unittest.TestCase):
    def test_interrupted_dispatch_keeps_raw_failure_and_forbids_retry(self):
        original = publisher.private_core
        with tempfile.TemporaryDirectory() as directory, configured(Path(directory)):
            def private(sources):
                core = original(sources)
                def interrupted(**kwargs):
                    raise KeyboardInterrupt('synthetic dispatch interruption')
                core.compare_multidecision_paths = interrupted
                return core
            with patch.object(publisher, 'private_core', side_effect=private):
                with self.assertRaises(BaseException):
                    publisher.run(execute=True)
            self.assertTrue((publisher.OUTPUT / 'raw_result.json').exists())
            self.assertTrue((publisher.OUTPUT / 'failure.json').exists())
            raw = json.loads((publisher.OUTPUT / 'raw_result.json').read_bytes())
            self.assertTrue(raw['call_invoked'])
            self.assertFalse(raw['returned'])
            self.assertEqual(raw['error']['type'], 'KeyboardInterrupt')
            self.assertFalse((publisher.OUTPUT / 'publication.json').exists())
            with self.assertRaisesRegex(ValueError, 'no retry'):
                publisher.run(execute=True)


if __name__ == '__main__':
    unittest.main()

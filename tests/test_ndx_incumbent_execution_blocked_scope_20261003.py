"""Dispatch-layer blocked control slots, using synthetic loaded context."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_multidecision_incumbent_execution_20261003 as worker
from test_ndx_multidecision_incumbent_execution_20261003 import physical_execution_sources


class BlockedScope(unittest.TestCase):
    def test_blocked_continuous_slots_keep_full_domain_without_raw_or_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent, bound = physical_execution_sources(root)
            with patch.object(worker, 'BOUND', bound), patch.object(worker, 'PARENT', parent), patch.object(worker, 'OUTPUT', root / 'dispatch'):
                context = worker.load_inputs()
                for lane in context['inputs']['rows']:
                    lane['tracks'][0]['status'] = 'BLOCKED_ORIGINAL_CONTROL_INPUT'
                    lane['tracks'][0]['blocking_reasons'] = ['SYNTHETIC_MISSING_CONTROL_QUOTE']
                def forbidden(**kwargs):
                    raise AssertionError('Blocked track must not call an account')
                context['engines']['CONTINUOUS'] = forbidden
                (worker.OUTPUT / 'tracks').mkdir(parents=True)
                result, references = worker.execute_tracks(context)
                self.assertIsNone(result['failure'])
                self.assertEqual(len(result['rows']), 16)
                self.assertEqual(result['account_call_count'], 8)
                self.assertEqual(result['returned_call_count'], 8)
                for row in result['rows'][::2]:
                    self.assertEqual(row['outcome'], 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT')
                    self.assertFalse(row['call_invoked'])
                    self.assertIsNone(row['raw_reference'])
                    self.assertEqual(row['blocking_reasons'], ['SYNTHETIC_MISSING_CONTROL_QUOTE'])
                    self.assertFalse((worker.OUTPUT / 'tracks' / f"{row['track_index']:02d}" / 'raw_result.json').exists())
                self.assertEqual(len(references), 40)


if __name__ == '__main__':
    unittest.main()

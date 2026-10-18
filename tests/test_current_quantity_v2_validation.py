import json,shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from data import current_quantity_v2_validation as v

class ValidationTests(unittest.TestCase):
    def test_saved_only_and_return_mutation_isolation(self):
        with patch('subprocess.run',side_effect=AssertionError('no worker')):
            a=v.read_quantity_v2_validation();self.assertIsNotNone(a)
            self.assertEqual(a['core_calls'],12);self.assertFalse(a['current_candidate_performance'])
            self.assertFalse(a['current_minute_execution_validated']);self.assertEqual(a['historical_initial_cash'],20000)
            a['source_fingerprints'].clear();self.assertEqual(len(v.read_quantity_v2_validation()['source_fingerprints']),5)

    def test_missing_or_drift_clears_v2(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);self.assertIsNone(v.read_quantity_v2_validation(root=root))
            for relative in v.PINS:
                target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(v.ROOT/relative,target)
            self.assertIsNotNone(v.read_quantity_v2_validation(root=root))
            p=root/v.REVIEW;p.write_bytes(p.read_bytes()+b' ')
            self.assertIsNone(v.read_quantity_v2_validation(root=root))

    def test_existing_projection_keeps_old_fields_and_new_field(self):
        from data.current_strategy_validation import read_current_strategy_validation
        with patch('subprocess.run',side_effect=AssertionError('no worker')):
            data=read_current_strategy_validation()
            self.assertIn('latest_period',data);self.assertIn('modes',data)
            self.assertEqual(data['quantity_v2_period']['method'],v.METHOD)
        with patch('data.current_strategy_validation.read_quantity_v2_validation',return_value=None):
            data=read_current_strategy_validation();self.assertIsNone(data['quantity_v2_period']);self.assertTrue(data['modes'])

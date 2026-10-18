from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from scripts import ndx_non_equal_three_cell_recovery_research as batch


class NoFitBatchTests(unittest.TestCase):
    def test_declared_correction_cannot_be_changed_to_any_other_benchmark(self):
        prepared={'errors':deepcopy(batch.ERRORS)}
        prepared['errors'][0]['new']+=.01
        with self.assertRaises(ValueError):batch.recover_task(prepared,{})

    def test_task_must_be_in_explicit_bucket(self):
        with self.assertRaises(ValueError):batch.recover_task({'errors':deepcopy(batch.ERRORS),'selected':[]},{'task':{}})

    def test_create_only_exact_replay_and_changed_replay_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'new.json'
            first=batch.publish(path,{'bound':True})
            self.assertEqual(first,batch.publish(path,{'bound':True}))
            with self.assertRaises(ValueError):batch.publish(path,{'bound':False})
            self.assertEqual(batch.read(path,first),{'bound':True})

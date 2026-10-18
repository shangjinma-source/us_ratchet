"""Independent metadata mutations only; no actual metrics or accounts."""
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest
import test_ndx_dated_first_economic_comparison_20261003 as owner
m=owner.core

class Review(unittest.TestCase):
    def test_cross_task_and_attempt_status_never_consume(self):
        for kind in ('task','validation','bool','role'):
            d=owner.saved_metadata()
            if kind=='task':d['continuous']['original_task_preserved']['numerical_task_id']='b'*64
            elif kind=='validation':d['candidate_postcheck']['status']='VALIDATION_FAILURE_RECORDED'
            elif kind=='bool':d['candidate_account']['returned_account_count']=True
            else:d['account_audit']['rows'].reverse()
            with self.assertRaises(ValueError):m.project_inputs(d)
    def test_input_and_receipt_source_closure_is_not_self_signed(self):
        for kind in ('input','sources','audit'):
            d=owner.saved_metadata()
            if kind=='input':d['candidate_started']['state']['inputs_reference']['sha256']='f'*64
            elif kind=='sources':d['continuous_publication']['source_hashes']['extra']='b'*64
            else:d['nav_audit']['metrics_sha256']='a'*64
            with self.assertRaises(ValueError):m.project_inputs(d)
    def test_existing_namespace_fails_before_any_load(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)),patch.object(m,'load_inputs') as load:
            (Path(tmp)/'failure.json').write_text('{}')
            with self.assertRaises(ValueError):m.run(execute=True)
            load.assert_not_called()
        with self.assertRaises(ValueError):m.guard({str(m.SOURCE):'0'*64})

if __name__=='__main__':unittest.main()

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_prospective_observation_writer_20261003 as m
from backtest import ndx_prospective_observation_receipt_research as core
from test_ndx_prospective_observation_writer_20261003 import args


def documents():
    refs={k:dict(path=k+'.json',sha256='a'*64) for k in m.BOUND}
    flags={k:False for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed')}
    known=[dict(kind='SEALED_PARENT_OBSERVED_SESSION',session=str(i)) for i in range(65)]
    p=dict(schema='SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1',policy_id='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH',source_hashes={},frontier_reference={},projection_inputs=dict(known_rows=known,new_prospective_observations=[]),new_observation_count=0,**flags)
    pub=dict(status='PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL',policy_reference=refs['parent'],source_hashes={},**flags)
    audit=dict(schema='SYNTHETIC_PARENT',status='PASS',policy_reference=refs['parent'],publication_reference=refs['parent_publication'],**flags)
    c=dict(schema='FORWARD_SOURCE_CAPTURE_SCOPED_PAYLOAD_V1',source_hashes={},input_references={'frontier':{}},plan=dict(schema='FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1',capture_plan=dict(schema='FORWARD_SOURCE_CAPTURE_PLANNING_V1',accounted_prefix_dates=[r['session'] for r in known],revisions=[],new_source_dates=['next'])),**flags)
    cp=dict(status='PUBLISHED_CURRENT_CACHE_CAPTURE_NOT_CALENDAR_APPEND',capture_reference=refs['capture'],source_hashes={},**flags)
    return dict(parent=p,parent_publication=pub,parent_readback=audit,capture=c,capture_publication=cp),refs


class Tests(unittest.TestCase):
    def test_metadata_false_count_and_reference_prefix_tamper(self):
        docs,refs=documents()
        with patch.object(m,'SESSION','next'),patch.object(m,'PARENT_READBACK_SCHEMA','SYNTHETIC_PARENT'):
            m.validate_documents(docs,refs)
            for mutation in (
                lambda d:d['parent'].__setitem__('new_observation_count',False),
                lambda d:d['parent'].__setitem__('new_observation_count',0.0),
                lambda d:d['capture']['plan']['capture_plan']['accounted_prefix_dates'].pop(),
                lambda d:d['parent_readback'].__setitem__('publication_reference',{}),
                lambda d:d['capture_publication'].__setitem__('candidate_seal_allowed',True),
            ):
                bad=deepcopy(docs);mutation(bad)
                with self.assertRaises(ValueError):m.validate_documents(bad,refs)

    def test_receipt_write_failure_preserves_payload_no_retry(self):
        original=m.save
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'attempt'
            def fail_receipt(path,value):
                if path.name=='receipt.json':raise OSError('synthetic receipt failure')
                return original(path,value)
            with patch.object(m,'OUTPUT',out),patch.object(m,'load_inputs',return_value=(args(),{},{},core)),patch.object(m,'now',return_value='2026-10-02T20:00:03+00:00'),patch.object(m,'guard'),patch.object(m,'save',side_effect=fail_receipt):
                with self.assertRaises(OSError):m.run(execute=True)
                blob=(out/'observation_payload.json').read_bytes()
                failure=m.load_json((out/'failure.json').read_bytes());self.assertTrue(failure['observation_payload_must_not_be_discarded'])
                with self.assertRaises(ValueError):m.run(execute=True)
                self.assertEqual((out/'observation_payload.json').read_bytes(),blob)

    def test_publication_clock_reversal_and_runtime_drift(self):
        for drift in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                times=iter(['2026-10-02T20:00:03+00:00','2026-10-02T20:00:04+00:00','2026-10-02T20:00:02+00:00','2026-10-02T20:00:05+00:00'])
                runtime=iter([{'v':1},{'v':2 if drift else 1}])
                out=Path(tmp)/'attempt'
                with patch.object(m,'OUTPUT',out),patch.object(m,'load_inputs',return_value=(args(),{},{},core)),patch.object(m,'now',side_effect=lambda:next(times)),patch.object(m,'runtime',side_effect=lambda:next(runtime)),patch.object(m,'guard'):
                    with self.assertRaises(ValueError):m.run(execute=True)
                    self.assertTrue((out/'observation_payload.json').exists());self.assertTrue((out/'failure.json').exists());self.assertFalse((out/'receipt.json').exists())

if __name__=='__main__':unittest.main()

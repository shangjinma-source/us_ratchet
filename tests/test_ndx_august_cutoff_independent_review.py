import copy
import json
import unittest
from unittest.mock import patch
from scripts import ndx_august_cutoff_snapshot_independent_readback_20260919 as m
from scripts import ndx_july_cutoff_snapshot_independent_readback_20260919 as july
from test_ndx_august_cutoff_snapshot_independent_readback_20260919 import fixture


class AugustReview(unittest.TestCase):
    def test_actual_august_denominator_rejects_july_coordinate_and_seed(self):
        queue=json.loads(m.QUEUE.read_bytes())
        flags=dict.fromkeys(m.FLAGS,False)
        index=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_COMPLETION_INDEX_V1',queue=dict(path=str(m.QUEUE),sha256=m.QUEUE_SHA),seed=None,
            planned=232,completed=[],status='PARTIAL',finalization=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_FINALIZATION_V1',planned=232,completed=0,status='PARTIAL',**flags),**flags)
        self.assertEqual(len(m.validate_index(index,queue)),232)
        self.assertNotEqual(m.CONTEXT_SHA,july.CONTEXT_SHA)
        for replacement in (dict(path=str(july.QUEUE),sha256=july.QUEUE_SHA),dict(path=str(m.QUEUE),sha256=july.QUEUE_SHA)):
            bad=copy.deepcopy(index);bad['queue']=replacement
            with self.assertRaises(ValueError):m.validate_index(bad,queue)
        bad=copy.deepcopy(index);bad['seed']={}
        with self.assertRaises(ValueError):m.validate_index(bad,queue)

    def test_success_null_numerical_source_and_attempt_drift_rejected(self):
        with patch.object(m,'PLANNED',104),patch.object(m,'QUEUE_SHA','1'*64):
            for defect in ('null','source','attempt'):
                q,i,v,a=fixture();candidates=m.validate_index(i,q)
                m.validate_task(v,a,q,i,candidates)
                if defect=='null':v['result']['refit']=None
                if defect=='source':
                    sources=v['result']['refit']['source_hashes'];sources[next(iter(sources))]='0'*64
                if defect=='attempt':a['runner_source_hashes']={}
                with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_task(v,a,q,i,candidates)


if __name__=='__main__':unittest.main()

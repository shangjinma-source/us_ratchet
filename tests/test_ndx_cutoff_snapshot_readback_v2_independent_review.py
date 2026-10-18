from copy import deepcopy
import unittest
from test_ndx_cutoff_snapshot_independent_readback_v2_20260919 import Tests as OwnerTests
from test_ndx_cutoff_snapshot_independent_readback_20260919 import fixture
from scripts import ndx_cutoff_snapshot_independent_readback_v2_20260919 as m


class IndependentTests(unittest.TestCase):
    def test_success_payload_and_check_types_fail_closed(self):
        for malformed in (None,[],False,0):
            value,attempt,kwargs=OwnerTests().nonseed()
            value['result']['refit']=malformed
            with self.subTest(refit=malformed),self.assertRaises(ValueError):m.validate_task(value,attempt,**kwargs)
        for defect in ('integer','missing','extra'):
            value,attempt,kwargs=OwnerTests().nonseed();value['result']['refit']={}
            checks=value['result']['independently_recomputed_five_checks']
            if defect=='integer':checks[next(iter(checks))]=1
            if defect=='missing':checks.pop(next(iter(checks)))
            if defect=='extra':checks['EXTRA']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_task(value,attempt,**kwargs)

    def test_explicit_numerical_failure_remains_failure(self):
        value,attempt,kwargs=OwnerTests().nonseed();result=value['result']
        result.pop('independently_recomputed_five_checks')
        result.update(status='FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY',error='synthetic arithmetic failure',error_type='ArithmeticError')
        self.assertIsNone(m.validate_task(value,attempt,**kwargs)['refit'])
        self.assertIs(result['numerical_failure_is_economic_infeasibility'],False)

    def test_nonempty_completed_queue_cannot_omit_seed(self):
        value,attempt,kwargs=OwnerTests().nonseed();index=deepcopy(kwargs['index'])
        index['completed']=[dict(job_id=value['job_id'])]
        m.previous.validate_index(index,kwargs['queue'])
        with self.assertRaisesRegex(ValueError,'retain its completed seed'):m.validate_index(index,kwargs['queue'])


if __name__=='__main__':unittest.main()

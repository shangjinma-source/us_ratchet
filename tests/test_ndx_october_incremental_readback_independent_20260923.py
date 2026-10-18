from copy import deepcopy
import unittest
from scripts import ndx_october_incremental_readback_20260923 as m


class IncrementalPrefixReview(unittest.TestCase):
    def fixture(self):
        entries=[dict(job_id=str(i),started={'path':str(i)+'.started','sha256':'s'},
                      result={'path':str(i)+'.result','sha256':'r'}) for i in range(202)]
        previous=dict(completed=deepcopy(entries[:201]))
        seed=dict(schema=m.original.SCHEMA,completed=201,
                  details=[dict(job_id=entry['job_id'],result_reference=deepcopy(entry['result'])) for entry in entries[:201]])
        return seed,previous,dict(completed=entries)

    def test_exact_prefix_accepted_without_numerical_functions(self):
        m.check_prefix(*self.fixture())

    def test_old_result_or_attempt_reference_cannot_change(self):
        for key in ('result','started'):
            seed,old,current=self.fixture()
            current['completed'][100][key]['sha256']='changed'
            with self.assertRaises(ValueError):m.check_prefix(seed,old,current)

    def test_resigned_detail_reference_or_order_rejected(self):
        seed,old,current=self.fixture();seed['details'][0]['result_reference']['sha256']='changed'
        with self.assertRaises(ValueError):m.check_prefix(seed,old,current)
        seed,old,current=self.fixture();seed['details'][0],seed['details'][1]=seed['details'][1],seed['details'][0]
        with self.assertRaises(ValueError):m.check_prefix(seed,old,current)

    def test_no_growth_or_wrong_prefix_count_rejected(self):
        seed,old,current=self.fixture();current['completed'].pop()
        with self.assertRaises(ValueError):m.check_prefix(seed,old,current)
        seed,old,current=self.fixture();seed['completed']=True
        with self.assertRaises(ValueError):m.check_prefix(seed,old,current)
        seed,old,current=self.fixture();old['completed'].pop()
        with self.assertRaises(ValueError):m.check_prefix(seed,old,current)


if __name__=='__main__':unittest.main()

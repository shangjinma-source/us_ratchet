"""Independent June coordinate/typed matrix counterexamples; no fit or readback build."""
import unittest
from test_ndx_june_cutoff_snapshot_independent_readback_20260919 import actual_fixture
from scripts import ndx_june_cutoff_snapshot_independent_readback_20260919 as m


class ReviewTests(unittest.TestCase):
    def test_june_matrix_cannot_relabel_may_or_fake_hash(self):
        for key,value in [('cutoff','2023-04-28'),('fit_end','2023-04-28'),('fit_data_sha256','0'*64)]:
            q,c,i,v,a=actual_fixture();v['result']['refit'][key]=value
            result=m.validate_task(v,a,q,i,m.validate_index(i,q))
            with self.subTest(key=key),self.assertRaises(ValueError):m.pure.inspect_context(c,q,result)

    def test_import_seed_or_foreign_attempt_forbidden(self):
        for defect in ('mode','attempt','source'):
            q,c,i,v,a=actual_fixture()
            if defect=='mode':v['mode']='IMPORTED_EXISTING_SEED'
            if defect=='attempt':a['queue']['path']=str(m.may.QUEUE)
            if defect=='source':v['result']['refit']['source_hashes'][str(m.ROOT/m.NUMERICAL_FILES[0])]='0'*64
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_task(v,a,q,i,m.validate_index(i,q))


if __name__=='__main__':unittest.main()

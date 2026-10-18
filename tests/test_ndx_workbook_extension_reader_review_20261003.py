import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_ndx_dated_workbook_extension_data_independent_readback_20261003 import fixture,check,rewrite_first,m

class IndependentReview(unittest.TestCase):
    def test_resigned_missing_row_and_saved_risk_source_cannot_be_changed(self):
        for mutate in (lambda r:r['risk_tracks']['candidate_integer'].update(source_reference={'path':'invented','sha256':'a'*64}),lambda r:r.update(formal_comparison_passed=0),lambda r:r.update(engine_normalization_evidence={})):
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):check(rewrite_first(fixture(),mutate))
        f=fixture();f[5]['task_index'][-1]['status']='DISPLAY_PROJECTED'
        with self.assertRaises(ValueError):check(f)

    def test_complete_strata_and_package_partition_are_not_display_estimates(self):
        for mutation in ('bool_count','last_spec','package_missing','calendar'):
            f=fixture()
            if mutation=='bool_count':f[5]['projected_task_count']=True
            elif mutation=='last_spec':f[3]['task_index'][-1]['weight_spec']='fourth'
            elif mutation=='package_missing':f[5]['package_plan']['packages'][0]['tasks'].pop()
            else:f[4]['calendar']=f[4]['calendar'][:-1]
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):check(f)

    def test_shared_identity_failure_retained_and_retry_blocked(self):
        f=fixture();paths=f[6];first=next(iter(paths));paths[first]['identity']['role']='candidate_integer'
        with self.assertRaises(ValueError):check(f)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'new';loaded=({}, {}, {}, {}, {}, {}, {}, {}, {}, {})
            with patch.object(m,'OUTPUT',out),patch.object(m,'load',return_value=loaded),patch.object(m,'inspect_classification',side_effect=ValueError('bad classification')):
                with self.assertRaises((ValueError,KeyError)):m.run(execute=True)
                self.assertTrue((out/'failure.json').is_file())
                with self.assertRaisesRegex(ValueError,'Create-only'):m.run(execute=True)

if __name__=='__main__':unittest.main()

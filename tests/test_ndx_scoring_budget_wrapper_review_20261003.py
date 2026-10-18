from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from test_ndx_multidecision_scoring_budget_wrapper_20261003 import fixture
from scripts import ndx_multidecision_scoring_budget_20261003 as m

class Review(unittest.TestCase):
    def test_saved_roles_and_full_inventory_not_relabelled(self):
        for attack in (lambda d:d['history_audit']['rows'][0]['inspection'].update(window_count=78.),
                       lambda d:d['target_audit'].update(reader_sha256='f'*64),
                       lambda d:d['original8_audit'].update(fit_performed=0),
                       lambda d:d['mdv_result']['periods'][5]['rows'][76]['required_dates'].pop()):
            d,r,c=fixture();attack(d)
            with self.assertRaises(ValueError):m.project_inputs(d,r,c)
        d,r,c=fixture();a=m.project_inputs(d,r,c)
        self.assertEqual(len(a['universe']),77)
        self.assertTrue(all(len(x['qualifications'])==77 for x in a['decisions']))
        self.assertTrue(all(x['mode_sources'][0]['complete_thirteen_windows'] is False for x in a['decisions']))

    def test_new_fitter_manifest_not_old_baseline_alias(self):
        ref={'path':'policy','sha256':'a'*64}
        sources={str(m.ROOT/f'code{i}.py'):'b'*64 for i in range(23)}
        sources.update({str(m.ROOT/'backtest/ndx_multidecision_rolling_fit_research.py'):'b'*64,str(m.ROOT/'backtest/ndx_multidecision_window_scoring_research.py'):'b'*64})
        doc=dict(schema=m.ROLLING_MANIFEST_SCHEMA,status='FROZEN_BEFORE_ACTUAL_PLAN_OR_SCORE_NOT_DISPATCH_AUTHORITY',policy_reference=ref,required_worker_environment={'PYTHONHASHSEED':'0','sys_flags_hash_randomization':0},inner_prior='FIRST_NONE_THEN_SAME_CANDIDATE_PREVIOUS_TARGET',first_anchored_fit_none_interpretation='LEGACY_EQUAL_WEIGHT_ANCHOR',first_anchored_fit_strength=.25,source_hashes=sources,runtime_versions=dict.fromkeys(('python','numpy','pandas','scipy'),'synthetic'),**dict.fromkeys(('execution_authorized','fit_performed','score_computed','point_in_time_verified','promotion_allowed','outer_cutoff_refit_substitution_allowed'),False))
        self.assertEqual(m.validate_fitter(doc,{},ref),sources)
        with self.assertRaises(ValueError):m.validate_fitter(doc,{next(iter(sources)):'c'*64},ref)
        doc['required_worker_environment']['sys_flags_hash_randomization']=False
        with self.assertRaises(ValueError):m.validate_fitter(doc,{},ref)

    def test_incomplete_sampling_preserves_full_diagnostic_plan(self):
        d,r,c=fixture();a=m.project_inputs(d,r,c);core=m.private_budget({});plan=core.plan_multidecision_scoring_budget(**a)
        plan['rows'][0]['sampling']['complete']=False;plan['rows'][0]['sampling']['status']='INCOMPLETE_POINT_SELECTION'
        plan['content_sha256']=m.sha(m.encoded({k:v for k,v in plan.items() if k!='content_sha256'}))
        stub=SimpleNamespace(plan_multidecision_scoring_budget=lambda **kw:plan)
        with TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)/'out'),patch.object(m,'space'),patch.object(m,'guard'),patch.object(m,'load_inputs',return_value=(d,r,{},a,stub)):
            with self.assertRaises(ValueError):m.run(execute=True)
            failure=m.loads((m.OUTPUT/'failure.json').read_bytes())
            refs=[x for x in failure['saved_references'] if Path(x['path']).name!='started.json']
            self.assertEqual(len(refs),1)
            blob=Path(refs[0]['path']).read_bytes();self.assertEqual(m.sha(blob),refs[0]['sha256'])
            diagnostic=m.loads(blob)
            self.assertIn(m.encoded(plan),m.encoded(diagnostic))
            self.assertFalse((m.OUTPUT/'publication.json').exists())
            with self.assertRaises(ValueError):m.run(execute=True)

if __name__=='__main__':unittest.main()

"""New independent adversarial tests. All attempts use mocked fitter output."""
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
from test_ndx_dated_single_task_20261003 import documents,small_state
from scripts import ndx_dated_single_task_20261003 as m

class Review(unittest.TestCase):
    def test_last_task_resigned_location_and_prior_rejected(self):
        docs,sources=documents()
        self.assertEqual(len(m.validate_common(docs,sources)['tasks']),1632)
        for mode in ('location','prior','evidence','count'):
            bad=deepcopy(docs);materialized=bad['preparation']['materialized'];task=materialized['combinations'][-1]['tasks'][-1]
            if mode=='location':
                task['location_identity']['combination_index']=False;task['location_id']=m.digest(task['location_identity'])
            elif mode=='prior':
                task['numerical_identity']['requested_previous_target_weights']={};task['numerical_task_id']=m.digest(task['numerical_identity'])
            elif mode=='evidence':bad['preparation']['preserved_evidence_sidecars'].popitem()
            else:materialized['new_cutoff_completed_task_count']=False
            materialized['content_sha256']=m.digest({k:v for k,v in materialized.items() if k!='content_sha256'})
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.validate_common(bad,sources)

    def test_old_bulk_root_blocks_new_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            old=Path(folder)/'bulk';tid='a'*64;(old/tid).mkdir(parents=True)
            with patch.object(m,'OLD_ROOTS',(old,)),patch.object(m,'OUTPUT_ROOT',Path(folder)/'new'),patch.object(m,'load_common',side_effect=AssertionError('must not load')):
                with self.assertRaises(ValueError):m.preflight(tid)

    def test_raw_is_durable_before_postguard_and_exception_classification(self):
        for failure in (False,True):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
                state=small_state();tid=state['task']['numerical_task_id'];root=Path(folder)/'new';destination=root/tid
                stack.enter_context(patch.object(m,'OUTPUT_ROOT',root));stack.enter_context(patch.object(m,'OLD_ROOTS',()))
                stack.enter_context(patch.object(m,'preflight',return_value=state));calls=[]
                def guard(_):
                    calls.append(1)
                    if len(calls)==2:
                        self.assertTrue((destination/'raw.json').is_file())
                        if not failure:raise ValueError('source drift after returned fit')
                stack.enter_context(patch.object(m,'guard',side_effect=guard))
                mock=stack.enter_context(patch.object(m.fitter,'refit_dynamic_cutoff_weights',side_effect=ArithmeticError('no returned fit') if failure else None,return_value={'evidence':'returned'}))
                ref=m.run(tid,execute=True);post=json.loads(Path(ref['path']).read_bytes());raw=json.loads((destination/'raw.json').read_bytes())
                self.assertEqual(post['status'],'NUMERICAL_EXCEPTION_NO_RETURNED_FIT' if failure else 'VALIDATION_FAILURE_RECORDED')
                self.assertEqual(raw['returned_fit_count'],0 if failure else 1);self.assertIsNone(raw['internal_optimizer_call_count'])
                if not failure:self.assertEqual(raw['fitted'],{'evidence':'returned'})
                with self.assertRaises(ValueError):m.run(tid,execute=True)
                self.assertEqual(mock.call_count,1)

    def test_declared_risk_boolean_not_integer(self):
        state=small_state();identity=state['task']['numerical_identity'];targets={sid:dict(ticker=v['ticker'],issuer_id=v['issuer_id'],target_weight=.25) for sid,v in identity['selected'].items()}
        fitted=dict(schema='ndx_dynamic_cutoff_refit_research_v2',fit_data_sha256=identity['fit_data_sha256'],cutoff=identity['cutoff'],weight_spec='equal_weight',source_hashes={},previous_target_weights={},targets=targets,declared_constraint_checks={k:1 for k in ('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')},declared_constraints_passed=True)
        with patch.object(m.fitter,'_sources',return_value={}):
            with self.assertRaises(ValueError):m.postflight(state,fitted)

if __name__=='__main__':unittest.main()

"""Synthetic metadata and mocked single attempts; no saved queue or fit runs."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import date,timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_dated_single_task_20261003 as module
from backtest import ndx_dated_fixed_task_preparation_research as preparation
from test_ndx_dated_fixed_task_preparation_research import fixture as preparation_fixture


def documents():
    a=preparation_fixture();r=module.ref
    # Rewrite only the externally declared fixture references, and recompute its
    # original metadata IDs before materializing the synthetic dated batch.
    a['training_reference']=r('panel');a['prior_preparation_reference']=r('prior_preparation');a['original_plan_reference']=r('plan')
    old=a['prior_preparation'];plan=a['original_lazy_plan'];old['materialized']['plan_reference']=r('plan')
    for c in old['materialized']['combinations']:
        for t in c['tasks']:
            t['location_identity']['plan_reference']=r('plan');t['location_id']=preparation.digest(t['location_identity'])
    out=preparation.prepare_dated_tasks(**a);panel=a['training_panel'];flags=dict.fromkeys(('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted'),False)
    q=dict(schema='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_DOCUMENT_V1',materialized=out,source_hashes={},training_fit_payload=panel['fit_payload'],complete_observed_provenance_and_missing=panel['original_provenance_and_missing'],preserved_evidence_sidecars=panel['preserved_evidence_sidecars'],original_coordinate_evidence=panel['original_coordinate_evidence'],evaluation_references=panel['evaluation_references'],late_pool_and_composition_selection=True,**flags)
    pub=dict(schema='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_PUBLICATION_V1',status='PUBLISHED_NEW_DATED_TASK_INPUTS_NOT_FITTED',preparation_reference=r('preparation'),source_hashes={})
    audit=dict(schema='DATED_FIXED_TASK_PREPARATION_INDEPENDENT_READBACK_V1',status='PASS',preparation_sha256=r('preparation')['sha256'],publication_sha256=r('publication')['sha256'],reader_sha256=r('audit_reader')['sha256'],combination_count=544,materialized_task_count=1632,new_numerical_ids=1632,new_location_ids=1632,old_id_intersection=0,original_provenance_count=101,preserved_sidecar_count=7,new_cutoff_completed_task_count=0)
    return dict(preparation=q,publication=pub,audit=audit,panel=dict(schema='DATED_CONDITIONAL_TRAINING_PANEL_DOCUMENT_V1',panel=panel,**flags),plan=dict(plan=plan),prior_preparation=old),plan['fitter_source_hashes']


def small_state():
    selected={f'S{i}':dict(ticker=f'T{i}',issuer_id=f'I{i}',risk_chain=f'R{i}') for i in range(4)}
    identity=dict(selected=selected,parameters=module.PARAMETERS,weight_spec='equal_weight',requested_previous_target_weights=None,cutoff='2026-03-20',fit_data_sha256='a'*64)
    return dict(task=dict(numerical_identity=identity,numerical_task_id=module.digest(identity)),returns=module.pd.DataFrame(),combination_identity={},source_hashes={},runtime=module.runtime(),input_references={})


class Tests(unittest.TestCase):
    def test_complete_synthetic_queue_and_mutations(self):
        docs,num=documents();result=module.validate_common(docs,num)
        self.assertEqual(len(result['tasks']),1632)
        for mutate in (lambda d:d['preparation']['materialized'].update(materialized_task_count=True),
                       lambda d:d['preparation']['preserved_evidence_sidecars'].popitem(),
                       lambda d:d['panel']['panel']['fit_payload']['returns']['data'][0].__setitem__(0,True),
                       lambda d:d['preparation']['materialized']['combinations'][0]['tasks'][0]['numerical_identity'].update(schema='WRONG')):
            bad=deepcopy(docs);mutate(bad)
            with self.assertRaises(ValueError):module.validate_common(bad,num)

    def test_all_eight_roots_reject_before_load(self):
        tid='a'*64
        for which in range(8):
            with tempfile.TemporaryDirectory() as td:
                roots=[Path(td)/str(i) for i in range(8)];(roots[which]/tid).mkdir(parents=True)
                with patch.object(module,'OLD_ROOTS',tuple(roots[:7])),patch.object(module,'OUTPUT_ROOT',roots[7]),patch.object(module,'load_common') as load:
                    with self.assertRaises(ValueError):module.preflight(tid)
                    load.assert_not_called()

    def attempt(self,td,fit,guard=None,post=None):
        state=small_state();tid=state['task']['numerical_task_id'];stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(module,'OUTPUT_ROOT',Path(td)/'new'))
        stack.enter_context(patch.object(module,'OLD_ROOTS',()))
        stack.enter_context(patch.object(module,'preflight',return_value=state))
        stack.enter_context(patch.object(module,'guard',side_effect=guard))
        fitter=stack.enter_context(patch.object(module.fitter,'refit_dynamic_cutoff_weights',side_effect=fit))
        stack.enter_context(patch.object(module,'postflight',return_value=post or dict(PASS=True)))
        return tid,fitter

    def test_no_execute_no_files_no_fit_and_strict_bool(self):
        with tempfile.TemporaryDirectory() as td:
            tid,fit=self.attempt(td,lambda **kw:{})
            module.run(tid);fit.assert_not_called();self.assertFalse((Path(td)/'new').exists())
            with self.assertRaises(ValueError):module.run(tid,execute=1)

    def test_returned_raw_survives_post_source_drift_and_no_retry(self):
        with tempfile.TemporaryDirectory() as td:
            calls=[]
            def guard(_):
                calls.append(1)
                if len(calls)>1:raise ValueError('drift')
            tid,fit=self.attempt(td,lambda **kw:dict(targets='retained'),guard)
            ref=module.run(tid,execute=True);post=json.loads(Path(ref['path']).read_bytes());raw=json.loads((Path(ref['path']).parent/'raw.json').read_bytes())
            self.assertEqual(raw['fitted'],dict(targets='retained'));self.assertEqual(post['status'],'VALIDATION_FAILURE_RECORDED')
            with self.assertRaises(ValueError):module.run(tid,execute=True)
            self.assertEqual(fit.call_count,1)

    def test_exception_and_risk_failure_distinct(self):
        for error in (True,False):
            with tempfile.TemporaryDirectory() as td:
                def fit(**kw):
                    if error:raise ArithmeticError('no return')
                    return dict(returned=True)
                tid,mock=self.attempt(td,fit,post=dict(PASS=False))
                ref=module.run(tid,execute=True);post=json.loads(Path(ref['path']).read_bytes());raw=json.loads((Path(ref['path']).parent/'raw.json').read_bytes())
                self.assertEqual(post['status'],'NUMERICAL_EXCEPTION_NO_RETURNED_FIT' if error else 'ORIGINAL_RISKS_FAILED_PENDING_INDEPENDENT_READBACK')
                self.assertEqual(raw['returned_fit_count'],0 if error else 1);self.assertIsNone(raw['internal_optimizer_call_count'])

    def test_common_handle_forgery_rejected(self):
        with patch.object(module,'check_roots'),patch.object(module.fitter,'refit_dynamic_cutoff_weights') as fit:
            with self.assertRaises(ValueError):module.preflight('a'*64,common=dict(ordered_task_ids=[]))
            fit.assert_not_called()


if __name__=='__main__':unittest.main()

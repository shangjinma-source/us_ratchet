from copy import deepcopy
import hashlib,json,tempfile
import weakref
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_corrected_cutoff_snapshot_research as m
from test_ndx_corrected_frontier_cutoff_refit_archive_research import context_fixture


def snapshot_fixture(reference=None):
    context,report,inputs=context_fixture()
    _,changed,identities,binding=m.adapter.correct_context(context,report,'2022-07-29')
    selected={identities[t]['security_id']:{k:identities[t][k] for k in ('ticker','issuer_id','risk_chain')} for t in ('AMAT','AVGO','CDNS','GOOG')}
    rows={j:dict(task=dict(job_id=j,weight_spec='equal_weight'),selected=selected) for j in ('a','b')}
    queue=dict(candidates=list(rows.values()),candidate_count=2,original_runtime=context['runtime'],input_binding=binding,historical_cutoff='2022-07-29',
        fit_parameters={k:inputs['contract'][k] for k in m.adapter.PARAMETERS},historical_loader_gap_observations=[],historical_expected_source_hashes={})
    temporary=None
    if reference is None:
        temporary=tempfile.TemporaryDirectory();path=Path(temporary.name)/'queue.json';path.write_text(json.dumps(queue));reference=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    sources={str(m.SOURCE):m.LOADED,str(m.single.SOURCE):m.single.LOADED,reference['path']:reference['sha256']}
    small=dict(sources,**{str(m.adapter.archive.ARCHIVE):m.adapter.archive.ARCHIVE_SHA})
    snapshot=m.Snapshot();m.STATES[snapshot]=dict(queue=queue,queue_digest=m.adapter.digest(queue),reference=reference,reference_digest=m.adapter.digest(reference),
        rows=rows,changed=changed,sources=sources,small_sources=small,additional={},additional_digest=m.adapter.digest({}),records={},records_digest=m.adapter.digest({}),closed=False,seed=None,seed_reference_digest=m.adapter.digest(None),temporary=temporary)
    if temporary is not None:weakref.finalize(snapshot,temporary.cleanup)
    return snapshot


class Tests(unittest.TestCase):
    def test_seed_full_wrapper_import_no_refit_and_wrong_attempt_reject(self):
        source=snapshot_fixture();result=m.evaluate(source,'b')['result'];result['schema']='CORRECTED_FRONTIER_HISTORICAL_CUTOFF_TASK_V1'
        snapshot=snapshot_fixture();s=m.state(snapshot)
        with tempfile.TemporaryDirectory() as folder,patch.object(m.adapter,'verify'):
            target=Path(folder)/'seed.json';started=Path(str(target)+'.started.json')
            hashes={str(m.single.SOURCE):m.single.LOADED,s['reference']['path']:s['reference']['sha256']}
            attempt=dict(schema='CORRECTED_FRONTIER_SINGLE_REFIT_ATTEMPT_V1',queue=s['reference'],job_id='b',output=str(target),runner_source_hashes=hashes,status='STARTED_NOT_COMPLETED')
            started.write_text(json.dumps(attempt));startref=dict(path=str(started),sha256=hashlib.sha256(started.read_bytes()).hexdigest())
            result['historical_expected_source_hashes']={}
            seed=dict(schema='CORRECTED_FRONTIER_SINGLE_REFIT_EXECUTION_V1',queue=s['reference'],job_id='b',fit_performed=True,
                selection_performed=False,point_in_time_verified=False,promotion_allowed=False,runner_source_hashes=hashes,started_attempt=startref,result=result)
            target.write_text(json.dumps(seed));s['seed']=dict(path=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest());s['seed_value']=seed
            s['seed_reference_digest']=m.adapter.digest(s['seed']);s['seed_wrapper_digest']=m.adapter.digest(seed)
            with patch.object(m.adapter.fitter,'refit_dynamic_cutoff_weights',side_effect=AssertionError('No seed refit')):
                imported=m.import_seed(snapshot)
            self.assertEqual(imported['original_single_fit_wrapper'],seed)
            with self.assertRaises(ValueError):m.evaluate(snapshot,'b')
            s['seed_value']['job_id']='a'
            with patch.object(m.adapter.fitter,'refit_dynamic_cutoff_weights') as fit:
                with self.assertRaises(ValueError):m.evaluate(snapshot,'b')
                fit.assert_not_called()
            s['seed_value']['job_id']='b'
            hard_seed=s['seed'];s['seed']=None
            with patch.object(m.adapter.fitter,'refit_dynamic_cutoff_weights') as fit:
                with self.assertRaises(ValueError):m.evaluate(snapshot,'a')
                fit.assert_not_called()
            s['seed']=hard_seed
            wrong=deepcopy(seed);wrong['result']['schema']='UNKNOWN_SAVED_NUMERICAL_ENGINE'
            with self.assertRaises(ValueError):m.validate_seed(s,wrong,s['seed'])
            started.write_text('{}')
            with self.assertRaises(ValueError):m.validate_seed(s,seed,s['seed'])

    def test_real_small_fitter_no_global_change_and_restore_validation(self):
        snapshot=snapshot_fixture();s=m.state(snapshot);before=m.adapter.typed.provenance._digest(s['changed'])
        with patch.object(m.adapter,'prepare_queue',side_effect=AssertionError('No repeated prepare')),patch.object(m,'verify_all',side_effect=AssertionError('No repeated full scan')):
            result=m.evaluate(snapshot,'a')
        self.assertEqual(before,m.adapter.typed.provenance._digest(s['changed']))
        self.assertEqual(result['result']['status'],'FITTED_FIVE_RISKS_PASSED')
        m.validate_result(s,result['result'])
        with self.assertRaises(ValueError):m.evaluate(snapshot,'a')
        for defect in ('nan','fitdata','risk','scope'):
            bad=deepcopy(result['result'])
            if defect=='nan':bad['refit']['targets']['security:AMAT']['target_weight']=float('nan')
            if defect=='fitdata':bad['refit']['fit_data_sha256']='0'*64
            if defect=='risk':bad['independently_recomputed_five_checks']['MAX_SINGLE_WEIGHT']=False
            if defect=='scope':bad['promotion_allowed']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_result(s,bad)

    def test_memory_runtime_changes_rejected_before_fit(self):
        for defect in ('matrix','runtime','queue','rows','sources','small_sources','additional'):
            snapshot=snapshot_fixture();s=m.state(snapshot)
            if defect=='matrix':s['changed']['nominal_prices'].iloc[0,0]+=1
            if defect=='runtime':s['queue']['original_runtime']['python']='0'
            if defect=='queue':s['queue']['fit_parameters']['max_single_weight']=1.
            if defect=='rows':s['rows']=deepcopy(s['rows']);s['rows']['a']['task']['weight_spec']='constrained_fixed_shrinkage'
            if defect=='sources':s['sources'].clear()
            if defect=='small_sources':s['small_sources'].clear()
            if defect=='additional':s['additional']['fake']='0'*64
            with patch.object(m.adapter.fitter,'refit_dynamic_cutoff_weights') as fit:
                with self.assertRaises(ValueError):m.evaluate(snapshot,'a')
                fit.assert_not_called()

    def test_numeric_failure_record_is_not_economic_infeasibility(self):
        snapshot=snapshot_fixture()
        with patch.object(m.adapter.fitter,'refit_dynamic_cutoff_weights',side_effect=RuntimeError('synthetic solver failure')):
            result=m.evaluate(snapshot,'b')['result']
        self.assertEqual(result['status'],'FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY')
        self.assertFalse(result['numerical_failure_is_economic_infeasibility']);self.assertIsNone(result['refit'])

    def test_full_finish_source_drift_cannot_complete(self):
        snapshot=snapshot_fixture()
        with patch.object(m.adapter.archive,'load_contract',return_value={}),patch.object(m.adapter.archive,'verify_expected_sources',side_effect=ValueError('unrelated source changed')):
            with self.assertRaises(ValueError):m.finish(snapshot)
        self.assertTrue(m.STATES[snapshot]['closed'])


if __name__=='__main__':unittest.main()

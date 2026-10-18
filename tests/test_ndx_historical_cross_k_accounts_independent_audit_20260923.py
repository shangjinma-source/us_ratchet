import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from test_ndx_historical_cross_k_account_independent_research import fixture
from scripts import ndx_historical_cross_k_accounts_independent_audit_20260923 as m


def skipped_fixture():
    args=fixture();task=args['task'];result=args['result'];selected=task['selected']
    for r in selected.values():r['risk_chain']='synthetic_one_chain'
    for r in args['inputs']['candidate_coordinate_and_risk_rows']:
        if r['security_id'] in selected:r['risk_chain']='synthetic_one_chain'
    task['task_id']=m.digest({k:v for k,v in task.items() if k!='task_id'})
    result['risk_chains_by_security']={s:'synthetic_one_chain' for s in selected}
    result['declared_constraint_checks']['RISK_CHAIN_TOP1_WEIGHT']=False;result['declared_constraints_passed']=False
    frame=copy.deepcopy(args['inputs']['prices']['returns']);frame['index']=frame['index'][:126];frame['data']=frame['data'][:126]
    detail=m.pure.scalar.inspect_result(result,task,dict(returns=frame))
    prepared=m.independent_binding(args['inputs'],task,result,args['numerical_sources'],detail)
    folder=Path('data/cache/research/test_only_account_prefix').resolve();identifier=task['task_id']
    ref=lambda name,h:dict(path=str(folder/identifier/name),sha256=h*64)
    auditref=ref('audit.json','d');fitref=ref('fit.json','e')
    entry=dict(task_id=identifier,started_reference=ref('started.json','a'),raw_reference=None,result_reference=ref('result.json','b'))
    base={str(folder/'base.py'):'f'*64};sources=dict(base);sources[entry['started_reference']['path']]=entry['started_reference']['sha256']
    marker=dict(schema='HISTORICAL_CROSS_K_ACCOUNT_ATTEMPT_V1',task_id=identifier,plan_reference=m.PLAN,fit_prefix_audit_reference=auditref,fit_checkpoint_reference=fitref,attempt_count=1,runtime=m.prefix.runtime())
    saved=dict(schema='HISTORICAL_CROSS_K_CANDIDATE_ACCOUNT_V1',task_id=identifier,plan_reference=m.PLAN,fit_prefix_audit_reference=auditref,fit_checkpoint_reference=fitref,
        started_reference=entry['started_reference'],raw_reference=None,parameter_digest=m.digest(prepared),status='SKIPPED_RISK',failed_original_risk_checks=['RISK_CHAIN_TOP1_WEIGHT'],arguments=None,execution=None,independent_decimal_accounting=None,execution_performed=False,
        historical_expected_source_hashes=sources,source_partition_verified_at_invocation_start=True,**dict.fromkeys(m.FALSE,False))
    return (entry,dict(started=marker,raw=None,result=saved),task,result,detail,auditref,base,args['inputs'],args['numerical_sources'],None,None)


class SourceAccountReaderTests(unittest.TestCase):
    def test_independent_binding_matches_pure_binder_under_actual_declared_inputs(self):
        from backtest import ndx_historical_cross_k_account_arguments_research as binder
        args=fixture();inputs={k:args[k] for k in ('inputs','task','result','numerical_sources','audited_detail')}
        actual=m.independent_binding(*inputs.values());expected=binder.prepare_candidate_arguments(**inputs)
        from scripts.ndx_historical_single_window_accounts_20260920 import encode
        self.assertTrue(m.exact(actual,encode(expected)))

    def test_skipped_risk_kept_and_fake_execution_source_claims_rejected(self):
        args=skipped_fixture();report=m.inspect_entry(*args)
        self.assertEqual(report['status'],'SKIPPED_RISK');self.assertIsNone(report['independent_result']['comparison'])
        for defect in ('marker','source','execute','raw','parameter','scope'):
            changed=list(copy.deepcopy(args));entry,docs=changed[:2]
            if defect=='marker':docs['started']['attempt_count']=True
            elif defect=='source':docs['result']['historical_expected_source_hashes']={}
            elif defect=='execute':docs['result']['execution']={}
            elif defect=='raw':entry['raw_reference']={'path':'fake','sha256':'a'*64};docs['raw']={}
            elif defect=='parameter':docs['result']['parameter_digest']='0'*64
            else:docs['result']['promotion_allowed']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect_entry(*changed)

    def test_index_denominator_and_external_account_not_imported(self):
        args=skipped_fixture();entry=args[0];folder=str(Path(entry['started_reference']['path']).parent.parent);required=dict(args[6])
        for key in ('started_reference','result_reference'):required[entry[key]['path']]=entry[key]['sha256']
        queue=[dict(task_id=entry['task_id'])]
        value=dict(schema='HISTORICAL_CROSS_K_CANDIDATE_ACCOUNT_INDEX_V1',plan_reference=m.PLAN,fit_prefix_audit_reference=args[5],folder=folder,audited_fit_task_count=1,completed_account_task_count=1,pending_account_task_count=0,entries=[entry],
            finalized_after_full_source_verification=True,external_completed_account_reference=m.EXTERNAL,external_account_imported=False,historical_expected_source_hashes=required,archive_resolution={},**dict.fromkeys(m.FALSE,False))
        m.validate_index(value,queue,dict(args[6]))
        for key,new in (('external_account_imported',True),('completed_account_task_count',True),('finalized_after_full_source_verification',1)):
            altered=copy.deepcopy(value);altered[key]=new
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_index(altered,queue,dict(args[6]))

    def test_no_actual_index_or_confirmation_fails_closed(self):
        with self.assertRaises(ValueError):m.build('not-present','0'*64)
        with patch.object(m,'RUNNER_SHA',None),self.assertRaisesRegex(ValueError,'Await'):m.build('not-present','0'*64,completed_prefix_confirmed=True)


if __name__=='__main__':unittest.main()

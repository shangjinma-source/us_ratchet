from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_dated_account_independent_readback_20261003 as core


def fixture():
    refs={k:dict(path=k+'.json',sha256='a'*64) for k in ('started','raw','inputs','publication','input_audit')}
    identity=dict(cutoff='2026-03-20',requested_previous_target_weights=None)
    tid=core.sha(core.enc(identity));task=dict(numerical_identity=identity,numerical_task_id=tid)
    candidate={'schedule':[{'targets':{'sid':{'target_weight':1.0}}}]}
    keys=('matrices','schedule','risk_chains_by_decision','corporate_actions','initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps','valuation_end_date','external_cashflows','initial_holdings','risk_parameters')
    incumbent=dict.fromkeys(keys,None)
    shared=dict(account=incumbent,original_control=[],calendar=['2026-03-20'])
    shared_id=core.sha(core.enc(shared))
    permissions=dict.fromkeys(('fit_performed','point_in_time_verified','promotion_allowed','execution_authorized','retry_allowed','independent_accounting_readback_performed'),False)
    state=dict(track='candidate',numerical_task_id=tid,runtime={},source_hashes={str(core.RUNNER):core.RUNNER_SHA},account=candidate,original_task=task,task_reference={},calendar=shared['calendar'],candidate_normalization_evidence={},common_incumbent_definition=shared,common_incumbent_identity=shared_id,blocked_nonpositive=False,**permissions)
    state.update(inputs_reference=refs['inputs'],publication_reference=refs['publication'],input_readback_reference=refs['input_audit'])
    started=dict(schema='DATED_ACCOUNT_STARTED_V1',state=state,planned_engine_call_count=1,**permissions)
    raw=dict(schema='DATED_ACCOUNT_RAW_V1',started_reference=refs['started'],runtime={},source_hashes=state['source_hashes'],engine_call_attempt_count=1,returned_account_count=1,status='ACCOUNT_RETURNED',account={'source_hashes':{str(core.ROOT/k):h for k,h in core.ENGINE.items()}},error=None,**permissions)
    post=dict(schema='DATED_ACCOUNT_POSTCHECK_V1',track='candidate',numerical_task_id=tid,started_reference=refs['started'],raw_reference=refs['raw'],common_incumbent_identity=shared_id,status='ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING',error=None,**permissions)
    flags=dict(point_in_time_verified=False,promotion_allowed=False,account_executed=False)
    inputs=dict(schema='DATED_ACCOUNT_INPUT_DOCUMENT_V1',source_hashes={},task_reference={},inputs=dict(candidate=candidate,incumbent=incumbent,original_task=task,calendar=shared['calendar'],candidate_engine_normalization_evidence={},original_incumbent_definition=[]),**flags)
    publication=dict(schema='DATED_ACCOUNT_INPUT_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED',inputs_reference=refs['inputs'],source_hashes={},**flags)
    audit=dict(schema='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=core.INPUT_READER_SHA,source_hashes={str(core.INPUT_READER):core.INPUT_READER_SHA},inputs_reference=refs['inputs'],publication_reference=refs['publication'],**flags)
    control=dict(schema='DATED_FIRST_ACCOUNTS_INDEPENDENT_ACCOUNTING_READBACK_V1',status='PASS',rows=[{},dict(track='incumbent',status='PASS',common_incumbent_identity=shared_id)])
    control['rows'][0]['track']='candidate'
    return [tid,post,raw,started,inputs,publication,audit,control,refs]


class Tests(unittest.TestCase):
    def test_links_permissions_counts_and_control(self):
        args=fixture();self.assertEqual(core.validate_evidence(*args)[0],'ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING')
        for index,key,value in [(1,'raw_reference',{}),(2,'returned_account_count',True),(5,'account_executed',True),(6,'reader_sha256','b'*64)]:
            bad=deepcopy(args);bad[index][key]=value
            with self.assertRaises(ValueError):core.validate_evidence(*bad)
        bad=deepcopy(args);bad[7]['rows'][1]['common_incumbent_identity']='b'*64
        with self.assertRaises(ValueError):core.validate_evidence(*bad)

    def test_exception_validation_and_zero_no_dispatch(self):
        args=fixture();args[2].update(status='ACCOUNT_EXCEPTION',account=None,error={'type':'Synthetic'},returned_account_count=0)
        args[1].update(status='ACCOUNT_EXCEPTION_NO_RETURNED_RESULT',error={'type':'Synthetic'})
        self.assertEqual(core.validate_evidence(*args)[0],'ACCOUNT_EXCEPTION_NO_RETURNED_RESULT')
        args[1].update(status='VALIDATION_FAILURE_RECORDED',error={'type':'SourceDrift'})
        self.assertEqual(core.validate_evidence(*args)[0],'VALIDATION_FAILURE_RECORDED')
        args=fixture();args[2]['account']=None
        with self.assertRaises(ValueError):core.validate_evidence(*args)
        args=fixture();args[3]['state']['account']['schedule'][0]['targets']['sid']['target_weight']=0
        args[3]['state']['blocked_nonpositive']=True;args[3]['planned_engine_call_count']=0
        args[2].update(status='NOT_EXECUTED_NONPOSITIVE_TARGET',account=None,error=None,returned_account_count=0,engine_call_attempt_count=0)
        args[1]['status']='NOT_EXECUTED_NONPOSITIVE_TARGET'
        self.assertEqual(core.validate_evidence(*args)[0],'NOT_EXECUTED_NONPOSITIVE_TARGET')

    def test_no_retry_and_source_conflict(self):
        with self.assertRaises(ValueError):core.readback(core.FIRST_TASK,{},execute=True)
        with self.assertRaises(ValueError):core.readback('a'*64,{},execute=1)
        with self.assertRaises(ValueError):core.guard({str(core.SOURCE):'a'*64})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/('a'*64);folder.mkdir();(folder/'independent_accounting.json').write_text('{}')
            with patch.object(core,'ATTEMPTS',root),patch.object(core,'guard') as guard:
                with self.assertRaises(ValueError):core.readback('a'*64,dict(path=str(folder/'postcheck.json'),sha256='b'*64),execute=True)
                guard.assert_not_called()

if __name__=='__main__':unittest.main()

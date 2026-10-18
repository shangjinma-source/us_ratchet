import copy
import json
from pathlib import Path
import unittest
from scripts import ndx_single_window_account_comparison_20260920 as m


def fixture(track='candidate'):
    load=lambda p:json.loads(Path(p).read_bytes())
    inputs=load(m.INPUT['path']);target=load(m.TARGET['path']);audit=load(m.TARGET_AUDIT['path'])
    folder=m.ACCOUNT_BASE/track
    value=load(folder/'account.json');raw=load(folder/'raw_execution.json');started=load(folder/'started.json')
    return value,raw,started,m.reconstruct(inputs,target,track),m.owner_sources(inputs,target,audit),value['archive_resolution']


def recovery_fixture():
    args=list(fixture());value,_,_,_,sources,partition=args
    load=lambda p:json.loads(Path(p).read_bytes())
    inputs=load(m.INPUT['path']);target=load(m.TARGET['path'])
    state=m.reconstruct(inputs,target,'incumbent');selected=state['selected']
    raw=load(m.CONTROL_REFS['raw']['path']);started=load(m.CONTROL_REFS['started']['path'])
    execution=m.restored_ledger(raw['execution'],selected['columns'],selected['labels'])
    audit=m.control_oracle_v2.audit(execution=execution,calendar=state['calendar'],schedule=state['effective_schedule'],prices=selected['prices'],risk_chains_by_decision=selected['arguments']['risk_chains_by_decision'],contract=m.CONTRACT)
    value.update(schema='HISTORICAL_SINGLE_WINDOW_CONDITIONAL_ACCOUNT_RAW_RECOVERY_V2',track='incumbent',execution=execution,independent_decimal_accounting=audit,
        schedule=selected['original_schedule'],effective_schedule=state['effective_schedule'],normalization_evidence=state['normalization_evidence'],internal_columns=selected['columns'],
        started_reference=m.CONTROL_REFS['started'],raw_execution_reference=m.CONTROL_REFS['raw'],prepared_sha256=started['prepared_sha256'],risk_is_order_gate=False,
        original_execution_source_hashes=sources,recovery_failure_reference=m.CONTROL_REFS['failure'],read_only_raw_recovery=True,execution_replayed=False)
    return value,raw,started,state,sources,partition,dict(sources=sources,partition=partition)


class ComparisonTests(unittest.TestCase):
    def test_saved_rejected_candidate_cash_ledger_independently_verified(self):
        args=fixture();result=m.inspect(*args)
        self.assertIsInstance(result,dict)
        self.assertEqual(args[0]['execution']['trades'],[])
        self.assertTrue(all(row['total_value_usd']==25000 for row in args[0]['execution']['daily']))
        self.assertEqual(len(args[3]['calendar']),127)

    def test_tampered_amount_source_flags_and_marker_rejected(self):
        for defect in ('cash','source','scope','marker','normalization','riskgate'):
            args=list(copy.deepcopy(fixture()));value,raw,started,state,sources,partition=args
            if defect=='cash':value['execution']['daily'][20]['total_value_usd']=25001
            elif defect=='source':value['historical_expected_source_hashes'].pop(next(iter(value['historical_expected_source_hashes'])))
            elif defect=='scope':value['promotion_allowed']=True
            elif defect=='marker':started['attempt_count']=True
            elif defect=='normalization':value['effective_schedule'][0]['targets'][next(iter(state['selected']['labels']))]['target_weight']+=1e-10
            else:value['risk_is_order_gate']=False
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect(*args)

    def test_raw_ticker_only_and_unsupported_claim_rejected(self):
        args=list(fixture());raw=args[1];raw['execution']['decisions'][0]['targets'][next(iter(args[3]['selected']['labels']))]['ticker']='FABRICATED'
        with self.assertRaises(ValueError):m.inspect(*args)
        args=list(fixture());args[1]['independent_accounting_completed']=True
        with self.assertRaises(ValueError):m.inspect(*args)

    def test_unsealed_other_account_fails_closed(self):
        from unittest.mock import patch
        with patch.object(m,'ACCOUNT_SHA',{'candidate':'0'*64,'incumbent':None}):
            with self.assertRaisesRegex(ValueError,'Await'):m.build()

    def test_actual_control_raw_without_reexecution_and_recovery_scope(self):
        args=recovery_fixture();result=m.inspect(*args)
        self.assertFalse(result['engine_called']);self.assertFalse(result['risk_is_order_gate'])
        self.assertEqual(len(args[0]['execution']['daily']),127)
        for key,value in (('execution_replayed',True),('read_only_raw_recovery',False),('original_execution_source_hashes',{})):
            changed=list(copy.deepcopy(args));changed[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.inspect(*changed)


if __name__=='__main__':unittest.main()

import copy
import json
import unittest
from decimal import Decimal
from scripts import ndx_two_period_account_comparison_20260919 as m


def fixture():
    docs={k:json.loads((m.BASE/p).read_bytes()) for k,(p,h) in m.BOUND.items()}
    target=docs['target']['result'];price=docs['prices'];identities=docs['identity'];calendar=price['calendar']
    # Synthetic NO_PLAN account: no execution engine, no feasibility claim.
    normalized,evidence=m.normalization.normalized_schedule(target['schedule'])
    decisions=[]
    for row in normalized:
        day=row['decision_date'];names=row['targets']
        decisions.append(dict(**copy.deepcopy(row),status='NO_PLAN',shares_before={},cash_before_usd=25000,
            target_k=len(names),prices={sid:price['matrices']['close'][day][t['ticker']] for sid,t in names.items()},
            risk_chains={sid:target['risk_chains_by_decision'][day][sid] for sid in names},
            risk_chain_observation_dates={sid:day for sid in names}))
    execution=dict(corporate_actions=[],identity_events=[],dividend_modelled=False,
        execution_policy='DECISION_CLOSE_FROZEN_DELTA_NEXT_COMMON_SESSION_OPEN_ATOMIC_BASKET',
        decisions=decisions,executions=[],trades=[],daily=[dict(session=d,shares={},tickers={},prices={},cash_usd=25000,
            total_value_usd=25000,risk={'checks':{'ALL_CASH':False},'all_passed':False},risk_chains={},risk_chain_observation_dates={}) for d in calendar],
        summary=dict(terminal_value_usd=25000,path_return_net=0,path_max_drawdown=0,session_count=21,all_cash_session_count=21,
            k_path=[len(r['targets']) for r in target['schedule']]))
    candidate=dict(schema='TWO_PERIOD_CONDITIONAL_FROZEN_ACCOUNT_V2',calendar=calendar,schedule=target['schedule'],normalized_schedule=normalized,normalization_evidence=evidence,execution_contract=m.CONTRACT,
        execution=execution,internal_columns={r['security_id']:'SID_'+r['subject_cik']+'_'+r['cusip'] for r in identities['rows']},execution_performed=True,
        **dict.fromkeys(('fit_performed','legacy_identity_bridge_called','frozen_engine_source_modified','additional_cash_flows_supported',
            'dividend_cash_flows_modelled','continuous_identity_interval_verified','provider_binding_verified','corporate_action_completeness_verified',
            'point_in_time_verified','promotion_allowed'),False))
    candidate['independent_decimal_accounting']=dict(schema='ACTION_FREE_FROZEN_ACCOUNT_DECIMAL_AUDIT_V1',session_count=21,decision_count=2,
        execution_count=0,rejected_count=0,trade_count=0,fees_usd='0',terminal_cash_usd='25000',terminal_value_usd='25000',terminal_shares={},
        engine_called=False,integer_optimizer_independently_recomputed=False,corporate_actions_supported=False,source_authenticity_verified=False,
        point_in_time_verified=False,promotion_allowed=False)
    return candidate,target,price,identities,docs['prefix']


class Tests(unittest.TestCase):
    def test_synthetic_no_plan_account_and_sealed_same_clock_references(self):
        c,t,p,i,prefix=fixture();audit,metrics=m.audit_account(c,t,p,i)
        self.assertEqual(audit['execution_count'],0)
        report=m.compare(prefix,c['calendar'],metrics)
        self.assertEqual(Decimal(report['candidate']['path_return']),0)
        self.assertEqual(len(report['references']),2)

    def test_embedded_audit_does_not_hide_bad_actual_cash(self):
        c,t,p,i,_=fixture();c['execution']['daily'][5]['cash_usd']=24999
        with self.assertRaises(ValueError):m.audit_account(c,t,p,i)

    def test_normalization_exact_and_raw_receipt_cannot_be_rewritten(self):
        c,t,p,i,_=fixture();c['normalized_schedule']=copy.deepcopy(c['schedule'])
        with self.assertRaises(ValueError):m.audit_account(c,t,p,i)
        c,t,p,i,_=fixture();c['started_attempt']={'path':'fixture','sha256':'a'*64};c['historical_expected_source_hashes']={}
        raw=copy.deepcopy(c['execution'])
        for row in raw['decisions']:
            for sid,value in row['targets'].items():value['ticker']=c['internal_columns'][sid]
        receipt=dict(schema='TWO_PERIOD_RAW_EXECUTION_RECEIPT_V2',execution=raw,original_schedule=c['schedule'],calendar=c['calendar'],
            execution_contract=c['execution_contract'],internal_columns=c['internal_columns'],started_attempt=c['started_attempt'],
            historical_expected_source_hashes={},independent_accounting_completed=False,point_in_time_verified=False,promotion_allowed=False)
        m.audit_raw_receipt(c,receipt,i)
        receipt['execution']['daily'][3]['cash_usd']+=1
        with self.assertRaises(ValueError):m.audit_raw_receipt(c,receipt,i)
        c,t,p,i,_=fixture();c['independent_decimal_accounting']['execution_count']=2
        with self.assertRaises(ValueError):m.audit_account(c,t,p,i)

    def test_clock_contract_identity_and_price_matrix_reject(self):
        for kind in ('contract','clock','identity','price','scope'):
            c,t,p,i,_=fixture();c,t,p,i=copy.deepcopy((c,t,p,i))
            if kind=='contract':c['execution_contract']['initial_cash_usd']=5000
            if kind=='clock':c['schedule'][1]['execution_date']='2023-05-02'
            if kind=='identity':i['rows'][0]['ticker']='OTHER'
            if kind=='price':p['matrices']['open'].pop(c['calendar'][0])
            if kind=='scope':c['provider_binding_verified']=True
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.audit_account(c,t,p,i)

    def test_metrics_interval_drawdown_and_benchmark_tampering(self):
        values=[100,80]+[110]*19;metric=m.metrics(values)
        self.assertEqual(Decimal(metric['path_return']),Decimal('.1'))
        self.assertEqual(Decimal(metric['path_max_drawdown']),Decimal('.2'))
        self.assertGreater(Decimal(metric['annualized_return_252_over_20']),2)
        with self.assertRaises(ValueError):m.metrics([100]*20)
        c,_,_,_,prefix=fixture();prefix['nav']['rows'][-1]['equity_index']+=.01
        with self.assertRaises(ValueError):m.compare(prefix,c['calendar'],metric)


if __name__=='__main__':unittest.main()

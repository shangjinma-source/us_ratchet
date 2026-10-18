"""Only synthetic ledgers and mocked accounting; no actual comparison build."""
from copy import deepcopy
from decimal import Context,Decimal,localcontext,Inexact,ROUND_UP
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_legacy_six_period_account_comparison_20260923 as m
from test_ndx_drawdown_six_period_account_comparison_20260923 import history_fixture


def candidate_fixture():
    docs={role:json.loads((m.BASE/m.BOUND[role][0]).read_bytes()) for role in ('schedule','price','identity','lane')}
    schedule,price,identity=(docs[k] for k in ('schedule','price','identity'))
    labels={r['security_id']:r for r in identity['rows']};calendar=price['calendar'];conversion=[]
    normalized,evidence=m.normalization.normalized_schedule(schedule['schedule'])
    for kind in ('open','close'):
        for day in calendar:
            for sid,label in labels.items():
                value=price['matrices'][kind][day][label['ticker']]
                with localcontext(Context(prec=160)):error=abs(Decimal.from_float(float(value))-Decimal(value))
                conversion.append(dict(session=day,security_id=sid,field=kind,original_decimal=value,
                    execution_float=float(value),absolute_binary_float_error=str(error)))
    candidate=dict(calendar=calendar,schedule=schedule['schedule'],security_count=12,distinct_issuer_count=11,fixed_security_count_policy=False,
        per_decision_target_counts=[4,4,4,4,6,4],execution_contract=m.CONTRACT,normalized_schedule=normalized,normalization_evidence=evidence,
        risk_chain_evidence={},independent_decimal_accounting={'synthetic':True},execution=dict(daily=[{'total_value_usd':25000} for _ in calendar],
            corporate_actions=[],identity_events=[],dividend_modelled=False),action_free_assumption=dict(dividend_events_retained_in_price_source=True,
            dividends_added_to_cash=False,identity_class_conversion_assumed=False,
            description='CONDITIONAL_ACTION_FREE_LEDGER_DESPITE_RETURNED_DIVIDEND_EVENTS',price_reference=m.reference('price')),
        price_conversion_evidence=dict(policy='EXPLICIT_FLOAT_ONLY_AT_FROZEN_ENGINE_BOUNDARY_DECIMAL_MARKS_RETAINED_FOR_INDEPENDENT_AUDIT',
            cell_count=2568,cells=conversion))
    return candidate,docs


class ComparisonTests(unittest.TestCase):
    def test_candidate_normalizes_and_accounts_once_with_decimal_marks(self):
        candidate,docs=candidate_fixture()
        with patch.object(m,'independent_risk_history',return_value=({}, {'cutoff_evidence':{}})), \
                patch.object(m.normalization,'normalized_schedule',wraps=m.normalization.normalized_schedule) as norm, \
                patch.object(m.accounting,'audit',return_value={'synthetic':True}) as audit:
            m.audit_candidate(candidate,docs['schedule'],docs['price'],docs['identity'],docs['lane'])
            self.assertEqual(norm.call_count,1);self.assertEqual(audit.call_count,1)
            self.assertEqual(sum(len(row)*2 for row in audit.call_args.kwargs['prices'].values()),2568)
            self.assertTrue(all(isinstance(row['close'],Decimal) for day in audit.call_args.kwargs['prices'].values() for row in day.values()))

    def test_class_sid_same_issuer_not_rename_and_false_cash_dividend_rejected(self):
        for attack in ('class','dividend','assumption','counts','future_identity'):
            candidate,docs=candidate_fixture()
            if attack=='class':next(row for row in docs['identity']['rows'] if row['ticker']=='GOOGL')['security_id']='security:0001652044:02079K107'
            if attack=='dividend':candidate['execution']['corporate_actions']=[{'type':'DIVIDEND'}]
            if attack=='assumption':candidate['action_free_assumption']['dividends_added_to_cash']=True
            if attack=='counts':candidate['per_decision_target_counts']=[4]*6
            if attack=='future_identity':docs['identity']['enph_original_conditional_window']['end']='2023-09-01'
            with self.subTest(attack=attack),patch.object(m.accounting,'audit') as audit:
                with self.assertRaises(ValueError):m.audit_candidate(candidate,docs['schedule'],docs['price'],docs['identity'],docs['lane'])
                audit.assert_not_called()

    def test_risk_dates_preserve_old_holdings_and_counts_are_derived(self):
        schedule,identity,execution=history_fixture()
        _,report=m.independent_risk_history(schedule,identity,execution)
        self.assertEqual((report['decision_count'],report['execution_count'],report['no_plan_count']),(6,4,2))
        execution['executions']=[]
        for row in execution['decisions']:row['status']='NO_PLAN'
        _,report=m.independent_risk_history(schedule,identity,execution)
        self.assertEqual((report['execution_count'],report['no_plan_count']),(0,6))
        execution['daily'][-1]['risk_chain_observation_dates']['S0']=m.CLOCK[-1][0]
        with self.assertRaises(ValueError):m.independent_risk_history(schedule,identity,execution)

    def test_saved_lane_risk_not_replaceable_by_alias(self):
        candidate,docs=candidate_fixture()
        chosen=docs['identity']['saved_lane_choices'][3]['saved_candidate']
        sid='security:0001652044:02079K107';chosen['selected'][sid]['ticker']='GOOGL'
        with self.assertRaises(ValueError):m.audit_candidate(candidate,docs['schedule'],docs['price'],docs['identity'],docs['lane'])

    def test_external_pins_fixed_namespace_and_decimal_context(self):
        with patch.object(m,'current_source_guard') as guard:
            with self.assertRaises(ValueError):m.build(m.ACCOUNT_DIRECTORY/'account.json','0'*64,m.PRODUCER_SHA)
            guard.assert_not_called()
        with self.assertRaises(ValueError):m.publish({},m.OUTPUT.with_name('other.json'))
        values=['100.123']*106+['105.567'];expected=m.metrics(values)
        with localcontext() as context:
            context.prec=2;context.rounding=ROUND_UP;context.traps[Inexact]=True
            self.assertEqual(m.metrics(values),expected)
        for value in ([1]*295,[True]*107,[float('nan')]*107):
            with self.assertRaises(ValueError):m.metrics(value)


if __name__=='__main__':unittest.main()

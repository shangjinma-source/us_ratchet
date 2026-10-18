from decimal import localcontext,Inexact,Rounded,ROUND_UP
import ast
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from scripts import ndx_drawdown_six_period_account_comparison_20260923 as m
import test_ndx_drawdown_six_period_account_comparison_20260923 as fixture


class IndependentReview(unittest.TestCase):
    def test_different_execution_denominators_are_derived(self):
        schedule,projection,execution=fixture.history_fixture()
        execution['executions']=[]
        for row in execution['decisions']:row['status']='NO_PLAN'
        _,result=m.independent_risk_history(schedule,projection,execution)
        self.assertEqual((result['decision_count'],result['execution_count'],result['no_plan_count']),(6,0,6))
        for row in execution['decisions']:
            row['status']='FROZEN'
            execution['executions'].append(dict(session=row['execution_date'],status='FILLED'))
        _,result=m.independent_risk_history(schedule,projection,execution)
        self.assertEqual((result['execution_count'],result['filled_execution_count'],result['no_plan_count']),(6,6,0))

    def test_enph_split_chain_or_window_upgrade_rejected_before_audit(self):
        schedule=json.loads((m.BASE/m.BOUND['schedule'][0]).read_bytes())
        projection=json.loads((m.BASE/m.BOUND['assembly'][0]).read_bytes())
        candidate=dict(calendar=projection['calendar'],schedule=schedule['schedule'])
        for attack in ('split','window','identity'):
            bad=deepcopy(projection)
            if attack=='split':
                for row in bad['saved_lane_choices']:
                    row['saved_candidate']['selected']['security:0001463101:29355A107']['risk_chain']='independent_enph'
            elif attack=='window':bad['identity_projection']['enph_original_interval_certification_extended']=True
            else:
                next(row for row in bad['identity_projection']['rows'] if row['ticker']=='ENPH')['issuer_id']='issuer:fake'
            with self.subTest(attack=attack),patch.object(m.accounting,'audit') as audit:
                with self.assertRaises(ValueError):m.audit_candidate(candidate,schedule,bad)
                audit.assert_not_called()

    def test_frozen_producer_constants_match_without_import(self):
        tree=ast.parse(m.PRODUCER.read_text(encoding='utf-8'))
        constants={}
        for node in tree.body:
            if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
                if node.targets[0].id in ('BOUND','FROZEN'):constants[node.targets[0].id]=ast.literal_eval(node.value)
        self.assertEqual(constants['BOUND'],m.BOUND)
        expected={str(m.ROOT/'backtest'/name):sha for name,sha in constants['FROZEN'].items()}
        self.assertEqual(expected,{**m.ENGINE_SOURCES,**m.FROZEN})

    def test_no_plan_cannot_be_counted_as_rejection(self):
        schedule,projection,execution=fixture.history_fixture()
        _,result=m.independent_risk_history(schedule,projection,execution)
        self.assertEqual((result['decision_count'],result['execution_count'],result['no_plan_count'],result['rejected_execution_count']),(6,4,2,3))
        execution['decisions'][2]['status']='REJECTED'
        with self.assertRaises(ValueError):m.independent_risk_history(schedule,projection,execution)

    def test_last_selected_label_cannot_use_future_reclassification(self):
        schedule,projection,execution=fixture.history_fixture()
        day=m.CLOCK[-1][0]
        projection['saved_lane_choices'][-1]['saved_candidate']['selected']['S1']['risk_chain']='changed-later'
        projection['selected_risk_chains_by_decision'][day]['S1']='changed-later'
        schedule['risk_chains_by_decision'][day]['S1']='changed-later'
        execution['decisions'][-1]['risk_chains']['S1']='changed-later'
        m.independent_risk_history(schedule,projection,execution)
        execution['decisions'][1]['risk_chains']['S1']='changed-later'
        with self.assertRaises(ValueError):m.independent_risk_history(schedule,projection,execution)

    def test_duplicate_or_missing_frozen_execution_is_not_silently_counted(self):
        for mode in ('duplicate','missing','cash'):
            schedule,projection,execution=fixture.history_fixture()
            if mode=='duplicate':execution['executions'].append(execution['executions'][-1])
            elif mode=='missing':execution['executions'].pop()
            else:execution['executions'][-1]['cash_after_usd']=101
            with self.assertRaises(ValueError):m.independent_risk_history(schedule,projection,execution)

    def test_external_pins_and_decimal_context_fail_closed(self):
        with patch.object(m.archive,'strict') as strict:
            with self.assertRaises(ValueError):m.build('unused','0'*64,m.PRODUCER_SHA)
            strict.assert_not_called()
        values=['100.123']*106+['112.345'];expected=m.metrics(values)
        with localcontext() as context:
            context.prec=2;context.rounding=ROUND_UP;context.traps[Inexact]=True;context.traps[Rounded]=True
            self.assertEqual(m.metrics(values),expected)


if __name__=='__main__':unittest.main()

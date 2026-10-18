from copy import deepcopy
from decimal import Inexact,localcontext
from fractions import Fraction
from pathlib import Path
from unittest import mock
import unittest
from scripts import ndx_cash_topup_neighbor_single_evaluation_independent_readback_20261003 as m

def fixture():
    r=dict(scenario_id='tiny',cash_event=dict(decision_date='2023-04-28',execution_date='2023-05-01',amount_usd='100'),starting_cash_usd='100',holdings={s:10 for s in 'ABCD'},execution_prices={s:'10' for s in 'ABCD'},securities={s:dict(issuer_id=s,risk_chain=s) for s in 'ABCD'},risk_parameters=dict(zip(m.RISK_KEYS,('.45','.05','.8','.7','.55'))),transaction_cost_bps='10',minimum_cash_buffer_usd='100',target_weights={s:'0.20' for s in 'ABCD'})
    a={k:deepcopy(v) for k,v in r.items() if k not in ('scenario_id','target_weights')};a.update(branches=[dict(branch_id='tiny',buy_limits={s:3 for s in 'ABCD'})],max_evaluations=1)
    args=dict(evaluation_inputs=a,plans_by_branch={'tiny':[dict(A=0,B=1,C=1,D=1)]})
    return r,args

def documents(error=False,validation=False):
    r,args=fixture();flags=dict.fromkeys(m.FLAGS,False);tid='a'*64
    start=dict(schema='CASH_TOPUP_SINGLE_EVALUATION_STARTED_V1',task_id=tid,source_hashes={},evaluation_arguments=args,original_contract={'contract':{'original_input_row':r}},**flags)
    result=None if error else m.independent_result(args)
    raw=dict(schema='CASH_TOPUP_SINGLE_EVALUATION_RAW_V1',task_id=tid,source_hashes={},explicit_evaluator_call_attempt_count=1,returned_evaluation_count=0 if error else 1,result=result,error={'type':'RuntimeError','message':'failed'} if error else None,**flags)
    outcome='VALIDATION_FAILURE' if validation else 'EVALUATION_EXCEPTION' if error else 'FEASIBLE'
    post=dict(schema='CASH_TOPUP_SINGLE_EVALUATION_POSTCHECK_V1',task_id=tid,source_hashes={},evaluation_error=raw['error'],validation_error={'type':'ValueError','message':'drift'} if validation else None,outcome=outcome,original_target_stock_weight_l1=None if error or validation else dict(distance=dict(numerator=3,denominator=86),fees_usd=dict(numerator=3,denominator=100)),score_absence_reason='UNACCEPTED_RETURNED_EVALUATION' if validation else 'NO_RETURNED_EVALUATION' if error else None,status='TECHNICAL_FAILURE_NOT_INFEASIBILITY' if error or validation else 'ACCEPTED_SINGLE_PLAN_DIAGNOSTIC',**flags)
    return start,raw,post

class Tests(unittest.TestCase):
    def test_known_exact_money_and_l1_hostilecontext(self):
        start,raw,post=documents()
        with localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True
            result=m.inspect_saved(start,raw,post)
        self.assertEqual(result['attempt_outcome'],'FEASIBLE');p=raw['result']['branches'][0]['evaluated_plans'][0]
        self.assertEqual(p['gross_buy_usd'],'30');self.assertEqual(p['fees_usd'],'0.03');self.assertEqual(p['cash_after_usd'],'169.97');self.assertEqual(p['cash_flow_adjusted_pnl_usd'],'-0.03')
        self.assertEqual(p['risk']['weights']['A'],'10/43');self.assertEqual(p['risk']['effective_n'],str(Fraction(1849,463)));self.assertEqual(p['proposed_holdings'],dict(A=10,B=11,C=11,D=11))
    def test_independent_tamper_checks(self):
        for kind in ('money','risk','issuer','feasible','score','count','authority'):
            s,r,p=documents();plan=r['result']['branches'][0]['evaluated_plans'][0]
            if kind=='money':plan['fees_usd']='0'
            elif kind=='risk':plan['risk']['checks']['MIN_SINGLE_WEIGHT']=False
            elif kind=='issuer':plan['issuer_conflicts']={'fake':['A','B']}
            elif kind=='feasible':plan['feasible']=1
            elif kind=='score':p['original_target_stock_weight_l1']['distance']['numerator']=0
            elif kind=='count':r['explicit_evaluator_call_attempt_count']=True
            else:p['point_in_time_verified']=0
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.inspect_saved(s,r,p)
    def test_exception_validation_not_infeasible(self):
        for error,validation in ((True,False),(False,True),(True,True)):
            s,r,p=documents(error,validation);expected=p['outcome'];self.assertEqual(m.inspect_saved(s,r,p)['attempt_outcome'],expected)
            p['outcome']='INFEASIBLE'
            with self.assertRaises(ValueError):m.inspect_saved(s,r,p)
    def test_no_cash_dilution_and_issuer_and_pending(self):
        row,args=fixture();args['evaluation_inputs']['cash_event']['amount_usd']='1000000';r=m.independent_result(args);self.assertEqual(r['branches'][0]['evaluated_plans'][0]['risk']['weights']['A'],'10/43')
        args['evaluation_inputs']['securities']['B']['issuer_id']='A';r=m.independent_result(args);self.assertFalse(r['branches'][0]['evaluated_plans'][0]['feasible']);self.assertEqual(r['branches'][0]['evaluated_plans'][0]['issuer_conflicts'],{'A':['A','B']})
        with mock.patch.object(m,'POSTCHECK_SHA',None),mock.patch.object(Path,'read_bytes',side_effect=AssertionError('No actual')):
            with self.assertRaises(ValueError):m.readback('a'*64,{},execute=True)

if __name__=='__main__':unittest.main()

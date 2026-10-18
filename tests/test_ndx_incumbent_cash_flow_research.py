from copy import deepcopy
from decimal import Inexact,localcontext
from fractions import Fraction
import unittest
from backtest import ndx_incumbent_cash_flow_research as module


def fixture(prices=None,weights=None,holdings=None,cash='100',flow='0',fee='0',buffer='0'):
    prices=prices or {'A':'10'}; weights=weights or {'A':'1'}
    return dict(initial={'session':'2023-01-02','cash_usd':cash,'holdings':holdings or {},'close_prices':prices},
        sessions=[{'session':'2023-01-03','open_prices':deepcopy(prices),'close_prices':deepcopy(prices),'cash_injection_usd':flow}],
        fixed_weights=weights,schedule=[{'decision_date':'2023-01-02','execution_date':'2023-01-03'}],
        securities={sid:{'ticker':sid,'issuer_id':sid,'risk_chain':sid} for sid in prices},
        risk_parameters={'max_single_weight':'.45','min_single_weight':'.05','top_weight_cap':'.8','minimum_effective_n_ratio':'.7','risk_chain_top1_cap':'.55'},
        transaction_cost_bps=fee,minimum_cash_buffer_usd=buffer)


class IncumbentTests(unittest.TestCase):
    def test_initial_plan_does_not_use_flow_future_plan_uses_own_state(self):
        args=fixture(flow='100'); before=deepcopy(args)
        args['sessions'] += [dict(session=day,open_prices={'A':'10'},close_prices={'A':'10'},cash_injection_usd='0') for day in ('2023-01-04','2023-01-05')]
        args['schedule'].append({'decision_date':'2023-01-04','execution_date':'2023-01-05'})
        result=module.simulate_incumbent_cash_flow(**args)
        self.assertEqual(result['decisions'][0]['desired_shares'],{'A':10})
        self.assertEqual(result['decisions'][1]['desired_shares'],{'A':20})
        self.assertEqual(result['decisions'][1]['shares_before'],{'A':10})
        self.assertEqual(result['decisions'][1]['cash_before_usd'],'100')
        self.assertEqual(result['executions'][1]['frozen_delta'],{'A':10})
        self.assertEqual(result['chained_twr'],module.ratio(Fraction(0)))
        self.assertEqual(args['initial'],before['initial'])

    def test_sell_not_external_withdrawal_and_two_sided_fees(self):
        args=fixture(prices={'A':'10','B':'10'},weights={'B':'1'},holdings={'A':10},cash='0',fee='10')
        result=module.simulate_incumbent_cash_flow(**args)
        self.assertEqual(result['executions'][0]['status'],'FILLED')
        self.assertEqual(result['executions'][0]['frozen_delta'],{'A':-10,'B':9})
        self.assertEqual(result['total_fees_usd'],'0.19')
        self.assertEqual(result['total_cash_injection_usd'],'0')
        self.assertEqual(result['chained_twr'],module.ratio(Fraction(-19,10000)))
        self.assertEqual(result['trades'][0]['signed_share_delta'],-10)
        self.assertFalse(result['trades'][0]['external_cash_flow'])

    def test_open_gap_atomic_reject_no_fee_no_replan(self):
        args=fixture(fee='10'); args['sessions'][0]['open_prices']={'A':'12'}
        result=module.simulate_incumbent_cash_flow(**args)
        execution=result['executions'][0]
        self.assertEqual(execution['status'],'REJECTED'); self.assertEqual(execution['shares_after'],{})
        self.assertEqual(execution['desired_shares'],{'A':9})
        self.assertEqual(result['total_fees_usd'],'0'); self.assertEqual(result['trades'],[])
        self.assertEqual(result['chained_twr'],module.ratio(Fraction(0)))

    def test_original_two_stage_reduction_keeps_high_price_single_slot(self):
        args=fixture(prices={'A':'100','B':'1'},weights={'A':'.5','B':'.5'},cash='200',fee='10')
        result=module.simulate_incumbent_cash_flow(**args); decision=result['decisions'][0]
        self.assertEqual(decision['original_floor_shares'],{'A':1,'B':100})
        self.assertEqual(decision['desired_shares'],{'A':1,'B':99})
        self.assertFalse(decision['projection_used'])
        self.assertEqual(decision['reductions'][0]['security_id'],'B')
        self.assertEqual(decision['reductions'][0]['stage'],'DYNAMIC_FIRST_STAGE_KEEP_ONE')
        self.assertFalse(decision['risk']['all_passed'])
        self.assertEqual(result['executions'][0]['status'],'FILLED')

    def test_zero_slot_financial_projection_and_reduction_budget(self):
        args=fixture(prices={'A':'1000','B':'.01'},weights={'A':'.0000001','B':'.9999999'},cash='100',fee='10')
        result=module.simulate_incumbent_cash_flow(**args); decision=result['decisions'][0]
        self.assertTrue(decision['projection_used']); self.assertEqual(decision['desired_shares'],{'A':0,'B':9990})
        self.assertEqual(result['daily'][0]['holdings_after'],{'A':0,'B':9990})
        self.assertEqual(result['daily'][0]['risk']['zero_share_security_ids'],['A'])
        args['max_projection_reductions']=0
        with self.assertRaisesRegex(ValueError,'ENGINEERING_REDUCTION'): module.simulate_incumbent_cash_flow(**args)

    def test_tolerance_is_not_permission_for_negative_cash(self):
        args=fixture(prices={'A':'1'},buffer='1'); args['sessions'][0]['open_prices']={'A':'1.00000000005'}
        result=module.simulate_incumbent_cash_flow(**args)
        self.assertEqual(result['executions'][0]['status'],'FILLED')
        self.assertLess(Fraction(result['executions'][0]['cash_after_usd']),1)
        args=fixture(prices={'A':'1'}); args['sessions'][0]['open_prices']={'A':'1.00000000005'}
        result=module.simulate_incumbent_cash_flow(**args)
        self.assertEqual(result['executions'][0]['status'],'REJECTED')
        self.assertIn('NONNEGATIVE_CASH',result['executions'][0]['failure_reasons'])

    def test_overnight_preserved_and_hostile_context_weights_not_normalized(self):
        args=fixture(holdings={'A':10},cash='100',flow='100',weights={'A':'1.00000000000000002'})
        args['sessions'][0]['open_prices']={'A':'20'}; args['sessions'][0]['close_prices']={'A':'20'}
        with localcontext() as context:
            context.prec=2; context.traps[Inexact]=True
            result=module.simulate_incumbent_cash_flow(**args)
        self.assertEqual(result['chained_twr'],module.ratio(Fraction(1,2)))
        self.assertEqual(result['original_fixed_weights'],args['fixed_weights']); self.assertFalse(result['weights_normalized'])
        self.assertEqual(result['daily'][0]['pre_flow_open_equity_usd'],'300')
        self.assertEqual(result['daily'][0]['post_flow_pre_fee_open_equity_usd'],'400')

    def test_strict_dates_inputs_and_no_future_execution(self):
        for change in ('bool','missing','date','weights'):
            args=fixture()
            if change=='bool': args['initial']['holdings']={'A':True}
            elif change=='missing': args['sessions'][0]['open_prices']={}
            elif change=='date': args['schedule'][0]['execution_date']='2023-01-04'
            else: args['fixed_weights']['A']='.99'
            with self.assertRaises(ValueError): module.simulate_incumbent_cash_flow(**args)


if __name__=='__main__': unittest.main()

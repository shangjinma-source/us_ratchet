from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal,Inexact,localcontext
from fractions import Fraction
import unittest
from backtest import ndx_topup_same_flow_comparison_research as module


def fixture():
    pref={'path':'synthetic/paired.json','sha256':'a'*64}; iref={'path':'synthetic/incumbent.json','sha256':'b'*64}
    flags=dict.fromkeys(('orders_executed','point_in_time_verified','promotion_allowed','dividends_modelled','corporate_actions_modelled'),False)
    paired={'schema':'OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1','scenario_count':40,'rows':[],**flags}
    inc={'schema':'INCUMBENT_SAME_FLOW_TEN_PATHS_FORTY_SCENARIOS_V1','path_count':10,'scenario_count':40,'paths':[],
         'scenario_mappings':[],'flow_policy':'FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN','risk_is_order_gate':False,**flags}
    for d in range(5):
        start=(date(2023,1,2)+timedelta(days=4*d)).isoformat()
        days=[(date.fromisoformat(start)+timedelta(days=i)).isoformat() for i in (1,2)]
        for amount in ('1000','10000'):
            pid=start+'|'+amount
            initial={'session':start,'cash_usd':'100','holdings':{'X':10},'close_prices':{'X':'10.0'}}
            rows=[{'session':day,'cash_injection_usd':amount if j==0 else '0',
                   'cumulative_twr':module.window.ratio(value),'holdings_after':{'X':10,'Z':0},'close_equity_usd':'99999'}
                  for j,(day,value) in enumerate(zip(days,(Fraction(0),Fraction(1,10))))]
            account={'schema':'SIGNED_FLOW_FROZEN_INCUMBENT_OPEN_ACCOUNT_V1','initial':deepcopy(initial),'daily':rows,
                'flow_policy':'FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN','risk_is_order_gate':False,'transaction_cost_bps':'10',
                'cash_event_timing':'AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES',
                'total_cash_injection_usd':amount,'chained_twr':module.window.ratio(Fraction(1,10)),**flags}
            inc['paths'].append({'path_id':pid,'account':account})
            for lane in module.LANES:
                index=len(paired['rows']); scenario=str(index)
                event={'decision_date':start,'execution_date':days[0],'amount_usd':amount}
                source_row={'scenario_id':scenario,'lane':lane,'cash_event':event,'transaction_cost_bps':'10','gaps':['not resolved']}
                inputref={'path':'synthetic/inputs.json','sha256':'c'*64,'json_pointer':f'/rows/{index}'}
                ci=deepcopy(initial); ci['close_prices']['X']='10'
                daily=[{'session':day,'cash_injection_usd':amount if j==0 else '0',
                        'cumulative_twr':module.window.ratio(value),'holdings_after':{'X':12,'Y':0},'close_equity_usd':'12345678'}
                       for j,(day,value) in enumerate(zip(days,(Fraction(-1,10),Fraction(1,5))))]
                candidate={'accounting_inputs':{'initial':ci,'transaction_cost_bps':'10'},
                    'account':{'schema':'BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1','rows':daily,
                        'cash_event_timing':'AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES','total_cash_injection_usd':amount,
                        'chained_twr':module.window.ratio(Fraction(1,5)),**flags}}
                paired['rows'].append({'scenario_id':scenario,'input_row':deepcopy(source_row),'input_reference':deepcopy(inputref),
                    'paths':{'candidate':candidate},'selected_plan_reference':{'synthetic':'selected'},'topup_context':{'synthetic':'preserved'}})
                inc['scenario_mappings'].append({'scenario_id':scenario,'path_id':pid,'original_input_row':deepcopy(source_row),'input_reference':deepcopy(inputref)})
    return dict(paired_accounts=paired,incumbent_accounts=inc,paired_reference=pref,incumbent_reference=iref)


class SameFlowTests(unittest.TestCase):
    def test_exact40_twr_dd_differences_refs_and_policy_asymmetry(self):
        args=fixture(); before=deepcopy(args); result=module.compare_same_flow_paths(**args)
        self.assertEqual(len(result['rows']),40); self.assertEqual(args,before)
        first=result['rows'][0]
        self.assertEqual(module.window.from_ratio(first['candidate_minus_incumbent']['cumulative_return']),Fraction(1,10))
        self.assertEqual(module.window.from_ratio(first['candidate_minus_incumbent']['maximum_drawdown']),Fraction(1,10))
        self.assertEqual(first['metrics']['candidate']['interval_count'],2)
        self.assertEqual(first['metrics']['candidate']['wealth'][0]['normalized_wealth'],module.window.ratio(Fraction(1)))
        self.assertEqual(first['observations']['candidate'][0]['source_row']['close_equity_usd'],'12345678')
        self.assertFalse(result['candidate_decision_time_executability_verified'])
        self.assertFalse(result['execution_policies_equivalent']); self.assertFalse(result['win_rate_calculated'])
        self.assertEqual(first['input_row']['gaps'],['not resolved'])

    def test_initial_cash_holdings_or_prices_different_rejected(self):
        for field,new in [('cash_usd','101'),('holdings',{'X':11}),('close_prices',{'X':'10.00000000001'})]:
            args=fixture(); args['incumbent_accounts']['paths'][0]['account']['initial'][field]=new
            with self.assertRaises(ValueError): module.compare_same_flow_paths(**args)
        args=fixture(); args['incumbent_accounts']['paths'][0]['account']['initial']['holdings']['X']=True
        with self.assertRaises(ValueError): module.compare_same_flow_paths(**args)

    def test_mapping_source_calendar_and_flow_attacks_rejected(self):
        args=fixture(); args['incumbent_accounts']['scenario_mappings'][0]['original_input_row']['gaps']=[]
        with self.assertRaisesRegex(ValueError,'scenario evidence'): module.compare_same_flow_paths(**args)
        args=fixture(); args['incumbent_accounts']['scenario_mappings'][0]['path_id']=args['incumbent_accounts']['paths'][1]['path_id']
        with self.assertRaisesRegex(ValueError,'flow coordinate'): module.compare_same_flow_paths(**args)
        args=fixture(); args['incumbent_accounts']['paths'][0]['account']['daily'].pop()
        with self.assertRaisesRegex(ValueError,'calendar'): module.compare_same_flow_paths(**args)
        args=fixture(); args['incumbent_accounts']['paths'][0]['account']['daily'][1]['cash_injection_usd']='1'
        with self.assertRaisesRegex(ValueError,'injection'): module.compare_same_flow_paths(**args)

    def test_duplicate_counts_bool_and_parent_permission_rejected(self):
        args=fixture(); args['paired_accounts']['rows'][1]=deepcopy(args['paired_accounts']['rows'][0])
        with self.assertRaises(ValueError): module.compare_same_flow_paths(**args)
        args=fixture(); args['incumbent_accounts']['path_count']=True
        with self.assertRaises(ValueError): module.compare_same_flow_paths(**args)
        args=fixture(); args['incumbent_accounts']['promotion_allowed']=True
        with self.assertRaises(ValueError): module.compare_same_flow_paths(**args)

    def test_annual_diagnostic_hostile_context_and_same_terminal_summary(self):
        args=fixture()
        with localcontext() as context:
            context.prec=2; context.traps[Inexact]=True
            result=module.compare_same_flow_paths(**args)
        first=result['rows'][0]
        with localcontext(Context(prec=80)):
            expected=Decimal(first['metrics']['candidate']['annualized_return_diagnostic_decimal'])-Decimal(first['metrics']['same_flow_incumbent']['annualized_return_diagnostic_decimal'])
        self.assertEqual(Decimal(first['candidate_minus_incumbent']['annualized_return_diagnostic_decimal']),expected)
        args['incumbent_accounts']['paths'][0]['account']['chained_twr']=module.window.ratio(Fraction(0))
        with self.assertRaisesRegex(ValueError,'Terminal TWR'): module.compare_same_flow_paths(**args)


from decimal import Context
if __name__=='__main__': unittest.main()

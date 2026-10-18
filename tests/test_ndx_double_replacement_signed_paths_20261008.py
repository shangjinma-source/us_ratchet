from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch
from backtest import ndx_double_replacement_domain_research as domain
from backtest import ndx_double_replacement_path_requests_research as requests
from backtest import ndx_signed_cash_flow_return_accounting_research as account
from backtest import ndx_signed_cash_flow_account_inspection_research as arithmetic
from scripts import ndx_double_replacement_signed_paths_independent_readback_20261008 as reader
from test_ndx_single_replacement_path_requests_research import fixture as old_fixture


def fixture():
    old=old_fixture();olds=old['old_paired_rows'];original=[]
    for row in olds:
        r=row['input_row'];r['holdings']['B']=1;r['execution_prices'].update(B='10',C='20');r['target_weights']={'C':'0.5','Z':'0.5'};r['allowed_buy_security_ids']=['C','Z']
        for sid in ('B','C'):r['securities'][sid]=dict(ticker=sid,issuer_id='issuer:'+sid,risk_chain='chain:'+sid)
        row['security_to_ticker']={k:v['ticker']for k,v in r['securities'].items()};row['topup_context']['input_row']=deepcopy(r)
        for path in row['paths'].values():
            template=path['accounting_inputs'];template['initial']['holdings']=deepcopy(r['holdings']);template['initial']['close_prices']['B']='10'
            for session in template.get('sessions',[]):
                session['open_prices'].update(B='10',C='20');session['close_prices'].update(B='10',C='20')
        original.append(dict(input_row=r,input_reference=row['input_reference']))
    contract=dict(domain.SEMANTICS,expected_scenario_ids=[x['input_row']['scenario_id']for x in original],domain_core_reference=dict(path='E:/synthetic/double.py',sha256='e'*64),action_contract_reference=dict(path='E:/synthetic/policy.json',sha256='f'*64),budget_math_reference=dict(path='E:/synthetic/math.py',sha256=domain.BUDGET_MATH_SHA256))
    prep=domain.prepare_double_replacement_domain(original,contract);rows=[]
    for i,c in enumerate(prep['document']['cases']):
        task=domain.unrank(prep,c['first_global_ordinal']);template=deepcopy(olds[i]['paths']['candidate']['accounting_inputs'])
        for j,s in enumerate(template['sessions']):s.pop('buy_shares');s['trade_shares']=deepcopy(task['signed_trade_quantities'])if j==0 else{}
        result=account.account_path(**template);first=result['rows'][0]
        evaluation=dict(status='FEASIBLE',feasible=True,gross_sell_usd=first['gross_sell_usd'],gross_buy_usd=first['gross_buy_usd'],total_fee_usd=first['fees_usd'],cash_after_usd=first['cash_after_usd'],equity_after_usd=first['post_trade_open_equity_usd'])
        chosen=dict(raw=dict(supplied_index=0,plan=dict(global_ordinal=task['global_ordinal'],task=task),status='FEASIBLE',evaluation=evaluation),locator={})
        rows.append(dict(scenario_index=i,scenario_id=c['scenario_id'],integer_count=c['integer_count'],feasible_count=1,infeasible_count=c['integer_count']-1,status='SELECTED',selected=chosen))
    selection=dict(schema='DOUBLE_REPLACEMENT_STREAM_SELECTION_V1',full_domain_selected=True,prepared_content_sha256=prep['content_sha256'],rows=rows,**{k:prep['document'][k]for k in ('scenario_count','pair_count','integer_count')},point_in_time_verified=False,account_executed=False,fit_executed=False,future_returns_used=False)
    return dict(prepared=prep,selection=selection,old_paired_rows=olds,source_references=old['source_references'])


class Tests(unittest.TestCase):
    def test_double_four_legs_full40_independent_projection_and_ledger(self):
        args=fixture();before=deepcopy(args)
        with patch.object(account,'account_path',side_effect=AssertionError('No account inside projection')):result=requests.prepare_double_replacement_path_requests(**args)
        self.assertEqual(args,before);self.assertEqual(result['new_account_request_count'],40)
        rebuilt=reader.inspect_requests(saved_requests=result,**args);self.assertEqual(rebuilt,result)
        for row in result['rows']:
            actual=account.account_path(**row['accounting_request']);self.assertEqual(arithmetic.inspect_saved_signed_account(**row['accounting_request'],saved_result=actual)['status'],'PASS');reader.inspect_first_trade(row,actual)
        self.assertEqual(result['rows'][0]['accounting_request']['sessions'][0]['trade_shares'],{'A':-10,'B':-1,'C':1,'Z':1})
        self.assertTrue(all(s['trade_shares']=={}for s in result['rows'][0]['accounting_request']['sessions'][1:]));self.assertEqual(result['rows'][0]['selection_reference']['json_pointer'],'/selection/rows/0')
    def test_no_feasible_and_missing_price_are_not_cash(self):
        args=fixture();row=args['selection']['rows'][0];row.update(status='NO_FEASIBLE',selected=None,feasible_count=0,infeasible_count=row['integer_count']);del args['old_paired_rows'][1]['paths']['candidate']['accounting_inputs']['sessions'][0]['open_prices']['C']
        result=requests.prepare_double_replacement_path_requests(**args);self.assertEqual(result['status_counts'],dict(NEW_SIGNED_PATH_REQUIRED=38,NO_FEASIBLE=1,BLOCKED_TEMPLATE_PRICE_GAP=1));reader.inspect_requests(saved_requests=result,**args)
    def test_identity_and_original_policy_tampering(self):
        args=fixture()
        for kind in ('single','sell','buybool','fee','quote','flow','order'):
            a=deepcopy(args);task=a['selection']['rows'][0]['selected']['raw']['plan']['task'];template=a['old_paired_rows'][0]['paths']['candidate']['accounting_inputs']
            if kind=='single':task['identity']['rule']='SELL_ALL_ONE_POSITIVE_OLD_BUY_ONE_NEW_INTEGER_V1'
            elif kind=='sell':task['signed_trade_quantities']['B']=0
            elif kind=='buybool':task['identity']['buy_quantities'][0]=True
            elif kind=='fee':template['transaction_cost_bps']='20'
            elif kind=='quote':template['sessions'][0]['open_prices']['C']='21'
            elif kind=='flow':template['sessions'][1]['cash_injection_usd']='1'
            else:a['selection']['rows'].reverse()
            with self.subTest(kind=kind),self.assertRaises(ValueError):requests.prepare_double_replacement_path_requests(**a)

if __name__=='__main__':unittest.main()


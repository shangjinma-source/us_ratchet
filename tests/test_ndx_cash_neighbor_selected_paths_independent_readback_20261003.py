"""Independent synthetic oracle; does not import production accounting or requests."""
from copy import deepcopy
from decimal import localcontext,Inexact
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_cash_neighbor_selected_paths_independent_readback_20261003 as m


def fixture():
    args=dict(initial=dict(session='2023-04-28',cash_usd='0',holdings={'A':10,'Z':0},close_prices={'A':'10','Z':'1'}),sessions=[dict(session='2023-05-01',open_prices={'A':'20','Z':'1'},close_prices={'A':'25','Z':'1'},cash_injection_usd='1000',buy_shares={'A':5,'Z':0})],transaction_cost_bps='10')
    ratio=lambda n,d=1:dict(numerator=str(n),denominator=str(d))
    row=dict(previous_close_session='2023-04-28',session='2023-05-01',previous_close_equity_usd='100',pre_flow_open_equity_usd='200',cash_injection_usd='1000',post_flow_pre_fee_open_equity_usd='1200',post_trade_open_equity_usd='1199.9',close_equity_usd='1274.9',gross_buy_usd='100',fees_usd='0.1',cash_after_usd='899.9',holdings_before={'A':10,'Z':0},buy_shares={'A':5,'Z':0},holdings_after={'A':15,'Z':0},overnight_pnl_usd='100',intraday_mark_pnl_before_fees_usd='75',after_flow_pnl_net_fees_usd='74.9',cash_flow_adjusted_pnl_usd='174.9',overnight_return=ratio(1),after_flow_return=ratio(749,12000),session_twr=ratio(6749,6000),cumulative_twr=ratio(6749,6000))
    account=dict(schema='BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1',rows=[row],initial_equity_usd='100',terminal_equity_usd='1274.9',total_cash_injection_usd='1000',total_fees_usd='0.1',net_dollar_pnl_excluding_injections_usd='174.9',chained_twr=ratio(6749,6000),transaction_cost_bps='10',cash_event_timing='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES',arithmetic='EXACT_RATIONAL_VALUES_FINITE_DECIMAL_MONEY_NO_FLOAT_INPUT',parameter_authority='CALLER_SUPPLIED_SYNTHETIC_OR_EXPLICIT_SCENARIO_NOT_SOURCE_BOUND',engineering_resource_limits_not_investment_policy=dict(sessions=512,security_ids=256,ratio_bits=12000),**dict.fromkeys(m.ACCOUNT_FALSE,False))
    trade=dict(buy_shares={'A':5,'Z':0},proposed_holdings={'A':15,'Z':0},gross_buy_usd='100',fees_usd='0.1',cash_after_usd='899.9')
    return args,account,trade


class Tests(unittest.TestCase):
    def test_independent_overnight_fee_and_exact_twr(self):
        args,a,t=fixture();before=deepcopy((args,a,t))
        with localcontext()as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True;out=m.inspect_account(args,a,t)
        self.assertEqual(out['chained_twr'],{'numerator':'6749','denominator':'6000'});self.assertEqual((args,a,t),before)
        for key,value in [('fees_usd','0'),('cash_after_usd','900'),('pre_flow_open_equity_usd','1200'),('cumulative_twr',{'numerator':'1749','denominator':'1000'})]:
            b=deepcopy(a);b['rows'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.inspect_account(args,b,t)

    def test_second_day_no_new_flow_fee_or_trade(self):
        args,a,t=fixture();args['sessions'].append(dict(session='2023-05-02',open_prices={'A':'25','Z':'1'},close_prices={'A':'25','Z':'1'},cash_injection_usd='0',buy_shares={}))
        row=deepcopy(a['rows'][0]);row.update(previous_close_session='2023-05-01',session='2023-05-02',cash_injection_usd='0',gross_buy_usd='0',fees_usd='0',holdings_before={'A':15,'Z':0},buy_shares={})
        for k in ('previous_close_equity_usd','pre_flow_open_equity_usd','post_flow_pre_fee_open_equity_usd','post_trade_open_equity_usd'):row[k]='1274.9'
        for k in ('overnight_pnl_usd','intraday_mark_pnl_before_fees_usd','after_flow_pnl_net_fees_usd','cash_flow_adjusted_pnl_usd'):row[k]='0'
        for k in ('overnight_return','after_flow_return','session_twr'):row[k]={'numerator':'0','denominator':'1'}
        a['rows'].append(row);self.assertEqual(m.inspect_account(args,a,t)['daily_rows_verified'],2)
        a['rows'][1]['cumulative_twr']={'numerator':'0','denominator':'1'}
        with self.assertRaises(ValueError):m.inspect_account(args,a,t)

    def test_missing_zero_slot_bad_types_and_no_false_authority(self):
        for mode in ('slot','bool','float','authority','None','session'):
            args,a,t=fixture()
            if mode=='slot':del args['sessions'][0]['open_prices']['Z']
            elif mode=='bool':args['sessions'][0]['buy_shares']['Z']=False
            elif mode=='float':args['initial']['cash_usd']=0.0
            elif mode=='authority':a['point_in_time_verified']=0
            elif mode=='session':a['rows'][0]['session']='2023-05-02'
            else:a=None
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_account(args,a,t)

    def test_partial_partition_preserves_unresolved_and_undispatched(self):
        ids=[str(i)for i in range(40)];r=dict(schema='CASH_NEIGHBOR_SELECTED_PATHS_RESULT_V1',scenario_count=40,status='STOPPED_NO_RETRY',completed_rows=[dict(scenario_id='0',scenario_index=0,outcome='REUSE_EXISTING_PAIRED_PATH')],attempted_scenario_ids=['1'],unresolved_scenario_ids=['1'],undispatched_scenario_ids=ids[2:],failure=dict(scenario_id='1',scenario_index=1,dispatch_invoked=True),**m.FLAGS)
        self.assertEqual(m.inspect_partition(r,ids),dict(completed=1,unresolved=1,undispatched=38,attempted=1))
        for mode in ('boolean','failure','missing','reorder'):
            b=deepcopy(r)
            if mode=='boolean':b['failure']['dispatch_invoked']=1
            elif mode=='failure':b['failure']['dispatch_invoked']=False
            elif mode=='missing':b['undispatched_scenario_ids'].pop()
            else:b['completed_rows'][0]['scenario_id']='3'
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_partition(b,ids)

    def test_pending_before_filesystem(self):
        with tempfile.TemporaryDirectory()as td,patch.object(m,'OUTPUT',Path(td)/'new'),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'Pending'):m.readback(execute=True)

if __name__=='__main__':unittest.main()

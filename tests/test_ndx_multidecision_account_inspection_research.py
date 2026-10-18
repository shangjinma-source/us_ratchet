from copy import deepcopy
import unittest
from backtest import ndx_multidecision_account_inspection_research as m
from backtest.ndx_dynamic_fractional_flow_split_research import simulate_dynamic_fractional_flow_split_research as old_fractional
from backtest.ndx_dynamic_fractional_flow_split_research_v2 import simulate_dynamic_fractional_flow_split_research as fractional
from backtest.ndx_dynamic_frozen_flow_split_research import simulate_dynamic_frozen_flow_split_research as whole
from test_ndx_dynamic_fractional_flow_split_research import fixture as fractional_fixture,flow as fflow,split as fsplit
from test_ndx_dynamic_frozen_flow_split_research import fixture as whole_fixture,flow as wflow,split as wsplit


def prepared(args,kind):
    kwargs=deepcopy(args)
    for key in ('opens','closes'):
      frame=kwargs[key];kwargs[key]=dict(index=[str(d.date()) for d in frame.index],columns=list(frame.columns),data=frame.values.tolist())
    return dict(track=kind,status='ENGINE_INPUTS_PREPARED_NOT_EXECUTED',stateful_input={'calendar':kwargs['closes']['index']},engine_binding={'keyword_arguments':kwargs})

class Tests(unittest.TestCase):
 def test_fractional_original_quotes_split_flow_fees_and_initial_peak(self):
    x=fractional_fixture();x['transaction_cost_bps']=10.;x['external_flows']=[fflow()];x['corporate_actions']=[fsplit()];x['opens'].iloc[2:,0]=5.;x['closes'].iloc[2:,0]=5.
    r=fractional(**x);t=prepared(x,'CONTINUOUS');report=m.inspect_saved_account(prepared_track=t,result=r)
    self.assertEqual(report['daily_rows'],4);self.assertEqual(report['split_trace_rows'],1);self.assertFalse(report['account_engine_called']);self.assertEqual(report['cash_injections_exact'],'100')
    for mutate in (lambda q:q['daily'][2].update(cash_usd=q['daily'][2]['cash_usd']+1),lambda q:q['daily'][2]['holdings']['SID'].update(shares=999.),lambda q:q['trades'][0].update(fee_usd=0.),lambda q:q['daily'][2].update(normalized_twr=2.)):
      bad=deepcopy(r);mutate(bad)
      with self.assertRaises(ValueError):m.inspect_saved_account(prepared_track=t,result=bad)
    t['engine_binding']['keyword_arguments']['opens']['data'][1][0]=20.
    with self.assertRaises(ValueError):m.inspect_saved_account(prepared_track=t,result=r)
 def test_old_fractional_projection_alias_is_rejected_not_reinterpreted(self):
    x=fractional_fixture();x['transaction_cost_bps']=10.;x['corporate_actions']=[fsplit()];x['external_flows']=[fflow()];x['opens'].iloc[2:,0]=5.;x['closes'].iloc[2:,0]=5.
    r=old_fractional(**x);self.assertNotEqual(r['rebalances'][0]['projection']['holdings'],r['rebalances'][0]['holdings_after'])
    with self.assertRaises(ValueError):m.inspect_saved_account(prepared_track=prepared(x,'CONTINUOUS'),result=r)
    r['schema']='DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V2'
    with self.assertRaises(ValueError):m.inspect_saved_account(prepared_track=prepared(x,'CONTINUOUS'),result=r)
 def test_whole_flow_does_not_resize_prior_close_basket_and_reject(self):
    for rejected in (False,True):
      x=whole_fixture();x['transaction_cost_bps']=10.;x['external_flows']=[wflow(x['schedule'][0]['execution_date'],100.)]
      if rejected:x['opens'].iloc[1,0]=100.
      r=whole(**x);t=prepared(x,'WHOLE_LOT');out=m.inspect_saved_account(prepared_track=t,result=r)
      self.assertEqual(out['scheduled_decisions'],1);self.assertFalse(out['integer_repair_search_independently_recomputed']);self.assertEqual(len(r['trades']),0 if rejected else 1)
      bad=deepcopy(r);bad['executions'][0]['frozen_delta']['A']+=1
      with self.assertRaises(ValueError):m.inspect_saved_account(prepared_track=t,result=bad)
 def test_whole_split_cancels_pending_and_old_shares_only(self):
    x=whole_fixture();day=str(x['closes'].index[3].date());dec=str(x['closes'].index[2].date());x['schedule'].append(dict(x['schedule'][0],decision_date=dec,execution_date=day));x['risk_chains_by_decision'][dec]={'A':'chain'};x['corporate_actions']=[wsplit(day)];x['closes'].iloc[3:,0]=5.;x['opens'].iloc[3:,0]=5.;x['external_flows']=[wflow(day)]
    r=whole(**x);out=m.inspect_saved_account(prepared_track=prepared(x,'WHOLE_LOT'),result=r);self.assertEqual(out['split_trace_rows'],1);self.assertEqual(out['chained_twr_exact'],'0');self.assertEqual(out['terminal_cash_exact'],'1100')
    bad=deepcopy(r);bad['corporate_actions'][0]['applied_events'][0]['post_shares']+=1
    with self.assertRaises(ValueError):m.inspect_saved_account(prepared_track=prepared(x,'WHOLE_LOT'),result=bad)
 def test_saved_identity_clock_and_frame_shape_cannot_drift(self):
    x=fractional_fixture();r=fractional(**x);t=prepared(x,'CONTINUOUS')
    for mutate in (lambda q:q['daily'][1]['holdings']['SID'].update(ticker='OTHER'),lambda q:q['daily'][1]['holdings']['SID'].update(issuer_id='OTHER'),lambda q:q['trades'][0].update(decision_date='2026-04-01')):
      bad=deepcopy(r);mutate(bad)
      with self.assertRaises(ValueError):m.inspect_saved_account(prepared_track=t,result=bad)
    for field in ('opens','closes'):
      bad=deepcopy(t);bad['engine_binding']['keyword_arguments'][field]['data'][1].append(10.)
      with self.assertRaises(ValueError):m.inspect_saved_account(prepared_track=bad,result=r)
    x=whole_fixture();r=whole(**x);t=prepared(x,'WHOLE_LOT')
    for mutate in (lambda q:q['executions'][0].update(decision_date='2026-04-01'),lambda q:q['daily'][1]['tickers'].update(A='OTHER'),lambda q:q['daily'][1]['risk_chain_observation_dates'].update(A='2099-01-01')):
      bad=deepcopy(r);mutate(bad)
      with self.assertRaises(ValueError):m.inspect_saved_account(prepared_track=t,result=bad)
 def test_fractional_rejected_still_retains_flow_and_all_slots(self):
    x=fractional_fixture();x.update(initial_cash_usd=50.,minimum_cash_buffer_usd=100.);x['external_flows']=[fflow(20.,'2026-04-01')];r=fractional(**x)
    out=m.inspect_saved_account(prepared_track=prepared(x,'CONTINUOUS'),result=r);self.assertEqual(out['terminal_cash_exact'],'70');self.assertEqual(out['chained_twr_exact'],'0')
    bad=deepcopy(r);bad['daily'].pop(1)
    with self.assertRaises(ValueError):m.inspect_saved_account(prepared_track=prepared(x,'CONTINUOUS'),result=bad)

if __name__=='__main__':unittest.main()

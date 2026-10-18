"""Synthetic proposals only; no account store, search or economic replay."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from data.current_research_qqq_reference import build_qqq_reference_plan,INITIAL_REVISION,METHOD
from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_fill_ledger import initialize_paper_ledger,apply_paper_fill,apply_paper_order_event,activate_paper_plan

DAYS=['2026-10-13','2026-10-14','2026-10-15','2026-10-30','2026-11-02','2026-11-03']
SID='internal:reference:QQQ'


def arguments(decision='2026-10-13',active='2026-10-14',price='10',from_date=None):
    pins={'evidence':'a'*64,'raw':'b'*64}
    return dict(expected_revision=INITIAL_REVISION,
        comparison_anchor=dict(initial_cash='100',decision_date=DAYS[0],active_date=DAYS[1],calendar=DAYS,source_references=['evidence']),
        qqq_security=dict(security_id=SID,identifier_kind='INTERNAL_RESEARCH_ID',ticker='QQQ',security_type='ETF',currency='USD',source_references=['evidence']),
        quote_observation=dict(ticker='QQQ',security_type='ETF',decision_date=decision,ohlc={'close':price},price_basis='CONDITIONAL_PROVIDER_UNIT',source_hashes={'raw':'b'*64},event_details=[],research_only=True,execution_blocked=True),
        decision_date=decision,active_date=active,calendar=DAYS,
        market_session=dict(date=active,timezone='America/New_York',open_at=active+'T09:30:00'+('-05:00' if active>='2026-11-01' else '-04:00'),close_at=active+'T16:00:00'+('-05:00' if active>='2026-11-01' else '-04:00'),source_references=['evidence']),
        source_hashes=pins,unit_continuity=dict(from_date=from_date or decision,to_date=decision,price_basis='CONDITIONAL_PROVIDER_UNIT',status='NO_UNPROCESSED_ACTIONS_OR_DIVIDENDS',source_references=['evidence']))


def partial_state():
    result=build_qqq_reference_plan(**arguments());assert result['status']=='READY',result
    plan=result['plan'];state=initialize_paper_ledger(plan,'paper-'+plan['plan_id'][:24]);order=plan['orders'][0]
    state=apply_paper_fill(state,dict(event_id='fill',mode='PAPER_MANUAL_FILL',plan_id=plan['plan_id'],order_id=order['order_id'],qty=7,price='10',fees='0',session=DAYS[1],expected_revision=state['revision']))
    state=apply_paper_order_event(state,dict(event_id='expire',event_type='EXPIRE',mode='PAPER_MANUAL_FILL',plan_id=plan['plan_id'],order_id=order['order_id'],completed_session=DAYS[1],expected_revision=state['revision']))
    return state


class ReferenceTests(unittest.TestCase):
    def test_initial_whole_share_or_cash_no_ranking(self):
        with patch('backtest.return_priority_fresh_cash_quantity_search.search_fresh_cash_quantities',side_effect=AssertionError('no search')):
            result=build_qqq_reference_plan(**arguments(price='30.001'))
        self.assertEqual(result['status'],'READY',result);self.assertEqual(result['target_quantities'],{SID:3})
        self.assertEqual(result['plan']['orders'][0]['limit'],'30')
        self.assertEqual(result['search_calls'],0);self.assertFalse(result['paired_registration_verified'])
        result=build_qqq_reference_plan(**arguments(price='101'))
        self.assertEqual(result['target_quantities'],{SID:0});self.assertEqual(result['plan']['orders'],[])
    def test_daily_frozen_target_wait_cash_and_monthly_own_equity(self):
        state=partial_state();before=deepcopy(state)
        daily=arguments(DAYS[1],DAYS[2],price='20',from_date=DAYS[0]);daily['expected_revision']=state['revision']
        result=build_qqq_reference_plan(state,**daily)
        self.assertEqual(result['status'],'READY',result);self.assertEqual(result['target_quantities'],{SID:10})
        self.assertEqual(result['plan']['orders'][0]['quantity'],1);self.assertEqual(result['plan']['wait_cash'][0]['remaining_deficit'],2)
        self.assertEqual(result['plan']['research_id'],state['plan']['research_id'])
        monthly=arguments(DAYS[3],DAYS[4],price='20',from_date=DAYS[0]);monthly['expected_revision']=state['revision']
        result=build_qqq_reference_plan(state,**monthly)
        self.assertEqual(result['investable_equity'],'170');self.assertEqual(result['available_cash'],'30')
        self.assertEqual(result['target_quantities'],{SID:8});self.assertEqual(result['route']['action'],'RESELECT')
        self.assertEqual(state,before);self.assertFalse(result['activation_performed'])
    def test_identity_method_fee_and_returned_actions_block(self):
        for mutate in [lambda a:a['qqq_security'].update(ticker='SNDK'),lambda a:a.update(commission_bps='1'),
                       lambda a:a['qqq_security'].update(identifier_kind='ASSUMED_CUSIP'),
                       lambda a:a['unit_continuity'].update(status='UNKNOWN')]:
            args=arguments();mutate(args)
            self.assertEqual(build_qqq_reference_plan(**args)['status'],'BLOCKED')
    def test_actions_only_block_exposed_assets_or_frozen_units(self):
        for kind in ('dividends','splits'):
            args=arguments();args['quote_observation']['event_details']=[dict(session=DAYS[0],kind=kind)]
            result=build_qqq_reference_plan(**args)
            self.assertEqual(result['status'],'READY',result);self.assertEqual(len(result['ignored_unexposed_events']),1)
        state=partial_state()
        args=arguments(DAYS[1],DAYS[2],from_date=DAYS[0]);args['expected_revision']=state['revision']
        args['quote_observation']['event_details']=[dict(session=DAYS[1],kind='dividends')]
        self.assertEqual(build_qqq_reference_plan(state,**args)['status'],'READY')
        args=arguments(DAYS[3],DAYS[4],from_date=DAYS[0]);args['expected_revision']=state['revision']
        args['quote_observation']['event_details']=[dict(session=DAYS[2],kind='dividends')]
        self.assertIn('EXPOSED',build_qqq_reference_plan(state,**args)['reason'])
        args['quote_observation']['event_details']=[dict(session=DAYS[1],kind='splits')]
        self.assertIn('EXPOSED',build_qqq_reference_plan(state,**args)['reason'])

    def test_dividend_sell_session_retains_pre_session_exposure(self):
        state=partial_state();old=state['plan'];snapshot=deepcopy(old['causal_inputs']['research_snapshot'])
        snapshot['market_session']=arguments(DAYS[1],DAYS[2])['market_session']
        plan=build_current_research_limit_plan(research_snapshot=snapshot,quotes=[dict(security_id=SID,price='10',as_of=DAYS[1],price_kind='RAW_PROVIDER_CLOSE_DECIMAL',price_basis='CONDITIONAL_PROVIDER_UNIT',source_references=['raw'])],
            available_cash=state['cash'],shares=state['shares'],account_revision=state['revision'],decision_date=DAYS[1],active_date=DAYS[2],calendar=DAYS,strategy_version=METHOD,target_quantities={SID:0})
        state=activate_paper_plan(state,plan,dict(event_type='ACTIVATE_PLAN',event_id='activate-exit',mode='PAPER_MANUAL_FILL',plan_id=plan['plan_id'],expected_revision=state['revision']))
        state=apply_paper_fill(state,dict(event_id='sell',mode='PAPER_MANUAL_FILL',plan_id=plan['plan_id'],order_id=plan['orders'][0]['order_id'],qty=7,price='10',fees='0',session=DAYS[2],expected_revision=state['revision']))
        args=arguments(DAYS[3],DAYS[4],from_date=DAYS[1]);args['expected_revision']=state['revision']
        args['quote_observation']['event_details']=[dict(session=DAYS[2],kind='dividends')]
        self.assertEqual(state['shares'].get(SID,0),0)
        self.assertIn('EXPOSED',build_qqq_reference_plan(state,**args)['reason'])

    def test_late_returned_action_before_current_plan_is_not_lost(self):
        state=partial_state()
        args=arguments(DAYS[3],DAYS[4],price='20',from_date=DAYS[0]);args['expected_revision']=state['revision']
        plan=build_qqq_reference_plan(state,**args)['plan']
        state=activate_paper_plan(state,plan,dict(event_type='ACTIVATE_PLAN',event_id='later-plan',mode='PAPER_MANUAL_FILL',plan_id=plan['plan_id'],expected_revision=state['revision']))
        for order in plan['orders']:
            state=apply_paper_order_event(state,dict(event_id='close-'+order['order_id'],event_type='EXPIRE',mode='PAPER_MANUAL_FILL',plan_id=plan['plan_id'],order_id=order['order_id'],completed_session=DAYS[4],expected_revision=state['revision']))
        args=arguments(DAYS[4],DAYS[5],price='20',from_date=DAYS[3]);args['expected_revision']=state['revision']
        for kind in ('dividends','splits'):
            args['quote_observation']['event_details']=[dict(session=DAYS[2],kind=kind)]
            result=build_qqq_reference_plan(state,**args)
            self.assertEqual(result['status'],'BLOCKED',result)
            self.assertIn('UNSUPPORTED_EXPOSED',result['reason'])
        args['quote_observation']['event_details']=[dict(session=DAYS[1],kind='dividends')]
        self.assertEqual(build_qqq_reference_plan(state,**args)['status'],'READY')

    def test_old_orders_unclosed_and_legacy_account_not_reused(self):
        initial=build_qqq_reference_plan(**arguments())['plan']
        state=initialize_paper_ledger(initial,'paper-'+initial['plan_id'][:24])
        args=arguments(DAYS[1],DAYS[2],from_date=DAYS[0]);args['expected_revision']=state['revision']
        self.assertIn('OPEN_ORDERS',build_qqq_reference_plan(state,**args)['reason'])
        state=partial_state();args['expected_revision']=state['revision'];args['comparison_anchor']['initial_cash']='200'
        self.assertEqual(build_qqq_reference_plan(state,**args)['status'],'BLOCKED')

if __name__=='__main__':unittest.main()

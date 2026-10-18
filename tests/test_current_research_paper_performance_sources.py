import unittest,json,hashlib
from copy import deepcopy
from datetime import datetime
import test_current_research_successor_prepare as fixture
import test_current_research_monthly_plan as sessions
from data.current_research_successor_prepare import save_prepared_input
from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_fill_ledger import activate_paper_plan,apply_paper_fill
from data.current_research_paper_performance_sources import build_saved_paper_performance

class SavedPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.PrepareTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.value=self.f.prepare();self.saved=save_prepared_input(self.value,root=self.f.root,relative_directory='prepared',registry_path='registry.json')
        original=json.loads((self.f.root/'calendar.json').read_bytes())
        original['calendar']=['2026-10-13']+original['calendar'];original['sessions'].insert(0,dict(sessions.session('2026-10-13'),source='evidence'))
        (self.f.root/'report_calendar.json').write_text(json.dumps(original))
        self.pins=dict(self.f.pins);self.pins['report_calendar.json']=hashlib.sha256((self.f.root/'report_calendar.json').read_bytes()).hexdigest()
        self.kw=dict(root=self.f.root,input_ids=[self.saved['input_id']],calendar_path='report_calendar.json',calendar_source_hashes=self.pins,through_date='2026-10-14',now=datetime.fromisoformat('2026-10-15T17:00:00-04:00'),registry_path='registry.json')
    def test_real_sources_and_historical_prefix_revision(self):
        state=self.f.state;c=state['plan']['causal_inputs']
        new=build_current_research_limit_plan(research_snapshot=deepcopy(c['research_snapshot']),quotes=[dict(q,security_id=sid,as_of='2026-10-14') for sid,q in c['quotes'].items()],available_cash=state['cash'],shares=state['shares'],account_revision=state['revision'],decision_date='2026-10-14',active_date='2026-10-15',calendar=['2026-10-14','2026-10-15'],strategy_version='test',target_quantities={'A':2})
        state=activate_paper_plan(state,new,dict(event_id='activate',mode='PAPER_MANUAL_FILL',event_type='ACTIVATE_PLAN',plan_id=new['plan_id'],expected_revision=state['revision']))
        r=build_saved_paper_performance(state,**self.kw)
        self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['daily_ledger'][0]['shares'],{})
        self.assertEqual(r['daily_ledger'][1]['equity'],'201/2');self.assertEqual(r['total_return'],'1/200')
        self.assertNotEqual(r['revision'],r['saved_source_audit'][0]['prefix_revision'])
    def test_missing_session_observation_remains_incomplete(self):
        args=dict(self.kw,input_ids=[])
        r=build_saved_paper_performance(self.f.state,**args)
        self.assertEqual(r['status'],'INCOMPLETE');self.assertIsNone(r['total_return'])

    def test_dividend_previous_session_holding_blocks_but_ex_date_buy_does_not(self):
        from unittest.mock import patch
        from data.current_research_successor_inputs import SuccessorInputLoader
        bundle=deepcopy(self.value['bundle'])
        decoded=deepcopy(bundle['saved_quote_observations']['A'])
        decoded['event_details']=[dict(session='2026-10-14',kind='dividends')]
        # This ledger first buys A on October 14: no prior-session entitlement.
        with patch('data.current_research_paper_performance_sources.read_saved_quote',return_value=decoded):
            result=build_saved_paper_performance(self.f.state,**self.kw)
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(result['return_scope'],'PRICE_AND_RECORDED_FILL_FEES_ONLY')
        self.assertFalse(result['total_return_certified'])
        self.assertFalse(result['dividend_coverage_complete'])
        # An October 15 dividend is exposed to the two shares held overnight.
        bundle['decision_date']='2026-10-15'
        bundle['decision_session']=dict(sessions.session('2026-10-15'),source='evidence')
        bundle['valuation_quotes'][0]['as_of']='2026-10-15'
        bundle['admission']['reviewed_at']='2026-10-15T17:00:00-04:00'
        bundle['held_unit_continuity']['A']['to_date']='2026-10-15'
        decoded['event_details']=[dict(session='2026-10-15',kind='dividends')]
        decoded['received_at']='2026-10-15T20:30:00+00:00'
        with patch.object(SuccessorInputLoader,'__call__',return_value=bundle), patch('data.current_research_paper_performance_sources.validate_successor_time_chain'), patch('data.current_research_paper_performance_sources.read_saved_quote',return_value=decoded):
            with self.assertRaisesRegex(ValueError,'UNPROCESSED_EXPOSED_DIVIDEND'):
                build_saved_paper_performance(self.f.state,**dict(self.kw,through_date='2026-10-15'))
    def test_duplicates_and_source_drift_rejected(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE_INPUT_ID'):build_saved_paper_performance(self.f.state,**dict(self.kw,input_ids=self.kw['input_ids']*2))
        (self.f.root/'AAA.response.bin').write_bytes(b'changed')
        with self.assertRaises(ValueError):build_saved_paper_performance(self.f.state,**self.kw)
    def test_old_prefix_late_day_action_blocks_even_after_same_day_sell(self):
        from unittest.mock import patch
        from data.current_research_successor_inputs import SuccessorInputLoader
        state=self.f.state;c=state['plan']['causal_inputs']
        new=build_current_research_limit_plan(research_snapshot=deepcopy(c['research_snapshot']),quotes=[dict(q,security_id=sid,as_of='2026-10-14') for sid,q in c['quotes'].items()],available_cash=state['cash'],shares=state['shares'],account_revision=state['revision'],decision_date='2026-10-14',active_date='2026-10-15',calendar=['2026-10-14','2026-10-15'],strategy_version='test',target_quantities={})
        state=activate_paper_plan(state,new,dict(event_id='activate',mode='PAPER_MANUAL_FILL',event_type='ACTIVATE_PLAN',plan_id=new['plan_id'],expected_revision=state['revision']))
        state=apply_paper_fill(state,dict(event_id='sell',mode='PAPER_MANUAL_FILL',plan_id=new['plan_id'],order_id=new['orders'][0]['order_id'],qty=2,price='10',fees='0',session='2026-10-15',expected_revision=state['revision']))
        self.assertFalse(any(state['shares'].values()))
        bundle=deepcopy(self.value['bundle']);bundle['decision_date']='2026-10-15'
        bundle['decision_session']=dict(sessions.session('2026-10-15'),source='evidence')
        bundle['valuation_quotes'][0]['as_of']='2026-10-15'
        bundle['admission']['reviewed_at']='2026-10-15T17:00:00-04:00'
        bundle['held_unit_continuity']['A']['to_date']='2026-10-15'
        decoded=deepcopy(bundle['saved_quote_observations']['A']);decoded['received_at']='2026-10-15T20:30:00+00:00'
        decoded['event_details']=[dict(session='2026-10-15',kind='splits')]
        with patch.object(SuccessorInputLoader,'__call__',return_value=bundle), patch('data.current_research_paper_performance_sources.validate_successor_time_chain'), patch('data.current_research_paper_performance_sources.read_saved_quote',return_value=decoded):
            with self.assertRaisesRegex(ValueError,'UNPROCESSED_EXPOSED_RAW_ACTION'):
                build_saved_paper_performance(state,**dict(self.kw,through_date='2026-10-15'))
            decoded['event_details']=[dict(session='2026-10-15',kind='dividends')]
            with self.assertRaisesRegex(ValueError,'UNPROCESSED_EXPOSED_DIVIDEND'):
                build_saved_paper_performance(state,**dict(self.kw,through_date='2026-10-15'))
        bundle.update(revision=state['revision'],parent_plan_id=state['plan']['plan_id'],valuation_quotes=[],saved_quote_observations={},held_unit_continuity={})
        with patch.object(SuccessorInputLoader,'__call__',return_value=bundle), patch('data.current_research_paper_performance_sources.validate_successor_time_chain'):
            with self.assertRaisesRegex(ValueError,'MISSING_OPENING_HELD_OR_TRADED_ACTION_EVIDENCE'):
                build_saved_paper_performance(state,**dict(self.kw,through_date='2026-10-15'))

    def test_claimed_quote_close_and_wrong_prefix_rejected(self):
        from unittest.mock import patch
        from data.current_research_successor_inputs import SuccessorInputLoader
        for field in ['price','parent','revision']:
            bundle=deepcopy(self.value['bundle'])
            if field=='price':bundle['valuation_quotes'][0]['price']='999'
            elif field=='parent':bundle['parent_plan_id']='wrong'
            else:bundle['revision']='wrong'
            with patch.object(SuccessorInputLoader,'__call__',return_value=bundle):
                with self.assertRaises(ValueError):build_saved_paper_performance(self.f.state,**self.kw)

if __name__=='__main__':unittest.main()


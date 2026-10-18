import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
import test_current_research_intraday_paper_ledger as fixture
from test_current_research_intraday_execution import NOW,payload,snapshot
from data.current_research_intraday_paper_ledger import apply_intraday_paper_event
from data.current_research_intraday_continuation import build_intraday_continuation_proposal

class ContinuationTests(unittest.TestCase):
    def setup(self,root,fill=2,price='1400',fees='0'):
        service,proposal,inputs,state=fixture.AcceptanceTests().fixture(root)
        event=fixture.AcceptanceTests().event(state,quantity=fill,price=price,fees=fees,executed_at=NOW.isoformat(),recorded_at=NOW.isoformat())
        state=apply_intraday_paper_event(state,event,now=NOW)
        if fill<14:
            event=fixture.AcceptanceTests().event(state,'CANCEL',event_id='cancel',cancelled_at=NOW.isoformat(),recorded_at=NOW.isoformat())
            state=apply_intraday_paper_event(state,event,now=NOW)
        response=service.preview('a'*24);receipt=response['observation_record']
        args=dict(expected_revision=state['revision'],journal_root=root,session='2026-10-15',event_path=receipt['event_path'],expected_event_hashes={receipt['event_path']:receipt['event_sha256']},research_snapshot=snapshot(None),market_session=inputs['market_session'],source_hashes=inputs['source_hashes'],now=NOW,
            unit_continuity=dict(security_id='sndk',from_session='2026-10-15',to_session='2026-10-15',status='NO_UNPROCESSED_ACTIONS',price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',initial_event_sha256=proposal['causal_inputs']['event_sha256'],current_event_sha256=receipt['event_sha256'],source_references=['calendar'],covered_from=NOW.isoformat(),covered_through=NOW.isoformat(),reviewed_asof=NOW.isoformat()))
        args['research_snapshot']=deepcopy(proposal['causal_inputs']['research_snapshot'])
        return service,state,args
    def test_partial_remaining_not_fresh_cash_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            _,state,args=self.setup(root);before=deepcopy(state)
            result=build_intraday_continuation_proposal(state,**args)
            self.assertEqual(result['status'],'READY',result);self.assertEqual(result['quantity'],12)
            self.assertEqual(result['target_quantity'],14);self.assertEqual(result['held_quantity'],2)
            self.assertEqual(result['available_cash'],'17200');self.assertEqual(state,before)
    def test_lower_cap_never_raises_target_and_full_no_action(self):
        with tempfile.TemporaryDirectory() as root:
            service,state,args=self.setup(root)
            p=payload();p['chart']['result'][0]['meta']['regularMarketPrice']='100'
            service.fetch=lambda _:p;r=service.preview('a'*24);receipt=r['observation_record']
            args.update(event_path=receipt['event_path'],expected_event_hashes={receipt['event_path']:receipt['event_sha256']})
            args['unit_continuity']['current_event_sha256']=receipt['event_sha256']
            self.assertEqual(build_intraday_continuation_proposal(state,**args)['quantity'],12)
        with tempfile.TemporaryDirectory() as root:
            _,state,args=self.setup(root,fill=14)
            result=build_intraday_continuation_proposal(state,**args)
            self.assertEqual(result['action'],'NO_ACTION');self.assertEqual(result['quantity'],0)
    def test_wait_cash_fee_and_closed_revision_continuity_guards(self):
        with tempfile.TemporaryDirectory() as root:
            _,state,args=self.setup(root,fees='100')
            result=build_intraday_continuation_proposal(state,**args)
            self.assertEqual(result['status'],'READY',result);self.assertEqual(result['quantity'],12)
            self.assertEqual(result['available_cash'],'17100')
            for change in ({'expected_revision':'bad'},{'session':'2026-11-02'},{'unit_continuity':{}}):
                a=deepcopy(args);a.update(change)
                self.assertEqual(build_intraday_continuation_proposal(state,**a)['status'],'BLOCKED')
            tampered=deepcopy(state);tampered['cash']='20000'
            self.assertEqual(build_intraday_continuation_proposal(tampered,**args)['status'],'BLOCKED')
    def test_cross_day_requires_explicit_action_coverage(self):
        with tempfile.TemporaryDirectory() as root:
            service,state,args=self.setup(root);tomorrow=NOW+timedelta(days=1)
            p=payload();r=p['chart']['result'][0]
            r['meta']['regularMarketPrice']='3000'
            for field in ('open','high','low','close'):r['indicators']['quote'][0][field][0]=3000
            r['timestamp']=[t+86400 for t in r['timestamp']];r['meta']['regularMarketTime']+=86400
            for key in ('start','end'):r['meta']['currentTradingPeriod']['regular'][key]+=86400
            service.fetch=lambda _:p;service.clock=lambda:tomorrow;receipt=service.preview('a'*24)['observation_record']
            args.update(now=tomorrow,session='2026-10-16',event_path=receipt['event_path'],expected_event_hashes={receipt['event_path']:receipt['event_sha256']})
            args['market_session']=dict(date='2026-10-16',timezone='America/New_York',open_at='2026-10-16T09:30:00-04:00',close_at='2026-10-16T16:00:00-04:00',source_references=['calendar'])
            args['unit_continuity'].update(to_session='2026-10-16',current_event_sha256=receipt['event_sha256'],covered_through=tomorrow.isoformat(),reviewed_asof=tomorrow.isoformat())
            result=build_intraday_continuation_proposal(state,**args);self.assertIn('CROSS_SESSION',result['reason'])
            args['unit_continuity']['action_review']=dict(covered_from='2026-10-15',covered_through='2026-10-16',status='NO_UNPROCESSED_ACTIONS',source_references=['calendar'],reviewed_asof=tomorrow.isoformat())
            result=build_intraday_continuation_proposal(state,**args)
            self.assertEqual(result['status'],'READY');self.assertEqual(result['quantity'],5);self.assertEqual(result['remaining_deficit'],7)

if __name__=='__main__':unittest.main()

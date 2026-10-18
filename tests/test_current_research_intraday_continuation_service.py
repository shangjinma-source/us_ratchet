import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
import test_current_research_intraday_paper_service as fixtures
from test_current_research_intraday_execution import NOW

RID='a'*24

class ContinuationServiceTests(unittest.TestCase):
    def fixture(self,root):
        service,reference,clock=fixtures.ServiceTests().fixture(root)
        def evidence(**kw):
            state=kw['state'];old=state['acceptance']['proposal']['causal_inputs']
            current=reference.journal.read_event(kw['event_path'],expected_sha256=kw['event_sha256'])
            checked=current['response']['stocks'][0]['checked_at'];day=checked[:10]
            return dict(source_hashes={},unit_continuity=dict(security_id='sndk',from_session='2026-10-15',to_session=day,
                status='NO_UNPROCESSED_ACTIONS',price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
                initial_event_sha256=old['event_sha256'],current_event_sha256=kw['event_sha256'],source_references=['source.json'],
                covered_from=old['observation']['checked_at'],covered_through=checked,reviewed_asof=checked))
        service.continuity_reader=evidence
        p=service.preview(RID)['proposal'];state=service.accept(RID,p['proposal_id'],'initial')
        return service,reference,clock,state
    def event(self,state,kind='FILL',event_id='fill',**kw):
        e=dict(event_id=event_id,kind=kind,expected_revision=state['revision'],order_id=state['order']['order_id'])
        if kind=='FILL':e.update(quantity=2,price='1400',fees='0',executed_at=NOW.isoformat())
        if kind=='CANCEL':e['cancelled_at']=NOW.isoformat()
        e.update(kw);return e
    def close(self,service,state):
        state=service.record_event(RID,self.event(state))
        return service.record_event(RID,self.event(state,'CANCEL','cancel'))
    def test_repeat_cycle_actual_cash_and_success_retry(self):
        with tempfile.TemporaryDirectory() as root:
            service,reference,clock,state=self.fixture(root);state=self.close(service,state)
            result=service.continuation_preview(RID);p=result['proposal']
            self.assertEqual(p['quantity'],12);self.assertEqual(p['available_cash'],'17200')
            state=service.accept_continuation(RID,p['proposal_id'],'next',state['revision'])
            state=service.record_event(RID,self.event(state,event_id='fill2',quantity=1))
            state=service.record_event(RID,self.event(state,'CANCEL','cancel2'))
            p2=service.continuation_preview(RID)['proposal'];self.assertEqual(p2['quantity'],11)
            revision=state['revision'];state=service.accept_continuation(RID,p2['proposal_id'],'next2',revision)
            self.assertEqual(state['cash'],'15800');self.assertEqual(state['shares'],{'sndk':3})
            service.continuation_proposals.clear();clock[0]+=timedelta(days=1)
            service.continuity_reader=lambda **kw:self.fail('idempotent must not reread')
            self.assertEqual(service.accept_continuation(RID,p2['proposal_id'],'next2',revision),state)
    def test_open_order_refresh_expiry_and_source_drift(self):
        for mode in ('refresh','expiry','drift','pin_conflict'):
            with tempfile.TemporaryDirectory() as root:
                service,reference,clock,state=self.fixture(root)
                with self.assertRaisesRegex(ValueError,'PRIOR_ORDER'):service.continuation_preview(RID)
                state=self.close(service,state);p=service.continuation_preview(RID)['proposal']
                if mode=='refresh':reference.preview(RID)
                if mode=='expiry':clock[0]+=timedelta(minutes=3)
                if mode=='drift':service.continuity_reader=lambda **kw:(_ for _ in ()).throw(ValueError('source drift'))
                if mode=='pin_conflict':
                    old=service.continuity_reader
                    def changed(**kw):
                        value=old(**kw);value['source_hashes']['source.json']='0'*64;return value
                    service.continuity_reader=changed
                with self.assertRaises(ValueError):service.accept_continuation(RID,p['proposal_id'],'next',state['revision'])
                self.assertEqual(service.account(RID),state)
    def test_no_action_is_preview_only_and_stale_revision_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            service,_,_,state=self.fixture(root)
            state=service.record_event(RID,self.event(state,quantity=14))
            p=service.continuation_preview(RID)['proposal'];self.assertEqual(p['action'],'NO_ACTION')
            with self.assertRaises(ValueError):service.accept_continuation(RID,p['proposal_id'],'next',state['revision'])
            with self.assertRaises(ValueError):service.accept_continuation(RID,p['proposal_id'],'next','stale')

if __name__=='__main__':unittest.main()

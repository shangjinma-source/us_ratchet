import tempfile
import unittest
import json
from pathlib import Path
from hashlib import sha256
from datetime import timedelta
import test_current_research_intraday_continuation_service as fixtures
from test_current_research_intraday_execution import NOW

RID='a'*24

class PendingTests(unittest.TestCase):
    def fixture(self,root):
        service,reference,clock,state=fixtures.ContinuationServiceTests().fixture(root)
        state=fixtures.ContinuationServiceTests().close(service,state)
        service.continuity_reader=None
        return service,reference,clock,state
    def register(self,service,state):
        pending=service.pending_unit_reviews[RID];receipt=pending['receipt']
        event=service.reference.journal.read_event(receipt['event_path'],expected_sha256=receipt['event_sha256'])
        checked=event['response']['stocks'][0]['checked_at'];old=state['acceptance']['proposal']['causal_inputs']
        unit=dict(security_id='sndk',from_session='2026-10-15',to_session='2026-10-15',status='NO_UNPROCESSED_ACTIONS',price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',initial_event_sha256=old['event_sha256'],current_event_sha256=receipt['event_sha256'],source_references=['source.json'],covered_from=old['observation']['checked_at'],covered_through=checked,reviewed_asof=checked)
        bind=dict(account_id=state['account_id'],initial_acceptance_id=state['acceptance_id'],event_path=receipt['event_path'],event_sha256=receipt['event_sha256'])
        bundle=dict(bind,schema='CONDITIONAL_INTRADAY_UNIT_REVIEW_V1',status='REVIEWED_CONDITIONAL',reviewed_by='synthetic reviewer',source_hashes={'source.json':sha256((service.root/'source.json').read_bytes()).hexdigest()},unit_continuity=unit)
        path=service.root/'review.json';path.write_text(json.dumps(bundle),encoding='utf-8')
        registry=service.root/'data/research_paper_intraday/continuity_sources.json';registry.parent.mkdir(parents=True,exist_ok=True)
        registry.write_text(json.dumps(dict(schema='INTRADAY_UNIT_CONTINUITY_REGISTRY_V1',entries=[dict(bind,bundle_path='review.json',sha256=sha256(path.read_bytes()).hexdigest())])),encoding='utf-8')
    def test_default_loader_pending_review_reuses_receipt_and_accepts(self):
        with tempfile.TemporaryDirectory() as root:
            service,reference,clock,state=self.fixture(root)
            response=service.continuation_preview(RID);self.assertEqual(response['status'],'PENDING_UNIT_REVIEW')
            self.assertEqual(set(response['review_reference']),{'event_sha256','checked_at','accept_before'})
            self.register(service,state)
            reference.fetch=lambda _:self.fail('pending must reuse capture')
            p=service.continuation_preview(RID)['proposal']
            result=service.accept_continuation(RID,p['proposal_id'],'next',state['revision'])
            self.assertEqual(result['cash'],state['cash']);self.assertEqual(result['shares'],state['shares'])
    def test_expired_or_new_observation_clears_without_refetch(self):
        for mode in ('expired','refresh'):
            with tempfile.TemporaryDirectory() as root:
                service,reference,clock,state=self.fixture(root);service.continuation_preview(RID)
                if mode=='expired':clock[0]+=timedelta(minutes=3)
                else:reference.preview(RID)
                reference.fetch=lambda _:self.fail('must not silently replace')
                with self.assertRaises(ValueError):service.continuation_preview(RID)
                self.assertNotIn(RID,service.pending_unit_reviews)
    def test_source_drift_does_not_become_pending(self):
        with tempfile.TemporaryDirectory() as root:
            service,reference,clock,state=self.fixture(root);service.continuation_preview(RID);self.register(service,state)
            (service.root/'source.json').write_bytes(b'changed')
            with self.assertRaises(ValueError):service.continuation_preview(RID)
            self.assertNotIn(RID,service.pending_unit_reviews)

if __name__=='__main__':unittest.main()

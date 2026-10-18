"""Temporal counterexamples use temporary sources and SQLite only."""
from copy import deepcopy
from datetime import datetime
import unittest
import test_current_research_successor_prepare as fixture
from data.current_research_successor_prepare import save_prepared_input
from data.current_research_successor_inputs import SuccessorInputLoader
from data.current_research_successor_service import CurrentResearchSuccessorService
from data.current_research_paper_service import CurrentResearchPaperService
from data.current_research_paper_store import ResearchPaperStore

class SuccessorTemporalTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.PrepareTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def service(self,value):
        f=self.f;saved=save_prepared_input(value,root=f.root,relative_directory='prepared',registry_path='registry.json')
        loader=SuccessorInputLoader(root=f.root,registry_path='registry.json')
        base=CurrentResearchPaperService(root=f.root,directory=f.root/'paper',clock=lambda:datetime.fromisoformat('2026-10-14T17:00:00-04:00'))
        store=ResearchPaperStore(base.directory);store.create(f.state['account_id'],f.initial['plan']);store.record_fill(f.state['account_id'],f.fill)
        service=CurrentResearchSuccessorService(base_service=base,input_provider=loader,search=lambda **_:self.fail('search forbidden'))
        return loader,saved,service
    def test_prepare_future_capture_and_review_before_close(self):
        self.f.f.received='2099-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'CAPTURE_AFTER_REVIEW'):self.f.prepare()
        self.f.f.received='2026-10-14T21:00:00+00:00'
        self.f.kw['admission']['reviewed_at']='2026-10-14T15:00:00-04:00'
        with self.assertRaisesRegex(ValueError,'REVIEW_BEFORE_DECISION_CLOSE'):self.f.prepare()
    def test_loader_does_not_trust_observation_timestamp(self):
        value=self.f.prepare();value['bundle']['saved_quote_observations']['A']['received_at']='2026-10-14T20:30:00+00:00'
        # Recompute registration honestly to test semantic binding, not stale hashes.
        from data.current_research_successor_prepare import _bytes
        import hashlib
        value['input_id']=hashlib.sha256(_bytes(value['bundle'])).hexdigest()
        value['registry_entry'].update(bundle_path=value['input_id']+'.json',sha256=value['input_id'])
        with self.assertRaisesRegex(ValueError,'RECEIPT_TIME_MISMATCH'):
            loader,saved,_=self.service(value)
            loader(saved['input_id'])
    def test_future_review_rejected_by_available_and_preview_no_db_mutation(self):
        self.f.kw['admission']['reviewed_at']='2099-01-01T00:00:00+00:00'
        loader,saved,service=self.service(self.f.prepare())
        path=self.f.root/'paper/research_paper.sqlite3';before=path.read_bytes()
        for call in [lambda:service.available_input(self.f.state['account_id'],self.f.state['revision']),
                     lambda:service.preview(self.f.state['account_id'],saved['input_id'],self.f.state['revision'])]:
            with self.assertRaisesRegex(ValueError,'REVIEW_AFTER_SERVER_NOW'):call()
        self.assertEqual(path.read_bytes(),before)
    def test_raw_policy_cannot_drop_observations(self):
        from data.current_research_successor_inputs import validate_successor_time_chain
        value=self.f.prepare()['bundle']
        for replacement in (None, {}):
            value['saved_quote_observations']=replacement
            with self.assertRaisesRegex(ValueError,'SAVED_OBSERVATION_DOMAIN_REQUIRED'):
                validate_successor_time_chain(value,root=self.f.root)

    def test_allcash_empty_quote_domain_is_valid_but_missing_record_is_not(self):
        from data.current_research_successor_inputs import validate_successor_time_chain
        value=self.f.prepare()['bundle']
        value['valuation_quotes']=[];value['saved_quote_observations']={}
        validate_successor_time_chain(value,root=self.f.root)
        value.pop('saved_quote_observations')
        with self.assertRaisesRegex(ValueError,'SAVED_OBSERVATION_DOMAIN_REQUIRED'):
            validate_successor_time_chain(value,root=self.f.root)

    def test_legacy_no_saved_observation_still_requires_review_time(self):
        from data.current_research_successor_inputs import validate_successor_time_chain
        value=self.f.prepare()['bundle'];value.pop('saved_quote_observations');value.pop('quote_reference_policy')
        now=datetime.fromisoformat('2026-10-14T17:00:00-04:00')
        validate_successor_time_chain(value,root=self.f.root,now=now)
        value['admission']['reviewed_at']='2099-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'REVIEW_AFTER_SERVER_NOW'):validate_successor_time_chain(value,root=self.f.root,now=now)

if __name__=='__main__':unittest.main()

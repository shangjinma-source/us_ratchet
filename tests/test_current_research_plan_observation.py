from copy import deepcopy
from datetime import datetime
import hashlib
import unittest
from data.current_research_plan_observation import review_plan_observations
from test_current_research_plan_review import state_fixture
import test_current_research_saved_quote as saved_fixtures


class PlanObservationTests(unittest.TestCase):
    def setUp(self):
        self.source=saved_fixtures.SavedQuoteTests();self.source.setUp();self.addCleanup(self.source.doCleanups)
        self.state=state_fixture();self.now=datetime.fromisoformat('2026-10-15T17:00:00-04:00')
    def prepared(self, day='2026-10-13'):
        if day=='2026-10-14':
            for key,value in [('open',10),('high',11),('low',9),('close',10.25)]:
                self.source.channel['indicators']['quote'][0][key][1]=value
            self.source.received='2026-10-15T12:00:00+00:00'
        self.source.read()
        pins={};entry={}
        for suffix,key in [('.response.bin','raw_sha256'),('.receipt.json','receipt_sha256'),('.decoded.json','decoded_sha256')]:
            name='AAA'+suffix;digest=hashlib.sha256((self.source.root/name).read_bytes()).hexdigest();pins[name]=digest;entry[key]=digest
        descriptor=dict(security_id='A',ticker='AAA',expected_security_type='EQUITY',relative_directory='.',entry=entry,observation_date=day,session_close_at=day+'T16:00:00-04:00')
        return descriptor,pins
    def review(self, observations, pins=None, cutoff='2026-10-14', now=None):
        return review_plan_observations(self.state,root=self.source.root,observations=observations,observed_through=cutoff,now=now or self.now,reviewed_observation_pins=pins)
    def test_default_has_no_close_guess_or_selection_date_dependency(self):
        from data.current_research_plan_observation import review_plan_bound_observations
        r=review_plan_bound_observations(self.state,root=self.source.root,now=self.now)
        self.assertEqual(r['observed_through'],self.state['plan']['causal_inputs']['decision_date'])
        self.assertEqual(r['orders'][0]['observed_touch'],'UNKNOWN')
        self.assertEqual(r['orders'][0]['reason'],'BOUND_RAW_REFERENCE_MISSING')

    def test_default_rejects_same_decision_date_without_completion_proof(self):
        from data.current_research_plan_observation import review_plan_bound_observations
        day=self.state['plan']['causal_inputs']['decision_date']
        for time in ('12:00:00', '17:00:00'):
            with self.assertRaisesRegex(ValueError,'REQUIRES_PRIOR_NY_DATE'):
                review_plan_bound_observations(self.state,root=self.source.root,now=datetime.fromisoformat(day+'T'+time+'-04:00'))

    def test_default_verifies_three_source_pins_without_reading_active_ohlc(self):
        from data.current_research_plan_observation import review_plan_bound_observations
        from data.current_research_limit_plan import build_current_research_limit_plan
        from data.current_research_fill_ledger import initialize_paper_ledger
        _,pins=self.prepared()
        c=deepcopy(self.state['plan']['causal_inputs']);c['research_snapshot']['source_hashes']=pins
        quotes=[dict(v,security_id=sid,source_references=['AAA.response.bin']) for sid,v in c['quotes'].items()]
        plan=build_current_research_limit_plan(research_snapshot=c['research_snapshot'],quotes=quotes,available_cash=c['available_cash'],shares=c['shares'],account_revision=c['account_revision'],decision_date=c['decision_date'],active_date=c['active_date'],calendar=c['calendar'],strategy_version=c['strategy_version'],target_quantities=c['target_quantities'])
        state=initialize_paper_ledger(plan,'synthetic')
        r=review_plan_bound_observations(state,root=self.source.root,now=self.now)
        self.assertEqual(r['orders'][0]['reason'],'BOUND_SOURCE_BYTES_VERIFIED_NO_COMPLETED_ACTIVE_OBSERVATION')
        self.assertEqual(r['orders'][0]['observed_touch'],'UNKNOWN')
        (self.source.root/'AAA.response.bin').write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):
            review_plan_bound_observations(state,root=self.source.root,now=self.now)

    def test_missing_and_old_observation_unknown_without_mutation(self):
        before=deepcopy(self.state)
        self.assertEqual(self.review([])['orders'][0]['observed_touch'],'UNKNOWN')
        old,pins=self.prepared();r=self.review([old],pins)
        self.assertEqual(r['orders'][0]['observed_touch'],'UNKNOWN');self.assertFalse(r['observation_audit'][0]['used_for_active_session_range'])
        self.assertEqual(self.state,before)
    def test_exact_completed_active_bar_only_describes_range(self):
        row,pins=self.prepared('2026-10-14');r=self.review([row],pins)
        self.assertEqual(r['orders'][0]['observed_touch'],'YES');self.assertEqual(r['generated_fill_count'],0)
        self.assertFalse(r['orders'][0]['missed_trade_established'])
        with self.assertRaisesRegex(ValueError,'NOT_COMPLETED'):
            self.review([row],pins,now=datetime.fromisoformat('2026-10-14T15:59:59-04:00'))
    def test_missing_admission_identity_and_source_tamper_rejected(self):
        row,pins=self.prepared()
        with self.assertRaisesRegex(ValueError,'NOT_ADMITTED'):self.review([row])
        wrong=dict(row,ticker='OTHER')
        with self.assertRaisesRegex(ValueError,'SECURITY'):self.review([wrong],pins)
        (self.source.root/'AAA.response.bin').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):self.review([row],pins)

if __name__=='__main__':unittest.main()

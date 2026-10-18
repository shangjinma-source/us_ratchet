from copy import deepcopy
from datetime import datetime
import hashlib,json,unittest
from data.current_research_observation_registry import PlanObservationLoader,SCHEMA
from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_fill_ledger import initialize_paper_ledger,apply_paper_fill
from test_current_research_plan_observation import PlanObservationTests

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.f=PlanObservationTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.source.root;self.f.source.channel['events']={}
        row,pins=self.f.prepared('2026-10-14')
        c=deepcopy(self.f.state['plan']['causal_inputs'])
        market=dict(date='2026-10-14',timezone='America/New_York',open_at='2026-10-14T09:30:00-04:00',close_at='2026-10-14T16:00:00-04:00')
        c['research_snapshot']['market_session']=market
        plan=build_current_research_limit_plan(research_snapshot=c['research_snapshot'],quotes=[dict(v,security_id=k) for k,v in c['quotes'].items()],**{k:c[k] for k in ['available_cash','shares','account_revision','decision_date','active_date','calendar','strategy_version','target_quantities']})
        self.state=initialize_paper_ledger(plan,'paper-test');self.now=self.f.now
        (self.root/'official.txt').write_text('synthetic reviewed official session evidence')
        calendar=dict(status='REVIEWED_OFFICIAL_SESSION_CALENDAR',source_references=['official.txt'],sessions={'2026-10-14':market})
        (self.root/'calendar.json').write_text(json.dumps(calendar))
        for name in ['official.txt','calendar.json']:pins[name]=hashlib.sha256((self.root/name).read_bytes()).hexdigest()
        self.bundle=dict(account_id='paper-test',plan_id=plan['plan_id'],research_id=plan['research_id'],active_date=plan['active_date'],source_hashes=pins,calendar_path='calendar.json',observed_through=plan['active_date'],observations=[row],unit_continuity={'A':dict(status='NO_UNPROCESSED_ACTIONS',from_date=plan['causal_inputs']['decision_date'],to_date=plan['active_date'],price_basis='CONDITIONAL',source_references=['official.txt'])},admission=dict(status='ACCEPTED_CONDITIONAL_OBSERVATION',reviewer='synthetic',reviewed_at='2026-10-15T13:00:00-04:00',evidence_references=['official.txt'],limitations=['Synthetic; daily touch is not fill.']))
        self.loader=PlanObservationLoader(root=self.root,registry_path='registry.json')
    def save(self):
        raw=json.dumps(self.bundle).encode();(self.root/'bundle.json').write_bytes(raw)
        self.entry={k:self.bundle[k] for k in ['account_id','plan_id','research_id','active_date']}
        self.entry.update(bundle_path='bundle.json',sha256=hashlib.sha256(raw).hexdigest())
        (self.root/'registry.json').write_text(json.dumps(dict(schema=SCHEMA,entries=[self.entry])))
    def test_completed_touch_no_fill_and_current_revision(self):
        self.save();before=deepcopy(self.state);r=self.loader.review(self.state,now=self.now)
        self.assertEqual(r['orders'][0]['observed_touch'],'YES');self.assertEqual(r['generated_fill_count'],0);self.assertEqual(self.state,before)
        p=self.state['plan'];new=apply_paper_fill(self.state,dict(event_id='f',mode='PAPER_MANUAL_FILL',plan_id=p['plan_id'],order_id=p['orders'][0]['order_id'],qty=1,price='10',fees='0',session=p['active_date'],expected_revision=self.state['revision']))
        self.assertEqual(self.loader.review(new,now=self.now)['revision'],new['revision'])
    def test_missing_or_other_account_none_unknown_current_binding_rejected(self):
        self.assertIsNone(self.loader.review(self.state,now=self.now));self.save()
        registry=dict(schema=SCHEMA,entries=[dict(self.entry,account_id='other')]);(self.root/'registry.json').write_text(json.dumps(registry))
        self.assertIsNone(self.loader.review(self.state,now=self.now))
        registry['entries']=[dict(self.entry,plan_id='bad')];(self.root/'registry.json').write_text(json.dumps(registry))
        with self.assertRaisesRegex(ValueError,'UNKNOWN_ACCOUNT_PLAN'):self.loader.review(self.state,now=self.now)
    def test_raw_split_cannot_be_overridden_by_continuity_claim(self):
        self.f.source.channel['events']={'splits':{'x':dict(date=1791984600,numerator=2,denominator=1,splitRatio='2:1')}}
        row,pins=self.f.prepared('2026-10-14')
        self.bundle['observations']=[row];self.bundle['source_hashes'].update(pins);self.save()
        with self.assertRaisesRegex(ValueError,'UNPROCESSED_CORPORATE_ACTION'):
            self.loader.review(self.state,now=self.now)

    def test_capture_after_review_or_future_capture_rejected(self):
        for received in ['2026-10-15T18:00:00+00:00','2026-10-16T12:00:00+00:00']:
            self.f.source.received=received
            self.f.source.read()
            for suffix,key in [('.response.bin','raw_sha256'),('.receipt.json','receipt_sha256'),('.decoded.json','decoded_sha256')]:
                name='AAA'+suffix;digest=hashlib.sha256((self.root/name).read_bytes()).hexdigest()
                self.bundle['source_hashes'][name]=digest
                self.bundle['observations'][0]['entry'][key]=digest
            self.save()
            with self.assertRaisesRegex(ValueError,'CAPTURE_AFTER_REVIEW'):
                self.loader.review(self.state,now=self.now)

    def test_tamper_root_and_unit_or_time_rejected(self):
        original=deepcopy(self.bundle)
        for change in [lambda b:b['unit_continuity']['A'].update(price_basis='wrong'),lambda b:b['admission'].update(reviewed_at='2026-10-14T15:00:00-04:00'),lambda b:b.update(research_id='bad')]:
            self.bundle=deepcopy(original);change(self.bundle);self.save()
            with self.assertRaises(ValueError):self.loader.review(self.state,now=self.now)
        self.bundle=original;self.save();(self.root/'official.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):self.loader.review(self.state,now=self.now)
        with self.assertRaisesRegex(ValueError,'OUTSIDE_ROOT'):PlanObservationLoader(root=self.root,registry_path='../registry.json').review(self.state,now=self.now)

if __name__=='__main__':unittest.main()

from copy import deepcopy
import hashlib,json,unittest
from unittest.mock import patch
from test_current_research_observation_registry import RegistryTests
from data.current_research_observation_prepare import prepare_observation_input,export_observation_input
from data.current_research_observation_registry import review_registered_plan_observations
from data.current_research_paper_service import CurrentResearchPaperService

class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.f=RegistryTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;b=self.f.bundle;session=self.f.state['plan']['causal_inputs']['research_snapshot']['market_session']
        session=dict(session,source_references=['official.txt'])
        schedule=dict(schema='SCHEDULED_REGULAR_SESSIONS_V1',calendar=[session['date']],sessions=[session],source_hashes={'official.txt':b['source_hashes']['official.txt']})
        (self.root/'schedule.json').write_text(json.dumps(schedule));pins=deepcopy(b['source_hashes']);pins['schedule.json']=hashlib.sha256((self.root/'schedule.json').read_bytes()).hexdigest()
        row=b['observations'][0];raw={k:row[k] for k in ['ticker','expected_security_type','relative_directory','entry']};raw['price_basis']='CONDITIONAL'
        self.kw=dict(root=self.root,raw_sources={'A':raw},source_hashes=pins,unit_continuity=b['unit_continuity'],admission=b['admission'],calendar_path='schedule.json',now=self.f.now,output_directory='export')
    def test_prepare_export_loader_service_and_createonly(self):
        before=deepcopy(self.f.state);prepared=prepare_observation_input(self.f.state,**self.kw)
        self.assertFalse((self.root/'export').exists())
        exported=export_observation_input(prepared,self.f.state,root=self.root,now=self.f.now)
        self.assertFalse((self.root/'export/validation.pending.json').exists())
        service=CurrentResearchPaperService(root=self.root,clock=lambda:self.f.now)
        with patch.object(service,'_read_account',return_value=self.f.state),patch('data.current_research_paper_service.review_registered_plan_observations',side_effect=lambda state,**kw:review_registered_plan_observations(state,registry_path=exported['registry_path'],**kw)):
            result=service.review(self.f.state['account_id'])
        self.assertEqual(result['market_review']['orders'][0]['observed_touch'],'YES')
        self.assertEqual(result['market_review']['generated_fill_count'],0);self.assertEqual(self.f.state,before)
        with self.assertRaisesRegex(ValueError,'CREATE_ONLY'):export_observation_input(prepared,self.f.state,root=self.root,now=self.f.now)
    def test_missing_or_old_active_data_and_time_rejected_without_export(self):
        with self.assertRaises(ValueError):prepare_observation_input(self.f.state,**dict(self.kw,raw_sources={}))
        early=deepcopy(self.kw);early['admission']['reviewed_at']='2026-10-14T15:00:00-04:00'
        with self.assertRaisesRegex(ValueError,'SESSION_NOT_COMPLETED'):prepare_observation_input(self.f.state,**early)
        self.f.source=self.f.f.source
        self.f.source.channel['indicators']['quote'][0]['close'][1]=None
        self.f.source.read()
        for suffix,key in [('.response.bin','raw_sha256'),('.receipt.json','receipt_sha256'),('.decoded.json','decoded_sha256')]:
            name='AAA'+suffix;h=hashlib.sha256((self.root/name).read_bytes()).hexdigest();self.kw['source_hashes'][name]=h;self.kw['raw_sources']['A']['entry'][key]=h
        with self.assertRaises(ValueError):prepare_observation_input(self.f.state,**self.kw)
        self.assertFalse((self.root/'export').exists())
    def test_future_capture_and_unit_action_rejected(self):
        source=self.f.f.source
        for case in ['future','split']:
            source.received='2099-01-01T00:00:00+00:00' if case=='future' else '2026-10-15T12:00:00+00:00'
            source.channel['events']={} if case=='future' else {'splits':{'x':dict(date=1791984600,numerator=2,denominator=1,splitRatio='2:1')}}
            source.read()
            for suffix,key in [('.response.bin','raw_sha256'),('.receipt.json','receipt_sha256'),('.decoded.json','decoded_sha256')]:
                name='AAA'+suffix;h=hashlib.sha256((self.root/name).read_bytes()).hexdigest();self.kw['source_hashes'][name]=h;self.kw['raw_sources']['A']['entry'][key]=h
            with self.assertRaisesRegex(ValueError,'CAPTURE_AFTER_REVIEW' if case=='future' else 'UNPROCESSED_CORPORATE_ACTION'):
                prepare_observation_input(self.f.state,**self.kw)
        self.assertFalse((self.root/'export').exists())

    def test_document_level_calendar_evidence_and_declared_bad_refs(self):
        path=self.root/'schedule.json'
        original=json.loads(path.read_bytes())
        def install(schedule):
            path.write_text(json.dumps(schedule),encoding='utf-8')
            self.kw['source_hashes']['schedule.json']=hashlib.sha256(path.read_bytes()).hexdigest()
        schedule=deepcopy(original)
        schedule['sessions'][0].pop('source_references',None)
        schedule['sessions'][0].pop('source',None)
        install(schedule)
        prepared=prepare_observation_input(self.f.state,**self.kw)
        self.assertIn('schedule.json',prepared['derived_calendar']['source_references'])
        self.assertIn('official.txt',prepared['derived_calendar']['source_references'])
        self.assertFalse((self.root/'export').exists())
        for declaration in ({'source_references':[]},{'source_references':['absent']},
                            {'source_references':None},{'source':''},{'source':'absent'},
                            {'source_references':[],'source':'official.txt'}):
            bad=deepcopy(schedule);bad['sessions'][0].update(declaration);install(bad)
            with self.assertRaisesRegex(ValueError,'UNPINNED_EVIDENCE'):
                prepare_observation_input(self.f.state,**self.kw)
        install(schedule)
        (self.root/'official.txt').write_text('drifted evidence')
        with self.assertRaises(ValueError):prepare_observation_input(self.f.state,**self.kw)
        self.assertFalse((self.root/'export').exists())

    def test_registry_tamper_rejected_before_writes(self):
        prepared=prepare_observation_input(self.f.state,**self.kw)
        prepared['registry']['entries'][0]['bundle_path']='other/bundle.json'
        with self.assertRaisesRegex(ValueError,'REGISTRY_CHANGED'):
            export_observation_input(prepared,self.f.state,root=self.root,now=self.f.now)
        self.assertFalse((self.root/'export').exists())

    def test_failed_export_never_publishes_registry(self):
        prepared=prepare_observation_input(self.f.state,**self.kw)
        (self.root/'official.txt').write_text('changed after preparation')
        with self.assertRaises(ValueError):export_observation_input(prepared,self.f.state,root=self.root,now=self.f.now)
        self.assertFalse((self.root/'export/registry.json').exists())
        self.assertFalse((self.root/'export/validation.pending.json').exists())

if __name__=='__main__':unittest.main()

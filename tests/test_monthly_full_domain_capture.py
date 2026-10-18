import copy
import gzip
import json
import unittest
from datetime import datetime
from urllib.parse import urlparse
import test_current_research_close_capture as fixture
from scripts.monthly_full_domain_capture import run, digest, SCHEMA


class FullDomainCaptureTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture.CloseCaptureTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root
        self.symbols=['AAA','BBB','CCC','DDD','EEE','FFF'];self.calls=[]
        membership=dict(schema='ndx_current_quote_list_observation_v1',observed_symbols=self.symbols,
            observed_security_count=6,point_in_time_membership_verified=False)
        raw=json.dumps(membership).encode();(self.root/'members.json').write_bytes(raw)
        self.plan=dict(self.fixture.manifest,schema=SCHEMA,membership_path='members.json',
            membership_source_hashes={'members.json':digest(raw)},
            securities=[dict(ticker=t,security_id='declared:'+t,security_type='EQUITY') for t in self.symbols])
    def fetch(self,url,**kwargs):
        ticker=urlparse(url).path.rsplit('/',1)[-1];self.calls.append(ticker)
        channel=copy.deepcopy(self.fixture.f.channel);channel['meta']['symbol']=ticker
        return dict(raw=gzip.compress(json.dumps({'chart':{'error':None,'result':[channel]}}).encode()),
            http_status=200,final_url=url,response_headers={})
    def invoke(self,**kwargs):
        raw=json.dumps(self.plan).encode();(self.root/'plan.json').write_bytes(raw)
        args=dict(root=self.root,capture=True,fetch=self.fetch,clock=lambda:self.fixture.now);args.update(kwargs)
        return run('plan.json',digest(raw),**args)
    def test_default_preflight_and_preclose_make_no_output_or_requests(self):
        self.assertEqual(self.invoke(capture=False)['batch_count'],2)
        self.fixture.now=datetime.fromisoformat('2026-10-13T19:59:59+00:00')
        with self.assertRaisesRegex(ValueError,'SESSION_NOT_CLOSED'):self.invoke()
        self.assertEqual(self.calls,[]);self.assertFalse((self.root/'capture').exists())
    def test_complete_six_names_two_batches_and_no_retry(self):
        result=self.invoke()
        self.assertEqual(result['status'],'DECLARED_DOMAIN_CAPTURED_NOT_ADMITTED',result)
        self.assertEqual(result['validated_count'],6);self.assertEqual(len(result['batches']),2)
        self.assertEqual(self.calls,self.symbols);self.assertFalse(result['training_admitted'])
        with self.assertRaisesRegex(ValueError,'NO_RETRY'):self.invoke()
        self.assertEqual(len(self.calls),6)
    def test_missing_or_duplicate_domain_rejected_before_network(self):
        self.plan['securities'][-1]=self.plan['securities'][0]
        with self.assertRaisesRegex(ValueError,'DUPLICATE_OR_MISSING'):self.invoke()
        self.assertEqual(self.calls,[]);self.assertFalse((self.root/'capture').exists())
    def test_partial_transport_failure_cannot_claim_complete(self):
        def fetch(url,**kwargs):
            if '/CCC?' in url:raise OSError('synthetic unavailable')
            return self.fetch(url,**kwargs)
        result=self.invoke(fetch=fetch)
        self.assertEqual(result['status'],'INCOMPLETE_NOT_ADMITTED');self.assertEqual(result['validated_count'],5)
    def test_source_change_during_final_batch_cannot_publish(self):
        def fetch(url,**kwargs):
            result=self.fetch(url,**kwargs)
            if '/FFF?' in url:(self.root/'members.json').write_bytes(b'changed')
            return result
        with self.assertRaisesRegex(ValueError,'FULL_DOMAIN_SOURCE_CHANGED'):self.invoke(fetch=fetch)
        self.assertFalse((self.root/'capture/completion_index.json').exists())
    def test_unresolved_identity_preserves_full_domain_without_fake_sid(self):
        self.plan['securities'][-1]['security_id']=None
        result=self.invoke()
        self.assertEqual(result['status'],'DECLARED_DOMAIN_CAPTURED_IDENTITY_UNRESOLVED_NOT_ADMITTED')
        self.assertEqual(result['declared_count'],6);self.assertEqual(result['validated_count'],5)
        self.assertEqual(result['unresolved_transport_saved_count'],1)
        entry=next(e for e in result['entries'] if e['ticker']=='FFF')
        self.assertIsNone(entry['security_id']);self.assertEqual(entry['identity_status'],'UNRESOLVED')
        self.assertFalse(result['training_admitted']);self.assertEqual(set(self.calls),set(self.symbols))


if __name__=='__main__':unittest.main()

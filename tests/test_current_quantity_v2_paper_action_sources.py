import unittest,json
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from unittest.mock import patch
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources,fetch_daily_actions

class SourcesTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,2,17,tzinfo=timezone.utc);self.calls=[]
        self.request=dict(account_id='a',state_revision='r',window_start='2026-10-01T13:30:00+00:00',observed_floor=self.now.isoformat(),
            securities={'OLD':{'ticker':'OLD'},'NEW':{'ticker':'NEW'}},current_target_quantities={'NEW':2})
    def daily(self,ticker,start,end):
        self.calls.append(ticker)
        return dict(status=200,body=json.dumps({'ticker':ticker,'events':{'dividends':{'x':{'date':1,'amount':2}}}}).encode())
    def rss(self):self.calls.append('RSS');return dict(status=200,body=b'<rss>original</rss>')
    def source(self,**kwargs):return PaperActionEvidenceSources(fetch=kwargs.get('fetch',self.daily),rss_fetch=self.rss,clock=lambda:self.now)
    def test_original_bytes_complete_domain_and_frozen_read(self):
        source=self.source();self.assertEqual(self.calls,[]);p=source.capture(self.request)
        self.assertEqual(self.calls,['NEW','OLD','RSS']);self.assertEqual(set(p['documents']['action_receipts']),{'OLD','NEW'})
        for path,h in p['source_hashes'].items():self.assertEqual(sha256(p['files'][path]).hexdigest(),h)
        receipt=json.loads(p['files'][p['documents']['action_receipts']['OLD']]);self.assertEqual(receipt['events_requested'],['dividends','splits'])
        self.assertLessEqual(receipt['requested_from'],self.request['window_start']);self.assertEqual(receipt['requested_through'],self.now.isoformat())
        self.assertIn(b'dividends',p['files'][receipt['raw_path']]);p['files'].clear();self.assertTrue(source.read(self.request)['files']);self.assertEqual(len(self.calls),3)
        self.now+=timedelta(seconds=120)
        with self.assertRaises(ValueError):source.read(self.request)
    def test_failure_clears_prior_snapshot_and_ambiguous_identity(self):
        source=self.source();source.capture(self.request);source.fetch=lambda *a:dict(status=302,body=b'x')
        with self.assertRaises(ValueError):source.capture(self.request)
        with self.assertRaises(ValueError):source.read(self.request)
        self.request['securities']['NEW']['ticker']='OLD';before=len(self.calls)
        with self.assertRaises(ValueError):source.capture(self.request)
        self.assertEqual(len(self.calls),before)
    def test_slow_capture_rollback_empty_and_size(self):
        def slow(*args):self.now+=timedelta(seconds=120);return dict(status=200,body=b'x')
        with self.assertRaises(ValueError):self.source(fetch=slow).capture(self.request)
        self.request['observed_floor']=self.now.isoformat();self.request['securities']={};self.request['current_target_quantities']={}
        source=self.source();p=source.capture(self.request);self.assertEqual(p['files'],{});self.assertEqual(self.calls,[])
        self.now-=timedelta(seconds=1)
        with self.assertRaises(ValueError):source.read(self.request)
        self.setUp()
        with patch('data.current_quantity_v2_paper_action_sources.MAX_TOTAL_BYTES',1):
            with self.assertRaises(ValueError):self.source().capture(self.request)
    def test_default_transport_fixed_url_timeout_no_redirect_bounded_read(self):
        class Response:
            code=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):self.n=n;return b'original'
        response=Response()
        with patch('data.current_quantity_v2_paper_action_sources.build_opener') as build:
            build.return_value.open.return_value=response
            result=fetch_daily_actions('A',self.now-timedelta(days=1),self.now)
            args,kwargs=build.return_value.open.call_args
            self.assertEqual(kwargs['timeout'],15);self.assertIn('events=div%2Csplits',args[0].full_url)
            self.assertEqual(type(build.call_args.args[0]).__name__,'NoRedirect');self.assertEqual(response.n,4*1024*1024+1)
            self.assertEqual(result['body'],b'original')

if __name__=='__main__':unittest.main()

import os
import importlib.util,sys,tempfile,unittest,json
from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
from copy import deepcopy
from core.strategy_account_ledger import canonical
from data.current_quantity_v2_paper_action_sources import daily_url,stamp
from scripts.current_research_official_alert_capture import URL
MODULE=Path(os.environ.get('REENTRY_CANDIDATE_ROOT', '.'))/'data/reentry_reference_evidence_v1.py'
spec=importlib.util.spec_from_file_location('reference_source_candidate',MODULE);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class SourceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.now='2026-10-07T21:00:00Z';self.days=['2026-10-02','2026-10-05','2026-10-06','2026-10-07']
  self.lock=dict(security_id='S',unit_id='u1',exit_session=self.days[0],reference_price='100')
  calendar={'schema':'FIXED_EXCHANGE_SESSIONS_V1','exchange':'NASDAQ','sessions':[dict(date=d,open=d+'T13:30:00Z',close=d+'T20:00:00Z') for d in self.days]}
  identityraw=self.put('identity_source.txt',b'Explicitly synthetic issuer ABC S identity')
  identity=self.put('identity.json',{'candidates':[dict(ticker='ABC',security_id='S',status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['identity_source.txt'])],'source_hashes':{'identity_source.txt':identityraw['sha256']}})
  self.series={'meta':dict(symbol='ABC',currency='USD',instrumentType='EQUITY',exchangeName='NMS',longName='Synthetic Corporation'),'timestamp':[int(stamp(d+'T13:30:00Z').timestamp()) for d in self.days],'indicators':{'quote':[{'close':[100,90,101,80]}],'adjclose':[{'adjclose':[100,90,101,80]}]},'events':{}}
  raw=self.put('daily.json',{'chart':{'error':None,'result':[self.series]}});self.receipt=dict(security_id='S',ticker='ABC',http_status=200,body_truncated=False,transport_error=None,raw_sha256=raw['sha256'],stored_bytes=(self.root/'daily.json').stat().st_size,requested_from='2026-10-02T13:30:00Z',requested_through='2026-10-07T20:30:00Z',received_at='2026-10-07T20:31:00Z',interval='1d',events_requested=['dividends','splits'])
  self.receipt.update(url=daily_url('ABC',stamp(self.receipt['requested_from']),stamp(self.receipt['requested_through'])),request_period1=int(stamp(self.receipt['requested_from']).timestamp()),request_period2=int(stamp(self.receipt['requested_through']).timestamp())+1)
  rss=b'<rss><channel><pubDate>Wed, 07 Oct 2026 20:58:30 GMT</pubDate><item><title>Unrelated issuer ZZZ scheduled notice</title><description>ZZZ corporate notice</description><pubDate>Wed, 07 Oct 2026 20:58:30 GMT</pubDate><link>https://www.nasdaqtrader.com/TraderNews.aspx?id=TEST</link></item></channel></rss>'
  rssref=self.put('rss.xml',rss);rr=self.put('rss_receipt.json',dict(url=URL,http_status=200,body_truncated=False,transport_error=None,raw_sha256=rssref['sha256'],stored_bytes=len(rss),started_at='2026-10-07T20:59:00Z',received_at='2026-10-07T20:59:10Z'))
  self.config=dict(notice_scope_reviewer=self.put('notice_scope.py',Path(mod.notice_scope.__file__).read_bytes()),schema='SERVER_REFERENCE_INTERVAL_V1',reviewer_sha256=sha256(MODULE.read_bytes()).hexdigest(),origin_security_id='S',origin_unit_id='u1',exit_session=self.days[0],decision_session=self.days[-1],calendar=self.put('calendar.json',calendar),approved_actions=self.put('actions.json',dict(schema='SERVER_APPROVED_REFERENCE_ACTIONS_V1',facts=[])),segments=[dict(identity=identity,ticker='ABC',security_id='S',exchange='NMS',unit_id='u1',start_session=self.days[0],end_session=self.days[-1],price_basis='ARCHIVED_SAME_UNIT_RAW_CLOSE',raw=raw,receipt=self.put('receipt.json',self.receipt))],official_rss=dict(raw=rssref,receipt=rr))
 def put(self,name,value):
  raw=value if isinstance(value,bytes) else canonical(value);(self.root/name).write_bytes(raw);return dict(path=name,sha256=sha256(raw).hexdigest())
 def refresh_daily(self):
  ref=self.put('daily.json',{'chart':{'error':None,'result':[self.series]}});self.receipt.update(raw_sha256=ref['sha256'],stored_bytes=(self.root/'daily.json').stat().st_size);self.config['segments'][0].update(raw=ref,receipt=self.put('receipt.json',self.receipt))
 def run_review(self):return mod.review_reference_interval(root=self.root,configuration_reference=self.put('config.json',self.config),lock=self.lock,decision_session=self.days[-1],as_of=self.now)
 def assertWait(self,reason=None):
  result=self.run_review();self.assertEqual(result['status'],'WAIT_REFERENCE_SOURCE',result)
  if reason:self.assertIn(reason,result['reason'])
 def test_full_constant_unit_and_ever_recovery_input(self):
  r=self.run_review();self.assertEqual(r['status'],'REFERENCE_SOURCE_REVIEWED_CONDITIONAL',r);self.assertEqual([v['close'] for v in r['evidence']['rows']],['90','101','80']);self.assertFalse(r['coverage_complete'])
 def test_raw_byte_tamper(self):(self.root/'daily.json').write_bytes(b'tampered');self.assertWait('HASH')
 def test_wrong_request_url(self):self.receipt['url']='https://evil.invalid';self.refresh_daily();self.assertWait('REQUEST_IDENTITY')
 def test_missing_middle_bar(self):
  del self.series['timestamp'][1];del self.series['indicators']['quote'][0]['close'][1];del self.series['indicators']['adjclose'][0]['adjclose'][1];self.refresh_daily();self.assertWait('MISSING_TRADING')
 def test_wrong_symbol(self):self.series['meta']['symbol']='ZZZ';self.refresh_daily();self.assertWait('CHART_IDENTITY')
 def test_truncated(self):self.receipt['body_truncated']=True;self.refresh_daily();self.assertWait('DAILY_RECEIPT')
 def test_uncompleted(self):self.now='2026-10-07T19:00:00Z';self.assertWait('UNCOMPLETED')
 def test_raw_adjustment_without_approved_cash(self):self.series['indicators']['adjclose'][0]['adjclose'][0]=99;self.refresh_daily();self.assertWait('NOMINAL')
 def test_exit_anchor_mismatch(self):self.lock['reference_price']='99';self.assertWait('ANCHOR')
 def test_unknown_action(self):self.series['events']={'capitalGains':{'x':{'date':int(stamp('2026-10-05T13:30:00Z').timestamp()),'amount':1}}};self.refresh_daily();self.assertWait('APPROVED')
 def cash(self):
  payload=dict(date=int(stamp('2026-10-05T13:30:00Z').timestamp()),amount=.04);event=dict(kind='dividends',key='x',payload=payload);self.series['events']={'dividends':{'x':payload}}
  body=b'Synthetic Corporation will pay its next quarterly cash dividend of $0.04 per share on October 7, 2026 to shareholders of record on October 5, 2026.';raw=self.put('official.txt',body);url='https://issuer.example.test/release';receipt=self.put('official_receipt.json',dict(http_status=200,body_truncated=False,transport_error=None,raw_sha256=raw['sha256'],stored_bytes=len(body),url=url,started_at='2026-10-07T20:00:00Z',received_at='2026-10-07T20:01:00Z'))
  fact=dict(security_id='S',provider_event_sha256=sha256(canonical(event)).hexdigest(),kind='ORDINARY_CASH_DIVIDEND',event_session='2026-10-05',currency='USD',unit_change=False,nominal_amount='.04',record_date='2026-10-05',payment_date='2026-10-07',record_quote='shareholders of record on October 5, 2026',payment_quote='cash dividend of $0.04 per share on October 7, 2026',issuer_name='Synthetic Corporation',quote='cash dividend of $0.04 per share',official_raw=raw,official_receipt=receipt,official_url=url)
  self.config['approved_actions']=self.put('actions.json',dict(schema='SERVER_APPROVED_REFERENCE_ACTIONS_V1',facts=[fact]));self.refresh_daily();return fact
 def test_cash_does_not_adjust_nominal(self):
  self.cash();r=self.run_review();self.assertEqual(r['status'],'REFERENCE_SOURCE_REVIEWED_CONDITIONAL',r);self.assertEqual(r['evidence']['rows'][0]['close'],'90');self.assertNotIn('cash_credit',r)
 def test_cash_changed_amount_observation(self):self.cash();self.series['events']['dividends']['x']['amount']=.4;self.refresh_daily();self.assertWait('APPROVED')
 def test_cash_quote_not_just_label(self):
  f=self.cash();f['nominal_amount']='.4';self.config['approved_actions']=self.put('actions.json',dict(schema='SERVER_APPROVED_REFERENCE_ACTIONS_V1',facts=[f]));self.assertWait('QUOTE_AMOUNT')
 def test_stale_rss_does_not_refresh(self):self.now='2026-10-07T22:00:00Z';self.assertWait('NOTICE_RECEIPT')
 def test_relevant_notice(self):
  text=(self.root/'rss.xml').read_bytes().replace(b'ZZZ',b'ABC');ref=self.put('rss.xml',text);r=json.loads((self.root/'rss_receipt.json').read_bytes());r.update(raw_sha256=ref['sha256'],stored_bytes=len(text));self.config['official_rss']=dict(raw=ref,receipt=self.put('rss_receipt.json',r));self.assertWait('KNOWN_ACTION')
 def test_rss_truncated_or_future_rejected(self):
  r=json.loads((self.root/'rss_receipt.json').read_bytes());r['body_truncated']=True;self.config['official_rss']['receipt']=self.put('rss_receipt.json',r);self.assertWait('NOTICE_RECEIPT')
  r['body_truncated']=False;raw=(self.root/'rss.xml').read_bytes().replace(b'Wed, 07 Oct 2026 20:58:30 GMT</pubDate><link>',b'Wed, 07 Oct 2026 22:58:30 GMT</pubDate><link>');ref=self.put('rss.xml',raw);r.update(raw_sha256=ref['sha256'],stored_bytes=len(raw));self.config['official_rss']=dict(raw=ref,receipt=self.put('rss_receipt.json',r));self.assertWait('KNOWN_ACTION')
 def test_exact_reviewed_future_notice_retains_clock(self):
  from xml.sax.saxutils import escape
  ident,signature=next(iter(mod.notice_scope.VERIFIED_UNRELATED_FUTURE_NOTICES.items()));category,title,description=signature
  raw=('<rss><channel><pubDate>Wed, 07 Oct 2026 20:58:30 GMT</pubDate><item><title>'+escape(title)+'</title><description>'+escape(description)+'</description><NewsCategory>'+escape(category)+'</NewsCategory><pubDate>Wed, 07 Oct 2026 22:58:30 GMT</pubDate><link>http://www.nasdaqtrader.com/TraderNews.aspx?id='+ident+'</link></item></channel></rss>').encode()
  ref=self.put('rss.xml',raw);r=json.loads((self.root/'rss_receipt.json').read_bytes());r.update(raw_sha256=ref['sha256'],stored_bytes=len(raw));self.config['official_rss']=dict(raw=ref,receipt=self.put('rss_receipt.json',r))
  result=self.run_review();self.assertEqual(result['status'],'REFERENCE_SOURCE_REVIEWED_CONDITIONAL',result)
  scope=result['evidence']['notice_scope_reviews'][0];self.assertFalse(scope['original_times_modified']);self.assertEqual(len(scope['ignored_future_items']),1)
 def test_notice_scope_code_tampered(self):
  self.config['notice_scope_reviewer']=self.put('notice_scope.py',b'not actual reviewer');self.assertWait('SCOPE_CODE_CHANGED')
 def test_cash_does_not_authorize_adjusted_prices(self):
  self.cash();self.series['indicators']['adjclose'][0]['adjclose'][0]=99;self.refresh_daily();self.assertWait('NOMINAL')
 def test_integer_split_requires_archived_pre_unit(self):
  old=deepcopy(self.config['segments'][0]);self.series['timestamp']=self.series['timestamp'][:1];self.series['indicators']={'quote':[{'close':[100]}],'adjclose':[{'adjclose':[100]}]};self.receipt.update(requested_through='2026-10-02T20:30:00Z',received_at='2026-10-02T20:31:00Z');self.receipt.update(url=daily_url('ABC',stamp(self.receipt['requested_from']),stamp(self.receipt['requested_through'])),request_period2=int(stamp(self.receipt['requested_through']).timestamp())+1);self.refresh_daily();self.config['segments'][0]['end_session']='2026-10-02'
  ir=self.put('identity_new_source.txt',b'Synthetic Corporation DEF N new identity');identity=self.put('identity_new.json',{'candidates':[dict(ticker='DEF',security_id='N',status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['identity_new_source.txt'])],'source_hashes':{'identity_new_source.txt':ir['sha256']}})
  payload=dict(date=int(stamp('2026-10-05T13:30:00Z').timestamp()),numerator=10,denominator=1);event=dict(kind='splits',key='x',payload=payload)
  series={'meta':dict(symbol='DEF',currency='USD',instrumentType='EQUITY',exchangeName='NMS',longName='Synthetic Corporation'),'timestamp':[int(stamp(d+'T13:30:00Z').timestamp()) for d in self.days[1:]],'indicators':{'quote':[{'close':[9,10.1,8]}],'adjclose':[{'adjclose':[9,10.1,8]}]},'events':{'splits':{'x':payload}}}
  raw=self.put('new_daily.json',{'chart':{'error':None,'result':[series]}});r=deepcopy(self.receipt);r.update(security_id='N',ticker='DEF',raw_sha256=raw['sha256'],stored_bytes=(self.root/'new_daily.json').stat().st_size,requested_from='2026-10-05T13:30:00Z',requested_through='2026-10-07T20:30:00Z',received_at='2026-10-07T20:31:00Z');r.update(url=daily_url('DEF',stamp(r['requested_from']),stamp(r['requested_through'])),request_period1=int(stamp(r['requested_from']).timestamp()),request_period2=int(stamp(r['requested_through']).timestamp())+1)
  self.config['segments'].append(dict(identity=identity,ticker='DEF',security_id='N',exchange='NMS',unit_id='u2',start_session=self.days[1],end_session=self.days[-1],price_basis='ARCHIVED_SAME_UNIT_RAW_CLOSE',raw=raw,receipt=self.put('new_receipt.json',r)))
  body=b'Synthetic Corporation 10-for-1 stock split. CUSIP 111111111 changes to 222222222. Effective before market open on October 5, 2026.';oref=self.put('split_official.txt',body);url='https://issuer.example.test/split';oreceipt=self.put('split_receipt.json',dict(http_status=200,body_truncated=False,transport_error=None,raw_sha256=oref['sha256'],stored_bytes=len(body),url=url,started_at='2026-10-07T20:00:00Z',received_at='2026-10-07T20:01:00Z'))
  fact=dict(security_id='S',provider_security_id='N',new_security_id='N',old_unit_id='u1',new_unit_id='u2',provider_event_sha256=sha256(canonical(event)).hexdigest(),kind='INTEGER_SPLIT',event_session='2026-10-05',timing='BEFORE_OPEN',effective_quote='Effective before market open on October 5, 2026',ratio='10',old_cusip='111111111',new_cusip='222222222',issuer_name='Synthetic Corporation',quote='10-for-1 stock split',official_raw=oref,official_receipt=oreceipt,official_url=url)
  self.config['approved_actions']=self.put('actions.json',dict(schema='SERVER_APPROVED_REFERENCE_ACTIONS_V1',facts=[fact]))
  result=self.run_review();self.assertEqual(result['status'],'REFERENCE_SOURCE_REVIEWED_CONDITIONAL',result);self.assertEqual(result['evidence']['rows'][0]['conversion']['ratio'],'10');self.assertEqual(result['current_security_id'],'N')
  self.receipt['received_at']='2026-10-07T20:31:00Z';self.config['segments'][0]['receipt']=self.put('receipt.json',self.receipt);self.assertWait('ARCHIVED_PRE_SPLIT')
if __name__=='__main__':unittest.main()

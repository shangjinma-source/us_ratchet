import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from zoneinfo import ZoneInfo
from hashlib import sha256
from unittest.mock import patch
import test_current_quantity_v2_followup_review as fixture_module
from scripts import capture_followup_evidence as m
from data.current_quantity_v2_followup_provider import STORAGE,canonical

class CaptureTests(unittest.TestCase):
 def fixture(self,directory):
  root=Path(directory);f=fixture_module.FollowupTests();f.setUp();self.addCleanup(f.doCleanups)
  event=f.event;event.update(event_id='b'*32,request_started_at=event['observed_at'])
  for c in event['captures']:
   previous=c['path'];c['path']='raw/'+c['sha256']+'.bin';f.files[c['path']]=f.files[previous]
  raw=canonical(event);eventpath='events/2026-10-15/'+event['event_id']+'.json'
  files={eventpath:raw,**{c['path']:f.files[c['path']] for c in event['captures']}}
  for path,content in files.items():m.save(root/'data/quantity_v2_observations'/path,content)
  repo=Path(__file__).resolve().parents[1];sources={m.CALENDAR:m.CALENDAR_SHA,m.FORWARD_PATH:m.FORWARD_SHA}
  for path in list(sources):sources.update(json.loads((repo/path).read_bytes())['source_hashes'])
  for path,h in sources.items():
   content=(repo/path).read_bytes();self.assertEqual(sha256(content).hexdigest(),h);m.save(root/path,content)
  args=dict(root=root,event_day='2026-10-15',event_id=event['event_id'],event_sha256=sha256(raw).hexdigest(),**f.binding)
  ticks=[datetime.fromisoformat('2026-10-16T22:00:00+00:00')];calls=[];changed=[False]
  def body():
   calendar=json.loads((root/m.CALENDAR).read_bytes());days=[d for d in calendar['calendar'] if '2026-10-15'<=d<=ticks[0].astimezone(ZoneInfo('America/New_York')).date().isoformat()]
   close=[12 if changed[0] and d=='2026-10-16' else 11 for d in days]
   return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol='AAA',longName='Example Corporation',currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),timestamp=[int(datetime.fromisoformat(d+'T09:30:00-04:00').timestamp()) for d in days],indicators={'quote':[dict(open=close,high=[13]*len(days),low=[10]*len(days),close=close)]},events={})])))
  def fetch(url,**kwargs):calls.append('close');return dict(raw=body(),http_status=200,final_url=url)
  def action(ticker,start,end):calls.append('action');return dict(body=body(),status=200,url=m.PaperActionEvidenceSources.__module__ and __import__('data.current_quantity_v2_paper_action_sources',fromlist=['daily_url']).daily_url(ticker,start,end))
  def rss():
   calls.append('rss');return dict(status=200,body=('<rss><channel><item><title>Unrelated news</title><pubDate>'+ticks[0].strftime('%a, %d %b %Y %H:%M:%S GMT')+'</pubDate></item></channel></rss>').encode())
  args.update(clock=lambda:ticks[0],fetch=fetch,action_fetch=action,rss_fetch=rss)
  return args,ticks,calls,changed
 def test_actual_capture_provider_upgrade_and_repeat(self):
  with TemporaryDirectory() as folder:
   args,ticks,calls,_=self.fixture(folder);root=Path(folder)
   self.assertEqual(m.run(**args)['status'],'PREFLIGHT_ONLY');self.assertEqual(calls,[])
   self.assertFalse((root/STORAGE).exists())
   first=m.run(**args,execute=True);self.assertEqual(first['status'],'FOLLOWUP_PUBLISHED');self.assertEqual(calls,['close','action','rss'])
   self.assertEqual(m.run(**args,execute=True)['status'],'ALREADY_COVERED');self.assertEqual(len(calls),3)
   ticks[0]=datetime.fromisoformat('2026-10-22T22:00:00+00:00')
   second=m.run(**args,execute=True);self.assertEqual(second['matured_horizons'],[1,5]);self.assertEqual(second['previous_manifest_sha256'],first['manifest_sha256'])
   self.assertTrue((root/STORAGE/'bundles'/first['manifest_sha256']).exists());self.assertEqual(len(calls),6)
 def test_dynamic_new_cap_bundle_replays_without_database(self):
  from data.current_quantity_v2_pullback_cap_store import PullbackCapStore
  from data.current_quantity_v2_pullback_chain_source import DATABASE
  from data.current_research_intraday_execution import decode_intraday_reference
  from test_current_quantity_v2_pullback_sources import payload
  with TemporaryDirectory() as folder:
   args,ticks,calls,_=self.fixture(folder);root=Path(folder)
   path=root/'data/quantity_v2_observations/events/2026-10-15'/('b'*32+'.json');event=json.loads(path.read_bytes())
   data=payload();data['chart']['result'][0]['meta']['symbol']='AAA';raw=canonical(data)
   database=root/DATABASE;database.parent.mkdir(parents=True)
   store=PullbackCapStore(database,clock=lambda:'2026-10-15T13:32:30+00:00',max_history_rows=100,max_history_bytes=1000000)
   for second in (15,16):
    captured='2026-10-15T13:32:%s+00:00'%second
    result=store.candidate(raw=raw,expected_sha256=sha256(raw).hexdigest(),security_id='A',ticker='AAA',session='2026-10-15',session_open='2026-10-15T13:30:00+00:00',session_close='2026-10-15T20:00:00+00:00',captured_at=captured,checked_at=captured,now=captured,rebound_fraction='1/2',minimum_discount='1/200',maximum_age_seconds=120)
   ref=decode_intraday_reference(raw,ticker='AAA',now=datetime.fromisoformat(captured),captured_at=datetime.fromisoformat(captured))
   ref['pullback']=dict(result['candidate'],prior_cap=result['frozen_proof']['prior_cap'],cap_record_hash=result['cap_store_receipt']['record_hash'],status='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED')
   event.update(observed_at='2026-10-15T13:32:31+00:00',request_started_at=captured,reference_valid_until=ref['refresh_by'])
   event['orders'][0]['limit_price']=result['candidate']['limit_price'];event['rows'][0].update(reference=ref,limit_price=result['candidate']['limit_price'])
   receipt=canonical(dict(security_id='A',ticker='AAA',raw_path='original.raw',raw_sha256=sha256(raw).hexdigest(),captured_at=captured))
   event['captures']=[]
   for role,source,content in [('ORIGINAL_QUOTE','original.raw',raw),('ORIGINAL_QUOTE_RECEIPT','original.receipt',receipt)]:
    h=sha256(content).hexdigest();relative='raw/'+h+'.bin';m.save(root/'data/quantity_v2_observations'/relative,content)
    event['captures'].append(dict(role=role,security_id='A',ticker='AAA',original_source_path=source,path=relative,sha256=h,captured_at=captured))
   event_raw=canonical(event);path.write_bytes(event_raw);args['event_sha256']=sha256(event_raw).hexdigest()
   published=m.run(**args,execute=True);self.assertEqual(published['status'],'FOLLOWUP_PUBLISHED')
   manifest=json.loads((root/STORAGE/'bundles'/published['manifest_sha256']/'manifest.json').read_bytes())
   self.assertIn(ref['pullback']['cap_record_hash'],manifest['trusted_chain_sources'])
   database.unlink()
   reread=m.FollowupBundleProvider(repository_root=root).review(event_raw=event_raw,binding={k:args[k] for k in ('decision_id','research_version','available_cash_exact')},now=ticks[0])
   self.assertEqual(reread['status'],'EVIDENCE_REVIEW_ONLY');self.assertEqual(reread['orders'][0]['horizons'][0]['status'],'CONDITIONAL_PRICE_CHANGE')
   self.assertFalse(database.exists());self.assertEqual(calls,['close','action','rss'])
   self.assertEqual(m.run(**args,execute=True)['status'],'ALREADY_COVERED');self.assertEqual(len(calls),3)
   ticks[0]=datetime.fromisoformat('2026-10-22T22:00:00+00:00')
   self.assertEqual(m.run(**args,execute=True)['matured_horizons'],[1,5]);self.assertFalse(database.exists());self.assertEqual(len(calls),6)
 def test_conflict_preserves_old_index_and_attempt_not_retried(self):
  with TemporaryDirectory() as folder:
   args,ticks,calls,changed=self.fixture(folder);root=Path(folder);m.run(**args,execute=True)
   index=next((root/STORAGE/'index').rglob('*.json'));before=index.read_bytes();ticks[0]=datetime.fromisoformat('2026-10-22T22:00:00+00:00');changed[0]=True
   with self.assertRaisesRegex(ValueError,'HISTORICAL_DATA_CONFLICT'):m.run(**args,execute=True)
   self.assertEqual(index.read_bytes(),before);count=len(calls)
   pre=m.run(**args);self.assertEqual(pre['status'],'NEEDS_RECOVERY');self.assertEqual(pre['reason'],'PRIOR_CAPTURE_FAILED_REQUIRES_REVIEW');self.assertEqual(len(calls),count)
   with self.assertRaisesRegex(ValueError,'ATTEMPT_EXISTS_NO_RETRY'):m.run(**args,execute=True)
   self.assertEqual(len(calls),count)
 def test_provider_read_index_race_rejects_before_network(self):
  with TemporaryDirectory() as folder:
   args,ticks,calls,_=self.fixture(folder);root=Path(folder);m.run(**args,execute=True)
   index=next((root/STORAGE/'index').rglob('*.json'));ticks[0]=datetime.fromisoformat('2026-10-22T22:00:00+00:00');count=len(calls)
   real=m.FollowupBundleProvider.review;replacement=canonical(dict(manifest_sha256='c'*64))
   def race(provider,**kwargs):
    value=real(provider,**kwargs);index.write_bytes(replacement);return value
   with patch.object(m.FollowupBundleProvider,'review',race):
    with self.assertRaisesRegex(ValueError,'INDEX_CHANGED_DURING_PREFLIGHT'):m.run(**args,execute=True)
   self.assertEqual(index.read_bytes(),replacement);self.assertEqual(len(calls),count)
 def test_old_pending_publication_blocks_new_target_without_capture(self):
  for suffix in ('.pending','.lock'):
   with self.subTest(suffix=suffix),TemporaryDirectory() as folder:
    args,ticks,calls,_=self.fixture(folder);root=Path(folder);m.run(**args,execute=True)
    index=next((root/STORAGE/'index').rglob('*.json'));index.with_suffix(suffix).write_bytes(b'needs recovery')
    ticks[0]=datetime.fromisoformat('2026-10-22T22:00:00+00:00');count=len(calls)
    result=m.run(**args,execute=True);self.assertEqual(result['status'],'NEEDS_RECOVERY')
    self.assertEqual(result['reason'],'INDEX_PUBLICATION_RECOVERY_REQUIRED');self.assertEqual(len(calls),count)
    self.assertFalse((root/STORAGE/'attempts'/args['event_sha256']/'2026-10-22').exists())
 def test_atomic_replace_failure_and_competing_publishers(self):
  from concurrent.futures import ThreadPoolExecutor
  from threading import Barrier
  with TemporaryDirectory() as folder:
   index=Path(folder)/'index.json';old=canonical(dict(manifest_sha256='a'*64));m.save(index,old)
   with patch.object(m.os,'replace',side_effect=OSError('simulated failure')):
    with self.assertRaises(OSError):m.guarded_replace(index,'a'*64,canonical(dict(manifest_sha256='b'*64)))
   self.assertEqual(index.read_bytes(),old);self.assertTrue(index.with_suffix('.pending').exists())
  with TemporaryDirectory() as folder:
   index=Path(folder)/'index.json';m.save(index,old);barrier=Barrier(2)
   def publish(value):
    barrier.wait()
    try:m.guarded_replace(index,'a'*64,canonical(dict(manifest_sha256=value*64)));return 'SUCCESS'
    except (ValueError,FileExistsError):return 'CONFLICT'
   with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(publish,['b','c']))
   self.assertEqual(sorted(outcomes),['CONFLICT','SUCCESS']);self.assertIn(json.loads(index.read_bytes())['manifest_sha256'],['b'*64,'c'*64])
 def test_beforeclose_wrong_binding_and_cas(self):
  with TemporaryDirectory() as folder:
   args,ticks,calls,_=self.fixture(folder);ticks[0]=datetime.fromisoformat('2026-10-16T19:59:00+00:00')
   self.assertEqual(m.run(**args,execute=True)['status'],'WAITING_SESSION_CLOSE');self.assertEqual(calls,[])
   with self.assertRaises(ValueError):m.run(**dict(args,available_cash_exact='1'),execute=True)
   index=Path(folder)/'index.json';m.save(index,canonical(dict(manifest_sha256='a'*64)));before=index.read_bytes()
   with self.assertRaisesRegex(ValueError,'INDEX_CAS_CONFLICT'):m.guarded_replace(index,'b'*64,canonical(dict(manifest_sha256='c'*64)))
   self.assertEqual(index.read_bytes(),before)
   index.with_suffix('.lock').write_bytes(b'competing publisher')
   with self.assertRaises(FileExistsError):m.guarded_replace(index,'a'*64,canonical(dict(manifest_sha256='c'*64)))
   self.assertEqual(index.read_bytes(),before)

if __name__=='__main__':unittest.main()

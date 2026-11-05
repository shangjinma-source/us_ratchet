"""HTTP news job with synthetic official HTML/model, real source recovery and risk."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from fractions import Fraction
import json,socket,threading,time,unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_split_native_capture_configuration_20261105 as fixture
from core.strategy_account_ledger import canonical
from data.news_risk_skill_v1 import PINS,load_risk_skill
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from data.news_sandisk_parser import parse_release
from docs.candidates.split_native_capture_configuration_20261105 import ConfiguredNativeAdmission,digest
from docs.candidates.split_configured_runtime_routes_20261105 import build_configured_app

# Exact synthetic JSON ticker parameterization before any release/selection.
# No textual replacement of source code, SQLite or already-issued authorization.
def prepare_supported_ticker(original, instance):
 original(instance)
 root=instance.root;objects={};raws={}
 for p in root.rglob('*'):
  if not p.is_file() or p.suffix in ('.py','.sqlite3'):continue
  try:obj=json.loads(p.read_bytes())
  except (ValueError,UnicodeError):continue
  objects[p]=obj;raws[p]=p.read_bytes()
 def transform(value,hashes=None):
  if isinstance(value,dict):return {k:transform(v,hashes) for k,v in value.items()}
  if isinstance(value,list):return [transform(v,hashes) for v in value]
  if isinstance(value,str):return (hashes or {}).get(value,'SNDK' if value=='BBB' else value)
  return value
 bodies={p:canonical(transform(v)) for p,v in objects.items()}
 for _ in range(30):
  mapping={digest(raws[p]):digest(raw) for p,raw in bodies.items()}
  updated={p:canonical(transform(v,mapping)) for p,v in objects.items()}
  if updated==bodies:break
  bodies=updated
 else:raise AssertionError('SYNTHETIC_HASH_GRAPH_CYCLE')
 for p,raw in bodies.items():p.write_bytes(raw)
 instance.f.entry=transform(instance.f.entry,mapping);instance.f.identity=transform(instance.f.identity,mapping);instance.second=transform(instance.second,mapping)
 # This is fixture construction before release/selection, not ledger migration.
 # Retain the original temporary database and replay new synthetic source pins
 # through the public store API; never edit SQLite rows or a real account.
 state=instance.store.read();path=instance.store.path
 assert path.resolve().is_relative_to(root.resolve())
 assert root.resolve()!=fixture.fixture.ROOT.resolve()
 path.rename(path.with_name('before-supported-ticker.sqlite3'))
 instance.store.initialize(state['account_id'],operation_id='supported-ticker-fixture')
 for row in state['events']:
  instance.store.append(transform(row['payload'],mapping),expected_revision=instance.store.read()['revision'])


class Tests(unittest.TestCase):
 def test_post_job_get_complete_real_sources_and_account_stale(self):
  helper=fixture.Tests();self.addCleanup(helper.doCleanups)
  original_setup=fixture.fixture.Tests.setUp
  with patch.object(fixture.fixture.Tests,'setUp',lambda obj:prepare_supported_ticker(original_setup,obj)):
   case=helper.case()
  service=case['service'];f=case['f'];view=case['view'];provider=case['provider']
  with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')):
   initial=service.preview(**case['request']);self.assertEqual(initial['status'],'READY')
   target=view.current();proposal=view.require_proposal(target_id=target['target_id'],expected_proposal_id=target['proposal_id'])
   desired=proposal['payload']['proposed_target_quantities']
   for sid in sorted(set(desired)|set(f.store.read()['shares'])):
    held=f.store.read()['shares'].get(sid,0);gap=desired.get(sid,0)-held
    if not gap:continue
    ticker=provider.market.identity(next(r['ticker'] for r in f.f.identity['candidates'] if r['security_id']==sid))['ticker']
    identity=provider.market.identity(ticker)
    f.store.append(dict(event_id='hold-position-'+sid,kind='DIRECT_FILL',security_id=sid,side='BUY' if gap>0 else 'SELL',quantity=abs(gap),price='10',fees='0',executed_at=f.now.isoformat(),identity_evidence=identity),expected_revision=f.store.read()['revision'])
   f.store.append(dict(event_id='hold-cash',kind='CASH_CONFIRM',amount='100',cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=f.store.read()['revision'])
   # Add the actual newly recorded identity source closure to the synthetic server
   # authorization; no source is inferred from browser input or model output.
   config=json.loads(case['configraw']);ref=config['authorizations'][target['target_id']];grant=json.loads((f.root/ref['path']).read_bytes())
   for event in f.store.read()['events']:
    for name,h in event['payload'].get('identity_evidence',{}).get('source_hashes',{}).items():
     raw=(f.root/name).read_bytes();self.assertEqual(digest(raw),h)
     path=f.root/'hold-authority'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);ref['files'][name]=path.relative_to(f.root).as_posix();grant['source_sha256'][name]=h
   (f.root/ref['path']).write_bytes(canonical(grant));ref['sha256']=digest(canonical(grant));(f.root/'native-config.json').write_bytes(canonical(config))
   service=ConfiguredNativeAdmission(**dict(case['arguments'],configuration_sha256=digest(canonical(config))))
   f.now+=timedelta(minutes=1);state=f.store.read();request=dict(expected_revision=state['revision'],target_id=target['target_id'],expected_proposal_id=target['proposal_id'])
   original=service.preview(**request);self.assertEqual(original['status'],'HOLD',original)

  for name in PINS:
   path=f.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((fixture.fixture.ROOT/name).read_bytes())
  self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.start_worker'));self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.stop_worker'))
  prepared=build_configured_app(root=f.root,monthly_view=view,daily_service=service,journal=DailyAdviceJournalV1(f.root/'api-journal.sqlite3'),clock=lambda:f.now,validate_sources=service.validate_code,policy_references={'scope':'SYNTHETIC_NATIVE_NEWS_HTTP'},timing_bundles=case['timing'],account_arguments=dict(database_path=f.store.path,account_id=state['account_id'],resolver=provider.market.identity,clock=lambda:f.now))
  news=prepared['news_service'];news.clock=lambda:f.now
  url='https://www.sandisk.com/company/newsroom/press-releases/2026/isolated-test'
  text='Sandisk synthetic fixture: management lowers its outlook. '+('Controlled complete disclosure for source validation only. '*4)
  raw=('<html><head><link rel="canonical" href="'+url+'"><meta name="article:published_time" content="2026-12-01T14:00:00Z"></head><body><article><h1>Synthetic Sandisk report</h1><p>December 1, 2026</p><div class="para-text">'+text+'</div></article></body></html>').encode()
  observed=f.now.isoformat();event=parse_release(raw,url,observed)['event'];rawhash=digest(raw)
  news.cache.mkdir(parents=True,exist_ok=True);(news.cache/'raw').mkdir(exist_ok=True);(news.cache/'raw'/('sandisk-'+rawhash+'.raw')).write_bytes(raw)
  snapshot=dict(generated_at=observed,events=[event],source_receipts=[dict(url=url,status=200,sha256=rawhash,fetched_at=observed)])
  news.collector=lambda *args,**kwargs:deepcopy(snapshot)
  chosen=[];model_calls=[]
  def model(sources,positions,cache,**kwargs):
   model_calls.append(True);rows=[]
   for position in positions:
    sid=position['security_id'];matches=[s for s in sources if sid in s['security_ids']]
    if position['ticker']=='SNDK':
     self.assertEqual(len(matches),1);source=matches[0];quantity=position['original_qty'];self.assertGreater(quantity,0);chosen.append(sid)
     rows.append(dict(security_id=sid,action='REDUCE_HOLDING',holding_fraction=str(Fraction(quantity-1,quantity)),reason='Synthetic bounded risk opinion',evidence=[dict(source_id=source['id'],source_sha256=source['text_sha256'],quote='management lowers its outlook.')]))
    else:rows.append(dict(security_id=sid,action='ABSTAIN',reason='No supported full text',evidence=[]))
   f.now+=timedelta(seconds=2)
   return dict(status='SUCCEEDED',model='SYNTHETIC_NO_MODEL_CALL',rows=rows,skill_context_binding=load_risk_skill(f.root)['binding'])
  news.model=model
  self.assertIsNone(news.source_builder) # Real raw recovery, parser and binding validator.
  app=prepared['app'];connect=socket.socket.connect
  def offline(sock,address):
   if isinstance(address,tuple) and address[0] in ('127.0.0.1','::1'):return connect(sock,address)
   raise AssertionError('NETWORK_FORBIDDEN')
  workers=[]
  try:
   with patch('socket.socket.connect',offline),TestClient(app) as client:
    response=client.post('/api/news/investment-review',json=request);self.assertEqual(response.status_code,202,response.text)
    job_id=response.json()['job_id'];workers=list(prepared['review_worker_owner'].workers)
    self.assertTrue(workers);deadline=time.monotonic()+300
    while True:
     response=client.get('/api/news/investment-review/job',params={'job_id':job_id});self.assertEqual(response.status_code,200,response.text)
     result=response.json()
     if result['status']!='RUNNING':break
     self.assertLess(time.monotonic(),deadline,'REAL_NEWS_WORKER_TIMEOUT');time.sleep(1)
    self.assertEqual(result['status'],'COMPLETE',result);self.assertEqual(len(model_calls),1)
    proposal=result['proposal'];plan=proposal['risk_plan'];self.assertEqual(plan['status'],'READY',plan)
    self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in plan['candidate_orders']],[(chosen[0],'SELL',1)])
    admitted=[r for r in proposal['coverage'] if r['status']=='ADMITTED_FULL_TEXT'];self.assertEqual(len(admitted),1)
    self.assertFalse(proposal['executable']);self.assertFalse(plan['orders_created']);self.assertEqual(f.store.read(),state)
    f.store.append(dict(event_id='post-news-cash',kind='CASH_CONFIRM',amount='101',cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=state['revision'])
    stale=client.get('/api/news/investment-review/job',params={'job_id':job_id}).json();self.assertEqual(stale['status'],'STALE');self.assertNotIn('proposal',stale)
    prepared['request_drain'].begin()
    refused=client.post('/api/news/investment-review',json=request);self.assertEqual(refused.status_code,503,refused.text)
   self.assertTrue(prepared['review_worker_owner'].closed.is_set())
   self.assertEqual(prepared['review_worker_owner'].workers,workers)
   self.assertTrue(all(not worker.is_alive() for worker in workers))
  finally:
   for worker in workers:worker.join(timeout=300)
   self.assertTrue(all(not worker.is_alive() for worker in workers),'REVIEW_THREAD_NOT_QUIESCENT')
if __name__=='__main__':unittest.main()

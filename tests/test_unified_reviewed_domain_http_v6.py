"""Full source-gated HTTP fixture only; no production state or approval."""
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
from copy import deepcopy
from datetime import datetime
import os,json,unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from data.strategy_continuous32_runtime import RUNTIME_PATHS,ACCOUNT_ID
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_profiled_runtime import build_runtime
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from data.strategy_bounded_source_gate_v1 import BoundedSourceGateV1
from api.strategy_unified_reviewed_domain_composition_v6 import SOURCES,create_unified_reviewed_domain_strategy_router_v6
from data.strategy_daily_signal_verifier import POLICY
import test_strategy_daily_domain_policy_reader_v1 as policy_fixture
import test_strategy_profiled_daily_packet_admission as base_fixture
from data.strategy_account_action_capture import StrategyAccountActionCapture
ACTION_INIT=StrategyAccountActionCapture.__init__
ROOT=Path(__file__).resolve().parents[1]

class ReviewedDomainHTTPTests(unittest.TestCase):
 def runtime_case(self, original, folder):
  c=original(folder);root=Path(folder)
  import shutil
  daily_calendar=(root/'calendar.json').read_bytes()
  shutil.copytree(c.provider.root,root,dirs_exist_ok=True)
  (root/'training-calendar.json').write_bytes((root/'calendar.json').read_bytes())
  manifest=json.loads((root/'manifest.json').read_bytes())
  manifest['source_hashes']['training-calendar.json']=manifest['source_hashes'].pop('calendar.json')
  (root/'manifest.json').write_bytes(canonical(manifest))
  (root/'calendar.json').write_bytes(daily_calendar)
  def put(name,value):
   raw=canonical(value);path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);return sha256(raw).hexdigest()
  pins={}
  for name in RUNTIME_PATHS:
   raw=(ROOT/name).read_bytes();path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
  (root/'identity-proof').write_bytes(b'identity')
  (root/'identity-only').write_bytes(b'id')
  identity=dict(candidates=[dict(ticker=t,security_id=s,issuer_id=s,status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['identity-proof']) for t,s in [('AAA','A'),('BBB','B')]],source_hashes={'identity-proof':sha256(b'identity').hexdigest()})
  cfg=dict(schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1',selector_profile=PROFILE_ID,target_month='2026-11',training_manifest=c.provider.manifest_path,training_sha256=sha256((root/'manifest.json').read_bytes()).hexdigest(),training_closed_at=c.provider.closed,identity_manifest='runtime-identity.json',identity_sha256=put('runtime-identity.json',identity),runtime_pins=pins)
  with patch.object(StrategyAccountActionCapture,'__init__',ACTION_INIT):
   runtime=build_runtime(root=root,configuration=cfg,clock=lambda:c.clock[0])
  provider=runtime.execution_provider.__self__
  def fetch(ticker):
   opening=int(c.clock[0].replace(hour=14,minute=30,second=0).timestamp());last=int(c.clock[0].timestamp())
   return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=100,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400))),timestamp=list(range(opening,last,60)),indicators=dict(quote=[dict(open=[100]*30,high=[101]*30,low=[99]*30,close=[100]*30,volume=[10]*30)]))])))
  provider.market=StrategyAccountMarketCapture(identity_resolver=PinnedStrategyIdentity(root,cfg['identity_manifest'],cfg['identity_sha256']),fetch=fetch,clock=lambda:c.clock[0],max_mark_age=900)
  provider.actions=c.provider.actions
  runtime.accounts.initialize(ACCOUNT_ID,operation_id='init')
  for event in c.store.read()['events']:
   runtime.accounts.append(event['payload'],expected_revision=runtime.accounts.read()['revision'])
  c.store=runtime.accounts;c.state=c.store.read();c.provider=provider;c.monthly=runtime
  c.target=runtime.generate(event_id='fixture-initial',reason='INITIAL',expected_revision=c.state['revision'],previous_target_id=None)
  c.runtime=runtime;c.configuration=cfg
  # Domain fixtures resolve saved selection closure under their explicit capture root.
  c.provider.output=root/'capture'
  return c

 def test_http_all_states_and_cash_does_not_select(self):
  original=base_fixture.ProfiledPacketTests().setup_case
  for mode in ('SELL','BUY','HOLD','WAIT'):
   with self.subTest(mode=mode),TemporaryDirectory() as folder:
    with patch.object(base_fixture.ProfiledPacketTests,'setup_case',side_effect=lambda d:self.runtime_case(original,d)):
     c,root,reader,options=policy_fixture.ExplicitPolicyReaderTests().setup(folder)
    # Domain fixture selected again after recording an exit holding. Persist that
    # genuine selector decision as a second isolated journal event, not a relabel.
    previous=c.runtime.targets.current()
    payload=deepcopy(c.target['payload']);payload['previous_target_id']=previous['target_id']
    payload['request']=dict(event_id='fixture-domain-target',reason='EXPLICIT_RECONFIGURE',expected_revision=c.store.read()['revision'],previous_target_id=previous['target_id'])
    c.target=c.runtime.targets.append(payload)
    resolver=PinnedStrategyIdentity(root,c.identity_reference['path'],c.identity_reference['sha256'])
    if mode in ('BUY','HOLD'):
     for sid,held in c.store.read()['shares'].items():
      wanted=0 if mode=='BUY' else c.target['payload']['target_quantities'].get(sid,0)//2
      if held!=wanted:
       c.store.append(dict(event_id='align-'+sid,kind='DIRECT_FILL',security_id=sid,side='BUY' if wanted>held else 'SELL',quantity=abs(held-wanted),price='10',fees='0',executed_at=c.clock[0].isoformat(),identity_evidence=resolver('AAA' if sid=='A' else 'BBB')),expected_revision=c.store.read()['revision'])
    def minute_raw(ticker):
     opening=int(datetime.fromisoformat('2026-11-02T14:30:00+00:00').timestamp());last=opening+1800
     return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400))),timestamp=list(range(opening,last,60)),indicators=dict(quote=[dict(open=[10]*30,high=[11]*30,low=[9]*30,close=[10]*30,volume=[10]*30)]))])))
    c.provider.market=StrategyAccountMarketCapture(identity_resolver=resolver,fetch=minute_raw,clock=lambda:c.clock[0],max_mark_age=120)
    def put(name,value):
     raw=canonical(value);(root/name).write_bytes(raw);return sha256(raw).hexdigest()
    config_hash=put('runtime.json',c.configuration)
    archive_hash=put('runtime-archive.json',dict(schema='PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1',entries=[dict(configuration_path='runtime.json',configuration_sha256=config_hash)]))
    snapshot=dict(revision=0,registry_path='unused.json',registry_sha256='0'*64,archive_path='runtime-archive.json',archive_sha256=archive_hash)
    # Real archive resolver and runtime source admission; only transports supplied
    # by the fixture are reused after constructing the actual archived runtime.
    def builder(**kwargs):
     runtime=build_runtime(**kwargs);provider=runtime.execution_provider.__self__
     provider.market=c.provider.market;provider.actions=c.provider.actions
     return runtime
    monthly=ProfiledRollingMonthlyRuntimeRouter(root=root,initial_snapshot=snapshot,snapshot_provider=lambda:snapshot,clock=lambda:c.clock[0],runtime_builder=builder,identity_configuration=c.configuration)
    pins={}
    for name in SOURCES:
     raw=(ROOT/name).read_bytes();path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
    evidence={k:v for k,v in options.items() if k not in ('root','clock')}
    if mode=='WAIT':evidence.pop('review_configuration_path');evidence.pop('review_configuration_sha256')
    daily=dict(policy_execution_enabled=True,policy_id=POLICY,evidence=evidence)
    app=FastAPI();app.include_router(create_unified_reviewed_domain_strategy_router_v6(monthly=monthly,validate_code=BoundedSourceGateV1(root=root,source_pins=pins),source_pins=pins,clock=lambda:c.clock[0],daily_configuration=daily,bootstrap_configuration=c.configuration))
    with TestClient(app) as client:
     before_target=monthly.current()
     with patch.object(type(c.provider),'selection',side_effect=AssertionError('cash refresh must not select')):
      response=client.post('/api/strategy-account/events',json=dict(expected_revision=c.store.read()['revision'],event=dict(event_id='http-cash',kind='CASH_CONFIRM',amount='1000' if mode=='BUY' else '0',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
      self.assertEqual(response.status_code,200,response.text)
      self.assertEqual(monthly.current(),before_target)
      account=client.get('/api/strategy-account');target=client.get('/api/strategy-account/target')
      self.assertEqual(account.status_code,200,account.text);self.assertEqual(target.status_code,200,target.text)
      capital=client.post('/api/strategy-capital-v1/status',json=dict(event_id='missing'));self.assertEqual(capital.status_code,200,capital.text)
      before=c.store.path.read_bytes();target_before=c.runtime.targets.path.read_bytes()
      response=client.post('/api/strategy-daily-v3/preview',json=dict(expected_revision=c.store.read()['revision'],target_id=c.target['target_id']))
     self.assertEqual(response.status_code,200,response.text);result=response.json()
     self.assertEqual(result['status'],'READY' if mode in ('BUY','SELL') else mode,result)
     if mode in ('BUY','SELL'):self.assertTrue(any(o['side']==mode for o in result['new_orders']),result)
     else:self.assertEqual(result['new_orders'],[])
     self.assertEqual(c.store.path.read_bytes(),before);self.assertEqual(c.runtime.targets.path.read_bytes(),target_before)
     export=os.environ.get('STRATEGY_HTTP_FIXTURE_EXPORT')
     if export:
      destination=Path(export);destination.mkdir(parents=True,exist_ok=True)
      with (destination/(mode+'.json')).open('xb') as stream:stream.write(canonical(dict(fixture_only=True,mode=mode,evaluated_at=c.clock[0].isoformat(),account=account.json(),target=target.json(),daily=result)))

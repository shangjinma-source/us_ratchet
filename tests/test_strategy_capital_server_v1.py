from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
import json,unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from data.strategy_account_runtime import build_runtime,ACCOUNT_ID
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from api.strategy_capital_server_v1 import build_capital_service,CAPITAL_SOURCES
from api.strategy_capital_v1 import create_router
import test_strategy_account_evidence_provider as fixtures

class CapitalServerTests(unittest.TestCase):
 def test_actual_rolling_archive_identity_and_selector(self):
  with TemporaryDirectory() as temp:
   original,_,now,root=fixtures.ProviderTests().fixture(temp)
   def put(name,value):
    raw=canonical(value);path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);return sha256(raw).hexdigest()
   pins={}
   for name in CAPITAL_SOURCES:
    raw=(Path(__file__).resolve().parents[1]/name).read_bytes();dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
   (root/'identity-proof').write_bytes(b'identity')
   identity=dict(candidates=[dict(ticker=t,security_id=s,issuer_id=s,status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['identity-proof']) for t,s in [('AAA','A'),('BBB','B')]],source_hashes={'identity-proof':sha256(b'identity').hexdigest()})
   config=dict(schema='REAL_STRATEGY_RUNTIME_V1',target_month='2026-11',training_manifest=original.manifest_path,training_sha256=original.manifest_hash,training_closed_at=original.closed,identity_manifest='capital-identity.json',identity_sha256=put('capital-identity.json',identity),runtime_pins=pins)
   archive=dict(schema='REAL_STRATEGY_RUNTIME_ARCHIVE_V1',entries=[dict(configuration_path='runtime.json',configuration_sha256=put('runtime.json',config))])
   snapshot=dict(registry_path='unused-registry.json',registry_sha256='0'*64,archive_path='archive.json',archive_sha256=put('archive.json',archive))
   calls=[]
   def builder(**kwargs):
    runtime=build_runtime(**kwargs);provider=runtime.execution_provider.__self__
    def fetch(ticker):
     start=int(now[0].timestamp())-1800;last=int(now[0].timestamp())
     return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),timestamp=[last-60],indicators=dict(quote=[dict(open=[10],high=[11],low=[9],close=[10],volume=[10])]))])))
    provider.market=StrategyAccountMarketCapture(identity_resolver=PinnedStrategyIdentity(root,config['identity_manifest'],config['identity_sha256']),fetch=fetch,clock=lambda:now[0],max_mark_age=900)
    provider.actions=original.actions
    calls.append(runtime);return runtime
   admission=dict(schema='CAPITAL_SERVER_ADMISSION_V1',source_pins=pins,initial_snapshot=snapshot,journal_path='data/strategy_account/capital_intents_v1.sqlite3')
   digest=put('capital-admission.json',admission)
   service=build_capital_service(root=root,configuration_path='capital-admission.json',configuration_sha256=digest,clock=lambda:now[0],runtime_builder=builder)
   account=service.monthly.accounts;account.initialize(ACCOUNT_ID,operation_id='init')
   identity_evidence=PinnedStrategyIdentity(root,config['identity_manifest'],config['identity_sha256'])('AAA')
   account.append(dict(kind='DIRECT_FILL',event_id='held-A',security_id='A',side='BUY',quantity=2,price='10',fees='0',executed_at='2026-10-30T19:00:00Z',identity_evidence=identity_evidence),expected_revision=account.read()['revision'])
   account.append(dict(kind='CASH_CONFIRM',event_id='cash',amount='1000',cash_basis='TOTAL_UNINVESTED'),expected_revision=account.read()['revision'])
   # Bootstrap a prior target using the genuine selector with pinned config.
   runtime=builder(root=root,configuration=config,clock=lambda:now[0])
   self.assertEqual(runtime.selection.select()['status'],'READY')
   decision=runtime.selection.current[0]
   target=service.monthly.targets.append(dict(schema='REAL_STRATEGY_MONTHLY_TARGET_V1',account_id=ACCOUNT_ID,target_month='2026-11',created_at=now[0].isoformat(),request=dict(event_id='initial'),previous_target_id=None,decision=decision,target_quantities=decision['payload']['target_quantities'],runtime_pins=pins))
   app=FastAPI();app.include_router(create_router(service=service));client=TestClient(app)
   before=account.path.read_bytes()
   body=dict(event_id='capital',contribution_amount='200',expected_revision=account.read()['revision'],previous_target_id=target['target_id'])
   result=client.post('/api/strategy-capital-v1/intents',json=body);self.assertEqual(result.status_code,200,result.text)
   result=client.post('/api/strategy-capital-v1/configure',json={'event_id':'capital'});self.assertEqual(result.status_code,200,result.text)
   self.assertEqual(result.json()['status'],'CONSUMED_BY_PUBLISHED_TARGET')
   self.assertEqual(account.path.read_bytes(),before)
   self.assertEqual(len(service.monthly.targets.history()),2)
   (root/'api/strategy_capital_v1.py').write_bytes(b'changed')
   result=client.post('/api/strategy-capital-v1/status',json={'event_id':'capital'})
   self.assertEqual(result.status_code,409)

 def test_active_release_replay_and_storage_collision(self):
  import test_strategy_account_release_activation as activation_fixture
  f=activation_fixture.ActivationTests();f.setUp();self.addCleanup(f.doCleanups)
  root=f.fixture.root
  pins={}
  for name in CAPITAL_SOURCES:
   raw=(Path(__file__).resolve().parents[1]/name).read_bytes();dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
  config=dict(schema='CAPITAL_SERVER_ADMISSION_V1',source_pins=pins,initial_snapshot=f.initial,journal_path='data/strategy_account/capital_intents_v1.sqlite3')
  def build(config,name='capital-active.json'):
   raw=canonical(config);(root/name).write_bytes(raw)
   return build_capital_service(root=root,configuration_path=name,configuration_sha256=sha256(raw).hexdigest(),clock=lambda:f.fixture.now)
  service=build(config)
  # Actual gate for adoption too; saved admission replay subsequently runs via factory.
  f.service.gate=service.validate_code
  f.adopt()
  with service.monthly.snapshot_operation() as snapshot:
   self.assertEqual(snapshot['revision'],1)
   self.assertEqual(snapshot['registry_path'],'reviewed-package/candidate/registry.json')
  for forbidden in ('active_monthly_releases.sqlite3','active_monthly_releases.sqlite3-wal','real_strategy.sqlite3','monthly_targets.sqlite3-journal'):
   bad=dict(config,journal_path='data/strategy_account/'+forbidden)
   with self.assertRaisesRegex(ValueError,'CAPITAL_DEDICATED_JOURNAL_REQUIRED'):build(bad,'invalid-capital.json')
  self.assertFalse(service.journal.path.exists())
  (root/f.receipt_path).write_bytes(b'corrupt')
  with self.assertRaises(ValueError):
   with service.monthly.snapshot_operation():pass

from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
import unittest
from unittest.mock import patch
from datetime import timedelta
from core.strategy_account_ledger import canonical
from data.strategy_account_runtime import ACCOUNT_ID
from data.strategy_continuous32_runtime import RUNTIME_PATHS
from data.strategy_profiled_runtime import build_runtime
from data.strategy_profiled_runtime_archive import configuration_for_target
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_market_capture import StrategyAccountMarketCapture
import test_strategy_account_evidence_provider as fixtures

class TransitionProfileIndependentTests(unittest.TestCase):
 def test_actual_continuous32_prepared_publication_only_recovery(self):
  with TemporaryDirectory() as temp:
   original,_,now,root=fixtures.ProviderTests().fixture(temp)
   def put(name,value):
    raw=canonical(value);path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);return sha256(raw).hexdigest()
   pins={}
   for name in RUNTIME_PATHS:
    raw=(Path(__file__).resolve().parents[1]/name).read_bytes();dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
   (root/'identity-proof').write_bytes(b'identity')
   identity=dict(candidates=[dict(ticker=t,security_id=s,issuer_id=s,status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['identity-proof']) for t,s in [('AAA','A'),('BBB','B')]],source_hashes={'identity-proof':sha256(b'identity').hexdigest()})
   config=dict(schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1',selector_profile=PROFILE_ID,target_month='2026-11',training_manifest=original.manifest_path,training_sha256=original.manifest_hash,training_closed_at=original.closed,identity_manifest='capital-identity.json',identity_sha256=put('capital-identity.json',identity),runtime_pins=pins)
   archive=dict(schema='PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1',entries=[dict(configuration_path='runtime.json',configuration_sha256=put('runtime.json',config))])
   snapshot=dict(registry_path='unused-registry.json',registry_sha256='0'*64,archive_path='archive.json',archive_sha256=put('archive.json',archive))
   calls=[]
   def builder(**kwargs):
    runtime=build_runtime(**kwargs);provider=runtime.execution_provider.__self__
    def fetch(ticker):
     start=int(now[0].replace(hour=14,minute=30,second=0).timestamp());last=int(now[0].timestamp())
     return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),timestamp=list(range(start,start+1800,60)),indicators=dict(quote=[dict(open=[10]*30,high=[11]*30,low=[9]*30,close=[10]*30,volume=[10]*30)]))])))
    provider.market=StrategyAccountMarketCapture(identity_resolver=PinnedStrategyIdentity(root,config['identity_manifest'],config['identity_sha256']),fetch=fetch,clock=lambda:now[0],max_mark_age=900)
    provider.actions=original.actions
    calls.append(runtime);return runtime
   runtime=builder(root=root,configuration=config,clock=lambda:now[0])
   account=runtime.accounts;account.initialize(ACCOUNT_ID,operation_id='init')
   account.append(dict(kind='CASH_CONFIRM',event_id='cash',amount='1000',cash_basis='TOTAL_UNINVESTED'),expected_revision=account.read()['revision'])
   before=account.path.read_bytes()
   target=runtime.generate(event_id='continuous-initial',reason='INITIAL',expected_revision=account.read()['revision'],previous_target_id=None)
   self.assertEqual(target['payload']['decision']['payload']['input_binding']['selector_profile'],PROFILE_ID)
   resolved=configuration_for_target(root=root,archive_path='archive.json',archive_sha256=snapshot['archive_sha256'],target=target)
   self.assertEqual(resolved,config)
   from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
   from api.strategy_capital_transition_composition import TransitionCapitalService as build_capital_service,SOURCES
   from api.strategy_capital_v1 import create_router
   from fastapi import FastAPI
   from fastapi.testclient import TestClient
   snapshot['revision']=0
   monthly=ProfiledRollingMonthlyRuntimeRouter(root=root,initial_snapshot=snapshot,snapshot_provider=lambda:snapshot,clock=lambda:now[0],runtime_builder=builder)
   capitalpins={}
   for name in SOURCES:
    raw=(Path(__file__).resolve().parents[1]/name).read_bytes();dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);capitalpins[name]=sha256(raw).hexdigest()
   service=build_capital_service(monthly=monthly,validate_code=runtime.selection._pins,source_pins=capitalpins)
   self.assertIs(service.monthly,monthly)
   app=FastAPI();app.include_router(create_router(service=service));client=TestClient(app)
   body=dict(event_id='new-contribution',contribution_amount='200',expected_revision=account.read()['revision'],previous_target_id=target['target_id'])
   self.assertEqual(client.post('/api/strategy-capital-v1/intents',json=body).status_code,200)
   with patch.object(monthly.targets,'append',side_effect=OSError('publication interrupted')):
    result=client.post('/api/strategy-capital-v1/configure',json={'event_id':body['event_id']})
   self.assertEqual(result.status_code,409,result.text)
   self.assertEqual(client.post('/api/strategy-capital-v1/status',json={'event_id':body['event_id']}).json()['status'],'PREPARED_PUBLISH_ONLY')
   with patch('data.strategy_profiled_capital_service.StrategyAccountTargetService.select',side_effect=AssertionError('never reselect')):
    result=client.post('/api/strategy-capital-v1/recover-publication',json={'event_id':body['event_id']})
   self.assertEqual(result.status_code,200,result.text)
   self.assertEqual(result.json()['status'],'CONSUMED_BY_PUBLISHED_TARGET')
   self.assertEqual(monthly.targets.current()['payload']['decision']['payload']['input_binding']['selector_profile'],PROFILE_ID)
   self.assertEqual(account.path.read_bytes(),before)
   self.assertEqual(account.read()['available_cash'],'1000')
   # An unresolved original journal must block, without losing its intent.
   from core.strategy_capital_intent_journal import CapitalIntentJournal
   old=CapitalIntentJournal(root/'data/strategy_account/capital_intents_v1.sqlite3')
   intent=service.profiled_journal.intent(body['event_id']);intent=dict(intent,event_id='legacy-pending',previous_target_id=monthly.targets.current()['target_id'])
   old.record(intent,account_state=account.read(),previous_target=monthly.targets.current())
   with self.assertRaisesRegex(ValueError,'CAPITAL_LEGACY_PENDING_REVIEW_REQUIRED'):
    service.record(event_id='blocked-new-profile-event',contribution_amount='20',expected_revision=account.read()['revision'],previous_target_id=monthly.targets.current()['target_id'])


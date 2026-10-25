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

class UnifiedDomainHTTPTests(unittest.TestCase):
 def test_routes_cash_defaultoff_missing_domain_wait_no_quotes(self):
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
   from api.strategy_unified_domain_composition_v5 import SOURCES,create_unified_domain_strategy_router_v5
   from data.strategy_bounded_source_gate_v1 import BoundedSourceGateV1
   from data.strategy_daily_dynamic_factory_v1 import FACTORY_SOURCES
   from data.strategy_daily_signal_verifier import POLICY
   from fastapi import FastAPI
   from fastapi.testclient import TestClient
   from datetime import date
   snapshot['revision']=0
   monthly=ProfiledRollingMonthlyRuntimeRouter(root=root,initial_snapshot=snapshot,snapshot_provider=lambda:snapshot,clock=lambda:now[0],runtime_builder=builder,identity_configuration=config)
   allpins={}
   for name in SOURCES:
    raw=(Path(__file__).resolve().parents[1]/name).read_bytes();dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);allpins[name]=sha256(raw).hexdigest()
   gate=BoundedSourceGateV1(root=root,source_pins=allpins)
   def app(daily):
    application=FastAPI();application.include_router(create_unified_domain_strategy_router_v5(monthly=monthly,validate_code=gate,source_pins=allpins,clock=lambda:now[0],daily_configuration=daily,bootstrap_configuration=config))
    paths=[(r.path,m) for r in application.routes if hasattr(r,'methods') for m in r.methods];self.assertEqual(len(paths),len(set(paths)))
    return application
   disabled=dict(policy_execution_enabled=False,evidence=dict(configuration_path='not-read.json',configuration_sha256='0'*64,archive_root=root/'daily-archive'))
   with patch.object(StrategyAccountMarketCapture,'capture',side_effect=AssertionError('WAIT must not quote')):
    with TestClient(app(disabled)) as client:
     self.assertEqual(client.get('/api/strategy-account').status_code,200)
     self.assertEqual(client.get('/api/strategy-account/target').status_code,200)
     r=client.post('/api/strategy-capital-v1/status',json=dict(event_id='not-recorded'));self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['status'],'NOT_FOUND')
     r=client.post('/api/strategy-account/events',json=dict(expected_revision=account.read()['revision'],event=dict(kind='CASH_CONFIRM',event_id='same-month-cash',amount='900',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
     self.assertEqual(r.status_code,200,r.text);self.assertEqual(monthly.current(),target)
     r=client.post('/api/strategy-daily-v3/preview',json=dict(expected_revision=account.read()['revision'],target_id=target['target_id']))
     self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['detail_status'],'DAILY_PREVIEW_DISABLED')
    days=[];day=date(2026,11,2)
    while len(days)<22:
     if day.weekday()<5:days.append(day.isoformat())
     day-=timedelta(days=1)
    days.reverse()
    sessions=[dict(date=d,open=d+'T09:30:00-04:00',close=d+'T16:00:00-04:00') for d in days[:-1]]+[dict(date=days[-1],open=days[-1]+'T09:30:00-05:00',close=days[-1]+'T16:00:00-05:00')]
    calendar=put('domain-calendar.json',dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=sessions))
    dynamic=dict(schema='SERVER_DYNAMIC_DAILY_SOURCE_V1',source_pins=[dict(path=p,sha256=allpins[p]) for p in FACTORY_SOURCES],identity=dict(path=config['identity_manifest'],sha256=config['identity_sha256']),calendar=dict(path='domain-calendar.json',sha256=calendar),runs_root='uncreated-domain',account_id=ACCOUNT_ID,first_execution_date='2026-11-02',target_evidence_root='capture')
    digest=put('domain-config.json',dynamic)
    # Isolated routing flag only: no release supplied, no fixture approval created.
    missing=dict(policy_execution_enabled=True,policy_id=POLICY,evidence=dict(configuration_path='domain-config.json',configuration_sha256=digest,archive_root=root/'daily-archive'))
    state=account.read();saved=account.path.read_bytes()
    with TestClient(app(missing)) as client:
     r=client.post('/api/strategy-daily-v3/preview',json=dict(expected_revision=state['revision'],target_id=target['target_id']))
     self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['status'],'WAIT');self.assertEqual(r.json()['new_orders'],[])
     self.assertEqual(r.json()['reason'],'WAIT_NEW_SESSION_EVIDENCE')
    self.assertEqual(monthly.current(),target);self.assertEqual(account.path.read_bytes(),saved);self.assertFalse((root/'daily-archive').exists())

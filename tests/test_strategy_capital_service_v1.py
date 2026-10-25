from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from threading import RLock
from hashlib import sha256
from unittest.mock import patch
import unittest
from datetime import timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from core.strategy_capital_intent_journal import CapitalIntentJournal
from data.strategy_account_target_service import StrategyAccountTargetService,MINIMUM_RUNTIME_PATHS
from data.strategy_capital_service_v1 import CapitalContributionServiceV1
from api.strategy_capital_v1 import create_router
import test_strategy_account_evidence_provider as fixtures

class CapitalServiceTests(unittest.TestCase):
 def setUp(self):
  identity=patch("data.strategy_capital_service_v1.validate_account_identity_coverage");identity.start();self.addCleanup(identity.stop)
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
  provider,state,now,sources=fixtures.ProviderTests().fixture(self.temp.name)
  pins={}
  for name in MINIMUM_RUNTIME_PATHS:
   raw=(Path(__file__).resolve().parents[1]/name).read_bytes();dest=sources/name
   dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
  provider.runtime_pins=pins
  accounts=StrategyAccountStore(root/'account.sqlite3',clock=lambda:now[0]);accounts.initialize(state['account_id'],operation_id='init')
  for row in state['events']:accounts.append(row['payload'],expected_revision=accounts.read()['revision'])
  # Resolve outstanding fixture orders before the contribution workflow.
  for order_id,order in list(accounts.read()['orders'].items()):
   if order['remaining_quantity']>0:accounts.append(dict(kind='CANCEL',event_id='cancel-'+order_id,order_id=order_id),expected_revision=accounts.read()['revision'])
  accounts.append(dict(kind='CASH_CONFIRM',event_id='capital-cash',amount='1000',cash_basis='TOTAL_UNINVESTED'),expected_revision=accounts.read()['revision'])
  selector=StrategyAccountTargetService(store=accounts,evidence_provider=provider.selection,runtime_root=sources,runtime_pins=pins,maximum_mark_age_seconds=900,execution_fee_bps='0',clock=lambda:now[0])
  selected=selector.select();self.assertEqual(selected['status'],'READY',selected)
  decision=selector.current[0];targets=StrategyMonthlyTargetStore(root/'targets.sqlite3')
  targets.append(dict(schema='REAL_STRATEGY_MONTHLY_TARGET_V1',account_id=state['account_id'],target_month='2026-11',created_at=now[0].isoformat(),request=dict(event_id='initial'),previous_target_id=None,decision=decision,target_quantities=decision['payload']['target_quantities'],runtime_pins=pins))
  runtime=SimpleNamespace(selection=selector,execution_provider=provider.execution)
  monthly=SimpleNamespace(root=sources,accounts=accounts,targets=targets,current=targets.current,_month=lambda:'2026-11',_for_target=lambda target:(runtime,{}),snapshot_operation=RLock,clock=lambda:now[0])
  journal=CapitalIntentJournal(root/'capital.sqlite3')
  self.service=CapitalContributionServiceV1(monthly=monthly,journal=journal,validate_code=lambda:None)
  self.now=now
  self.accounts,self.targets,self.provider,self.journal=accounts,targets,provider,journal
  app=FastAPI();app.include_router(create_router(service=self.service));self.client=TestClient(app)
  self.body=dict(event_id='capital-1',contribution_amount='250',expected_revision=accounts.read()['revision'],previous_target_id=targets.current()['target_id'])
 def post(self,endpoint,body=None):return self.client.post('/api/strategy-capital-v1/'+endpoint,json=body or {'event_id':'capital-1'})
 def test_actual_selector_publication_no_account_write(self):
  before=self.accounts.path.read_bytes()
  self.assertEqual(self.post('intents',self.body).status_code,200)
  result=self.post('configure');self.assertEqual(result.status_code,200,result.text)
  self.assertEqual(result.json()['status'],'CONSUMED_BY_PUBLISHED_TARGET')
  self.assertEqual(self.accounts.path.read_bytes(),before)
  self.assertEqual(self.accounts.read()['available_cash'],'1000')
  with patch.object(self.provider,'selection',side_effect=AssertionError('must not select')):
   self.assertEqual(self.post('recover-publication').json(),result.json())
 def test_prepared_publication_recovery_and_response_loss(self):
  self.post('intents',self.body)
  with patch.object(self.targets,'append',side_effect=OSError('publish unavailable')):
   self.assertEqual(self.post('configure').status_code,409)
  self.assertEqual(self.post('status').json()['status'],'PREPARED_PUBLISH_ONLY')
  original=self.targets.append
  def lost(payload):original(payload);raise OSError('response lost')
  with patch.object(self.targets,'append',side_effect=lost):self.assertEqual(self.post('recover-publication').status_code,409)
  self.assertEqual(self.post('status').json()['status'],'CONSUMED_BY_PUBLISHED_TARGET')
  self.assertEqual(len(self.targets.history()),2)
 def test_http_input_and_unknown_event(self):
  self.assertEqual(self.post('status').json()['status'],'NOT_FOUND')
  self.post('intents',self.body)
  self.assertEqual(self.post('status',{'event_id':'other'}).json()['status'],'NOT_FOUND')
  for content in ('{"event_id":"a","event_id":"b"}', ' '*4097):
   self.assertEqual(self.client.post('/api/strategy-capital-v1/status',content=content).status_code,409)
  self.assertEqual(self.post('configure',dict(event_id='capital-1',decision={})).status_code,409)



 def test_claim_failure_never_reselects(self):
  self.post('intents',self.body)
  runtime=self.service.monthly._for_target(self.targets.current())[0]
  with patch.object(runtime.selection,'provider',side_effect=OSError('offline')) as call:
   self.assertEqual(self.post('configure').status_code,409)
   self.assertEqual(self.post('configure').status_code,409)
   self.assertEqual(call.call_count,1)
  self.assertEqual(self.post('status').json()['status'],'RECOVERY_REQUIRED')
 def test_prepared_stale_account_cannot_publish(self):
  self.post('intents',self.body)
  with patch.object(self.targets,'append',side_effect=OSError('offline')):
   self.assertEqual(self.post('configure').status_code,409)
  self.accounts.append(dict(kind='CASH_CONFIRM',event_id='new-balance',amount='900',cash_basis='TOTAL_UNINVESTED'),expected_revision=self.accounts.read()['revision'])
  self.assertEqual(self.post('recover-publication').status_code,409)
  self.assertEqual(len(self.targets.history()),1)
  self.assertEqual(self.post('status').json()['status'],'PREPARED_PUBLISH_ONLY')

 def test_prepared_expired_recovery_refused_without_fetch(self):
  self.post('intents',self.body)
  with patch.object(self.targets,'append',side_effect=OSError('offline')):
   self.assertEqual(self.post('configure').status_code,409)
  self.now[0]+=timedelta(seconds=901)
  with patch.object(self.provider.market,'capture',side_effect=AssertionError('no fetch')):
   response=self.post('recover-publication')
  self.assertEqual(response.status_code,409,response.text)
  self.assertEqual(response.json()['reason'],'REQUOTE_REQUIRED')
  self.assertEqual(len(self.targets.history()),1)

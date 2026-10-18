from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_monthly_target_service import StrategyMonthlyTargetService,LIFECYCLE_PATHS
from api.strategy_monthly_target import create_router

class MonthlyAPITests(unittest.TestCase):
 def test_real_service_cas_idempotent_and_compact_readonly(self):
  with TemporaryDirectory() as d:
   root=Path(d);now=datetime(2026,10,16,15,tzinfo=timezone.utc)
   accounts=StrategyAccountStore(root/'account.db',clock=lambda:now);targets=StrategyMonthlyTargetStore(root/'target.db')
   class Selection:
    store=accounts;pins={k:'a'*64 for k in LIFECYCLE_PATHS};age=120;fees='0';calls=0
    def _pins(self):pass
    def generate(self):
     self.calls+=1;s=self.store.read()
     binding=dict(account_revision=s['revision'],search_arguments=dict(metadata={'A':{'ticker':'SNDK'}}),training_cutoff_date='2026-10-14',valuation_at=now.isoformat(),strategy_equity='2000')
     p=dict(input_binding=binding,target_quantities={'A':14})
     self.current=(dict(payload=p,decision_id=sha256(canonical(p)).hexdigest()),{},s)
     return {'status':'READY'}
   selection=Selection()
   def evidence(state,target,at):return dict(marks={'A':dict(security_id='A',currency='USD',price_basis='CURRENT',price='100',observed_at=at.isoformat())},limits={'A':dict(security_id='A',price_basis='CURRENT',observed_at=at.isoformat(),buy='100',sell='100',ticker='SNDK',buy_reason='测试买价',sell_reason='测试卖价',reference_valid_until='2026-10-16T15:02:00+00:00')})
   service=StrategyMonthlyTargetService(selection_service=selection,target_store=targets,execution_provider=evidence,clock=lambda:now)
   app=FastAPI();app.include_router(create_router(service=service));base='/api/strategy-account/target'
   with TestClient(app) as client:
    self.assertEqual(client.get(base).json()['status'],'NOT_INITIALIZED');self.assertFalse(accounts.path.exists());self.assertFalse(targets.path.exists())
    initial=accounts.initialize('fixed',operation_id='init');state,_=accounts.append(dict(event_id='cash',kind='CASH_CONFIRM',amount='2000',cash_basis='TOTAL_UNINVESTED'),expected_revision=initial['revision'])
    before=accounts.path.read_bytes()
    body=dict(event_id='target1',reason='INITIAL',expected_revision=state['revision'],previous_target_id=None)
    first=client.post(base+'/generate',json=body);self.assertEqual(first.status_code,200)
    target=first.json();self.assertEqual(target['status'],'SAVED_TARGET');self.assertNotIn('source_hashes',str(target))
    self.assertEqual(client.post(base+'/generate',json=body).json(),target);self.assertEqual(selection.calls,1)
    self.assertEqual(client.get(base).json(),target)
    self.assertEqual(target['configuration_reason'],'EXPLICIT_RECONFIGURE')
    service.clock=lambda:datetime(2026,11,1,3,59,tzinfo=timezone.utc)
    self.assertEqual(client.get(base).json()['server_month'],'2026-10')
    service.clock=lambda:datetime(2026,11,1,4,0,tzinfo=timezone.utc)
    self.assertEqual(client.get(base).json()['configuration_reason'],'MONTHLY_SELECTION')
    service.clock=lambda:now
    preview=client.post(base+'/preview',json=dict(expected_revision=state['revision'],target_id=target['target_id']))
    self.assertEqual(preview.status_code,200);self.assertNotIn('binding',preview.json()['difference']);self.assertEqual(selection.calls,1)
    self.assertIsNone(preview.json()['reference_quotes']['A']['buy_limit'])
    self.assertEqual(preview.json()['reference_quotes']['A']['sell_limit'],'100')
    self.assertTrue(preview.json()['reference_quotes']['A']['sell_is_exit_reference'])
    self.assertEqual(accounts.path.read_bytes(),before)
    self.assertEqual(client.post(base+'/preview',json=dict(expected_revision='0'*64,target_id=target['target_id'])).status_code,409)
    self.assertEqual(client.post(base+'/generate',json=dict(body,event_id='other',previous_target_id=None)).status_code,409)
    for extra in ('now','account_id','database_path','decision'):
     self.assertEqual(client.post(base+'/generate',json=dict(body,**{extra:'bad'})).status_code,422)
    self.assertEqual(client.get(base+'?now=2099').status_code,422)
    self.assertEqual(client.post(base+'/generate',content=' '*5000).json()['reason'],'BODY_TOO_LARGE')
    self.assertEqual(client.post(base+'/preview',content='{"target_id":"a","target_id":"b"}').json()['reason'],'DUPLICATE_JSON_FIELD')
 def test_bound_chart_http_and_query_validation(self):
  from test_strategy_monthly_target_charts import ChartsTests
  from types import SimpleNamespace
  fixture=ChartsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
  service=SimpleNamespace(selection=SimpleNamespace(_pins=lambda:None))
  app=FastAPI();app.include_router(create_router(service=service,charts=fixture.charts))
  with TestClient(app) as client:
   query=dict(target_id=fixture.target['target_id'],security_id='sid:AAA',interval='day')
   response=client.get('/api/strategy-account/target/bars',params=query)
   self.assertEqual(response.status_code,200,response.text)
   self.assertEqual(response.json()['ticker'],'AAA')
   self.assertEqual(client.get('/api/strategy-account/target/bars',params=dict(query,path='secret')).status_code,422)
   self.assertEqual(client.get('/api/strategy-account/target/bars',params=dict(query,target_id='0'*64)).status_code,409)
 def test_exception_text_not_leaked(self):
  class Broken:
   def current(self):raise OSError('secret path')
  app=FastAPI();app.include_router(create_router(service=Broken()))
  with TestClient(app) as client:
   response=client.get('/api/strategy-account/target')
   self.assertEqual(response.json()['reason'],'TARGET_UNAVAILABLE');self.assertNotIn('secret',response.text)

if __name__=='__main__':unittest.main()


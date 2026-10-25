"""V11 route/runtime composition in temporary SQLite; no live network or balances."""
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from fastapi import FastAPI,APIRouter
from fastapi.testclient import TestClient
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from core.strategy_profiled_capital_intent_journal import ProfiledCapitalIntentJournal
from core.strategy_profiled_capital_journal_v2 import ProfiledCapitalJournalV2
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from data.strategy_unified_server_preparation_v11 import attach_capital_arrival_v11,OLD_ROUTES

class CapitalV11Tests(unittest.TestCase):
 def setup(self,directory):
  root=Path(directory);account=StrategyAccountStore(root/'account.db');account.initialize('fixture',operation_id='init')
  journal=ProfiledCapitalJournalV2(root/'v2.db');journal.initialize_from_legacy(ProfiledCapitalIntentJournal(root/'absent.db'))
  provider=SimpleNamespace(market=StrategyAccountMarketCapture(identity_resolver=lambda t:None,max_mark_age=900))
  class Provider:
   def execution(self):pass
  provider=Provider();provider.market=StrategyAccountMarketCapture(identity_resolver=lambda t:None,max_mark_age=900)
  runtime=SimpleNamespace(execution_provider=provider.execution)
  monthly=SimpleNamespace(_runtimes={},_builder=lambda **kw:runtime,accounts=account,snapshot_operation=lambda:nullcontext(),targets=StrategyMonthlyTargetStore(root/'targets.db'))
  router=APIRouter()
  for path,method in OLD_ROUTES:router.add_api_route(path,lambda:{'old':True},methods=[method])
  router.add_api_route('/api/strategy-display/latest-bars',lambda:{'display':True},methods=['GET'])
  gatecalls=[];prepared=dict(monthly=monthly,router=router,validate_code=lambda:gatecalls.append('base'))
  return root,prepared,journal,account,runtime,gatecalls
 def test_routes_status_shared_runtime_and_no_writes(self):
  with TemporaryDirectory() as d:
   root,p,j,a,r,calls=self.setup(d);before=a.path.read_bytes();jb=j.path.read_bytes()
   result=attach_capital_arrival_v11(prepared=p,root=root,journal_path=j.path,validate_v11_sources=lambda:calls.append('v11'))
   self.assertIs(result['capital_arrival'].monthly,p['monthly'])
   app=FastAPI();app.include_router(result['router'])
   with TestClient(app) as client:
    response=client.post('/api/strategy-capital-v2/status',json={'event_id':'absent'})
    self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['status'],'NOT_FOUND')
    self.assertEqual(client.post('/api/strategy-capital-v1/status',json={'event_id':'absent'}).status_code,404)
    self.assertEqual(client.get('/api/strategy-display/latest-bars').status_code,200)
   built=p['monthly']._builder()
   self.assertIs(built,r);self.assertIs(type(r.execution_provider.__self__.market),StrategyAccountMarketCapture)
   self.assertEqual(r.execution_provider.__self__.market.max_mark_age,900)
   self.assertEqual(a.path.read_bytes(),before);self.assertEqual(j.path.read_bytes(),jb)
 def test_missing_import_and_existing_runtime_rejected(self):
  with TemporaryDirectory() as d:
   root,p,j,a,r,calls=self.setup(d);original=p['monthly']._builder
   with self.assertRaisesRegex(ValueError,'IMPORT_REQUIRED'):attach_capital_arrival_v11(prepared=p,root=root,journal_path=root/'missing.db',validate_v11_sources=lambda:None)
   self.assertIs(p['monthly']._builder,original);self.assertFalse((root/'missing.db').exists())
   p['router'].add_api_route('/api/strategy-capital-v2/status',lambda:{},methods=['POST'])
   with self.assertRaisesRegex(ValueError,'DUPLICATE_ROUTE'):attach_capital_arrival_v11(prepared=p,root=root,journal_path=j.path,validate_v11_sources=lambda:None)
 def test_new_gate_applies_before_runtime_or_capture(self):
  with TemporaryDirectory() as d:
   root,p,j,a,r,calls=self.setup(d);broken=[False]
   def gate():
    if broken[0]:raise ValueError('SOURCE_CHANGED')
   result=attach_capital_arrival_v11(prepared=p,root=root,journal_path=j.path,validate_v11_sources=gate)
   broken[0]=True
   with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):result['capital_arrival'].status(event_id='absent')
   with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):result['validate_code']()
if __name__=='__main__':unittest.main()

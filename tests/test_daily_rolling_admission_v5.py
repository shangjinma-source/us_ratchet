from contextlib import nullcontext
from datetime import timedelta
from email.utils import format_datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from fastapi import FastAPI,APIRouter
from fastapi.testclient import TestClient
from data.strategy_daily_rolling_admission_v3 import RollingDailyAdmissionV3
from data.strategy_daily_rolling_admission_v5 import RollingDailyAdmissionV5
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from data.strategy_unified_server_preparation_v12 import attach_daily_rss_v12
from api.strategy_daily_preview_v3 import create_router
from test_daily_composition_v3 import CompositionTests,POLICY

class DailyRssV4Tests(unittest.TestCase):
 def test_actual_provider_microlead_observed_http_and_no_shared_mutation(self):
  with TemporaryDirectory() as directory:
   c=CompositionTests().setup_case(directory)
   c.clock[0]=c.clock[0].replace(microsecond=500000)
   published=c.clock[0]+timedelta(seconds=1.5)
   c.provider.actions.rss_fetch=lambda:dict(status=200,body=(
    '<rss><channel><title>Nasdaq</title><pubDate>'+format_datetime(published)+
    '</pubDate><item><title>Unrelated</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>').encode())
   original_actions=c.provider.actions;original_market=c.provider.market
   runtime=SimpleNamespace(execution_provider=c.provider.execution,selection=SimpleNamespace(fees='10'))
   c.monthly.root=Path(directory);c.monthly.snapshot_operation=lambda:nullcontext()
   c.monthly._for_target=lambda target:(runtime,{})
   daily=RollingDailyAdmissionV3(monthly=c.monthly,reader=c.reader,clock=lambda:c.clock[0],validate_code=lambda:None,policy_execution_enabled=True,policy_id=POLICY)
   journal=DailyAdviceJournalV1(Path(directory)/'observed.db',clock=lambda:c.clock[0])
   observed=ObservedDailyAdmission(service=daily,monthly=c.monthly,journal=journal,clock=lambda:c.clock[0],validate_sources=lambda:None,policy_references={'fixture_only':True})
   router=create_router(service=observed)
   prepared=dict(monthly=c.monthly,observed_daily=observed,advice_journal=journal,router=router,validate_code=lambda:None)
   request=dict(expected_revision=c.state['revision'],target_id=c.target['target_id'])
   before=c.store.path.read_bytes()
   with patch('data.strategy_daily_rolling_admission_v3.validate_account_identity_coverage'):
    old=FastAPI();old.include_router(router)
    response=TestClient(old).post('/api/strategy-daily-v3/preview',json=request)
   self.assertEqual(response.status_code,409,response.text)
   self.assertIn('ACTION_RSS_TIME_INVALID',response.text)
   new=dict(observed_daily=ObservedDailyAdmission(service=RollingDailyAdmissionV5(monthly=c.monthly,reader=c.reader,clock=lambda:c.clock[0],validate_code=lambda:None,policy_execution_enabled=True,policy_id=POLICY),monthly=c.monthly,journal=journal,clock=lambda:c.clock[0],validate_sources=lambda:None,policy_references={'fixture_only':True}))
   new['router']=create_router(service=new['observed_daily'])
   self.assertIs(new['observed_daily'].journal,journal)
   self.assertIs(new['observed_daily'].service.reader,c.reader)
   waits=[]
   def sleep(seconds):
    waits.append(seconds);c.clock[0]+=timedelta(seconds=seconds)
   app=FastAPI();app.include_router(new['router'])
   with patch('data.strategy_daily_rolling_admission_v5.validate_account_identity_coverage'),patch('data.strategy_rss_verified_transport_v2.time.sleep',side_effect=sleep):
    response=TestClient(app).post('/api/strategy-daily-v3/preview',json=request)
   self.assertEqual(response.status_code,200,response.text)
   self.assertEqual(response.json()['status'],'READY',response.text)
   self.assertEqual(response.json()['new_orders'][0]['side'],'SELL')
   self.assertEqual(len(waits),1);self.assertGreater(waits[0],1);self.assertLess(waits[0],5)
   self.assertIs(c.provider.actions,original_actions);self.assertIs(c.provider.market,original_market)
   self.assertEqual(c.store.path.read_bytes(),before)

if __name__=='__main__':unittest.main()

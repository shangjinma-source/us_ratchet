from contextlib import nullcontext
from datetime import timedelta
from email.utils import format_datetime
from pathlib import Path
from hashlib import sha256
from datetime import datetime
from core.strategy_account_ledger import canonical
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from data.strategy_daily_market_capture_v3 import DailyMarketCaptureV3
from data.strategy_unified_server_preparation_v15 import attach_daily_rss_v15
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from fastapi import FastAPI,APIRouter
from fastapi.testclient import TestClient
from data.strategy_daily_rolling_admission_v5 import RollingDailyAdmissionV5
from data.strategy_daily_rolling_admission_v7 import RollingDailyAdmissionV7
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
    '</pubDate><item><title>Unrelated</title><pubDate>Mon, 02 Nov 2026 21:00:00 GMT</pubDate></item></channel></rss>').encode())
   # Only market leads; RSS stays in the past.
   c.provider.actions.rss_fetch=lambda:dict(status=200,body=b'<rss><channel><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated</title><pubDate>Mon, 02 Nov 2026 21:00:00 GMT</pubDate></item></channel></rss>')
   class Identity:
    def __call__(self,ticker):return dict(ticker=ticker,security_id={'AAA':'A','BBB':'B'}[ticker],source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
    def _read(self,path,h):return b'id'
   def fetch(ticker):
    start=int(datetime.fromisoformat('2026-11-02T14:30:00+00:00').timestamp());last=int(published.timestamp())
    return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),timestamp=[last-60],indicators=dict(quote=[dict(open=[10],high=[11],low=[9],close=[10],volume=[10])]))])))
   c.provider.market=StrategyAccountMarketCapture(identity_resolver=Identity(),fetch=fetch,clock=lambda:c.clock[0])
   original_actions=c.provider.actions;original_market=c.provider.market
   runtime=SimpleNamespace(execution_provider=c.provider.execution,selection=SimpleNamespace(fees='10'))
   c.monthly.root=Path(directory);c.monthly.snapshot_operation=lambda:nullcontext()
   c.monthly._for_target=lambda target:(runtime,{})
   daily=RollingDailyAdmissionV5(monthly=c.monthly,reader=c.reader,clock=lambda:c.clock[0],validate_code=lambda:None,policy_execution_enabled=True,policy_id=POLICY)
   journal=DailyAdviceJournalV1(Path(directory)/'observed.db',clock=lambda:c.clock[0])
   observed=ObservedDailyAdmission(service=daily,monthly=c.monthly,journal=journal,clock=lambda:c.clock[0],validate_sources=lambda:None,policy_references={'fixture_only':True})
   router=create_router(service=observed)
   prepared=dict(monthly=c.monthly,observed_daily=observed,advice_journal=journal,router=router,validate_code=lambda:None)
   request=dict(expected_revision=c.state['revision'],target_id=c.target['target_id'])
   before=c.store.path.read_bytes()
   with patch('data.strategy_daily_rolling_admission_v5.validate_account_identity_coverage'):
    old=FastAPI();old.include_router(router)
    response=TestClient(old).post('/api/strategy-daily-v3/preview',json=request)
   self.assertEqual(response.status_code,409,response.text)
   self.assertIn('INCOMPLETE_MARK_DOMAIN',response.text)
   new=attach_daily_rss_v15(prepared=prepared,validate_v15_sources=lambda:None)
   self.assertIs(new['observed_daily'].journal,journal)
   self.assertIs(new['observed_daily'].service.reader,c.reader)
   waits=[]
   def sleep(seconds):
    waits.append(seconds);c.clock[0]+=timedelta(seconds=seconds)
   app=FastAPI();app.include_router(new['router'])
   with patch('data.strategy_daily_rolling_admission_v7.validate_account_identity_coverage'),patch('data.strategy_daily_rolling_admission_v7.DailyMarketCaptureV3',side_effect=lambda **kwargs:DailyMarketCaptureV3(**kwargs,sleep=sleep,monotonic=lambda:sum(waits))):
    response=TestClient(app).post('/api/strategy-daily-v3/preview',json=request)
   self.assertEqual(response.status_code,200,response.text)
   self.assertEqual(response.json()['status'],'READY',response.text)
   self.assertEqual(response.json()['new_orders'][0]['side'],'SELL')
   self.assertGreater(sum(waits),1);self.assertLess(sum(waits),3)
   self.assertIs(c.provider.actions,original_actions);self.assertIs(c.provider.market,original_market)
   self.assertEqual(c.store.path.read_bytes(),before)
   # The same future-dated item must still block when it names a target issuer.
   prior_fetch=c.provider.actions.rss_fetch
   c.provider.actions.rss_fetch=lambda:dict(prior_fetch(),body=prior_fetch()['body'].replace(b'Unrelated',b'BBB reverse split'))
   with patch('data.strategy_daily_rolling_admission_v7.validate_account_identity_coverage'),patch('data.strategy_daily_rolling_admission_v7.DailyMarketCaptureV3',side_effect=lambda **kwargs:DailyMarketCaptureV3(**kwargs,sleep=sleep,monotonic=lambda:sum(waits))):
    denied=TestClient(app).post('/api/strategy-daily-v3/preview',json=request)
   self.assertEqual(denied.status_code,409,denied.text)
   self.assertIn('KNOWN_NOTICE_REQUIRES_REVIEW',denied.text)
   self.assertEqual(c.store.path.read_bytes(),before)

if __name__=='__main__':unittest.main()


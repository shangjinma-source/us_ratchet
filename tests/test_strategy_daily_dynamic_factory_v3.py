from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_dynamic_factory_v3 import run_dynamic_sources,FACTORY_SOURCES
import test_strategy_daily_domain_runner_v1 as fixtures

class DynamicFactoryTests(unittest.TestCase):
 def setup(self,folder):
  c,_,root=fixtures.DomainRunnerTests().setup(folder)
  calendar=json.loads((root/'calendar.json').read_bytes())
  calendar['sessions'].extend([dict(date=day,open=day+'T09:30:00-05:00',close=day+'T16:00:00-05:00')
    for day in ('2026-11-03','2026-11-04')])
  raw=canonical(calendar);(root/'dynamic-calendar.json').write_bytes(raw)
  pins=[]
  for name in FACTORY_SOURCES:
   body=(fixtures.fixtures.ROOT/name).read_bytes();path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
   pins.append(dict(path=name,sha256=sha256(body).hexdigest()))
  config=dict(official_time_policy='REAL_WAIT_CHANNEL_MAX_1S_ITEMS_AT_NETWORK_RECEIPT_V1',schema='SERVER_DYNAMIC_DAILY_SOURCE_V1',first_window_review_version='CLOSED_AT_ORIGINAL_RECEIPT_V2',source_pins=pins,
   calendar=dict(path='dynamic-calendar.json',sha256=sha256(raw).hexdigest()),identity=c.identity_reference,
   runs_root='dynamic-runs',first_execution_date='2026-11-02',target_evidence_root='capture',account_id=c.state['account_id'])
  calls=[]
  def fetch(ticker,*args):
   calls.append(ticker);today=c.clock[0].date().isoformat()
   dates=[row['date'] for row in calendar['sessions']];index=dates.index(today)
   window=calendar['sessions'][index-20:index]
   raw=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',
    instrumentType='EQUITY',exchangeName='NMS'),events={},
    timestamp=[int(datetime.fromisoformat(s['open']).timestamp()) for s in window],
    indicators=dict(quote=[dict(close=[100]*20)],adjclose=[dict(adjclose=[100]*20)]))])))
   return dict(status=200,body=raw)
  def run():
   raw=canonical(config)
   return run_dynamic_sources(root=root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
    account_reader=c.store.read,target_reader=lambda:c.target,execute=True,clock=lambda:c.clock[0],
    fetch_daily=fetch,fetch_official=lambda:dict(status=200,body=b'<rss><channel><title>Nasdaq</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'))
  return c,root,run,calls
 def test_same_security_rolls_without_requiring_stale_target_baseline(self):
  with TemporaryDirectory() as folder:
   c,root,run,calls=self.setup(folder);before=c.store.path.read_bytes()
   first=run();self.assertEqual(first['status'],'DYNAMIC_DOMAIN_PACKET_SAVED',first)
   self.assertEqual(first['routes'],{'B':'FIRST'})
   self.assertEqual(run()['status'],'EXISTING_DYNAMIC_PACKET_VERIFIED')
   c.clock[0]=datetime.fromisoformat('2026-11-03T15:00:00+00:00')
   second=run();self.assertEqual(second['status'],'DYNAMIC_DOMAIN_PACKET_SAVED',second)
   self.assertEqual(second['routes'],{'B':'ROLLING'});self.assertEqual(calls,['BBB','BBB'])
   self.assertEqual(c.store.path.read_bytes(),before)
 def test_missing_previous_day_does_not_fall_back_or_recollect(self):
  with TemporaryDirectory() as folder:
   c,root,run,calls=self.setup(folder);self.assertEqual(run()['status'],'DYNAMIC_DOMAIN_PACKET_SAVED')
   c.clock[0]=datetime.fromisoformat('2026-11-04T15:00:00+00:00')
   self.assertEqual(run()['status'],'WAIT_PREVIOUS_SESSION_EVIDENCE');self.assertEqual(len(calls),1)
 def test_new_holding_first_window_and_existing_holding_roll_together(self):
  with TemporaryDirectory() as folder:
   c,root,run,calls=self.setup(folder);self.assertEqual(run()['status'],'DYNAMIC_DOMAIN_PACKET_SAVED')
   c.clock[0]=datetime.fromisoformat('2026-11-03T15:00:00+00:00')
   from data.strategy_account_identity import PinnedStrategyIdentity
   from data.strategy_continuous32_target_decision import decide_target,REQUIRED_PINS
   resolver=PinnedStrategyIdentity(root,c.identity_reference['path'],c.identity_reference['sha256'])
   c.store.append(dict(event_id='new-a',kind='DIRECT_FILL',security_id='A',side='BUY',quantity=1,
    price='100',fees='0',executed_at='2026-11-02T15:00:00Z',identity_evidence=resolver('AAA')),
    expected_revision=c.store.read()['revision'])
   c.store.append(dict(event_id='newcash',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'),
    expected_revision=c.store.read()['revision'])
   from data.strategy_account_market_capture import StrategyAccountMarketCapture
   def minute_raw(ticker):
    last=int(c.clock[0].timestamp());start=last-1800
    return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',
     instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',
     regularMarketPrice=100,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),
     timestamp=[last-60],indicators=dict(quote=[dict(open=[100],high=[101],low=[99],close=[100],volume=[10])]))])))
   c.provider.market=StrategyAccountMarketCapture(identity_resolver=resolver,fetch=minute_raw,clock=lambda:c.clock[0],max_mark_age=120)
   state=c.store.read();args=c.provider.selection(state)
   for name in REQUIRED_PINS:
    body=(fixtures.fixtures.ROOT/name).read_bytes();args['source_package']['files'][name]=body
    args['source_package']['source_hashes'][name]=sha256(body).hexdigest()
   decision=decide_target(state=state,now=c.clock[0].isoformat(),maximum_mark_age_seconds=900,**args)
   c.target['payload'].update(decision=decision,target_quantities=decision['payload']['target_quantities'],
    created_at=c.clock[0].isoformat())
   c.target['target_id']=sha256(canonical(c.target['payload'])).hexdigest()
   before=c.store.path.read_bytes();result=run()
   self.assertEqual(result['status'],'DYNAMIC_DOMAIN_PACKET_SAVED',result)
   self.assertEqual(result['routes'],{'A':'FIRST','B':'ROLLING'})
   self.assertEqual(result['http_calls'],4);self.assertEqual(c.store.path.read_bytes(),before)

if __name__=='__main__':unittest.main()


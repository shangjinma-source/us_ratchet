"""Isolated approved fixture only: real rolling capture/normalization/reader/provider."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from core.strategy_account_ledger import canonical
from data.strategy_daily_rolling_runner_v3 import run_rolling_sources,V3_SOURCES
from data.strategy_daily_composition_v3 import DailyCompositionV3
from data.strategy_daily_signal_verifier import ROOT,POLICY
from data.strategy_profiled_rolling_packet_admission_v3 import ProfiledRollingSessionDailyReaderV3
import test_strategy_profiled_daily_packet_admission as fixtures

class RollingAdmissionTests(unittest.TestCase):
 def setup_case(self,directory):
  c=fixtures.ProfiledPacketTests().setup_case(directory);root=Path(directory)
  def save(name,value):
   raw=value if isinstance(value,bytes) else canonical(value);p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
   return dict(path=name,sha256=sha256(raw).hexdigest())
  calendar=json.loads((root/'calendar.json').read_bytes())
  calendar['sessions'].insert(0,dict(date='2026-10-02',open='2026-10-02T09:30:00-04:00',close='2026-10-02T16:00:00-04:00'))
  cal=save('rolling-calendar.json',calendar)
  release=json.loads((root/'release.json').read_bytes());release['calendar_sha256']=cal['sha256'];rel=save('rolling-release.json',release)
  receipt=json.loads((root/'parent.json').read_bytes());inputs=json.loads((root/'normalized.json').read_bytes())
  rows=calendar['sessions'][:20];days=[r['date'] for r in rows]
  inputs.update(signal_date=days[-1],session_dates=days,observed_at=rows[-1]['close'])
  inputs['session_close_times']['closes']={r['date']:r['close'] for r in rows}
  inputs['histories']['B']['units']['unit_asof']=days[-1]
  inputs['histories']['B']['closes']=[dict(date=r['date'],completed_at=r['close'],close='100') for r in rows]
  norm=save('rolling-seed-inputs.json',inputs)
  receipt.update(normalized_inputs_path=norm['path'],market_asof=rows[-1]['close'],source_received_at='2026-10-30T13:00:00Z',available_at='2026-10-30T13:01:00Z',execution_session=calendar['sessions'][-2],release_sha256=rel['sha256'])
  receipt['source_sha256'][norm['path']]=norm['sha256']
  seed=save('rolling-seed.json',receipt)
  pins=[save(name,(ROOT/name).read_bytes()) for name in sorted(V3_SOURCES)]
  security=dict(ticker='BBB',security_id='B',currency='USD',exchangeName='NMS',instrumentType='EQUITY')
  identity=save('rolling-identity.json',dict(schema='SERVER_CAPTURE_IDENTITY_V1',review_status='REVIEWED',security=security,fixture_only=True))
  capture=save('rolling-capture.json',dict(schema='SERVER_DAILY_SESSION_CAPTURE_V1',calendar=cal,identity_review=identity,security=security,source_pins=pins,output_root='rolling-capture'))
  config=dict(schema='SERVER_ROLLING_DAILY_SOURCE_V3',source_pins=pins,capture_configuration=capture,first_execution_date='2026-11-02',seed_receipt=seed,seed_source_paths={p:p for p in receipt['source_sha256']},accepted_prior_configuration_sha256=[],runs_root='rolling-runs',account_id=c.state['account_id'])
  cfg=save('rolling-pipeline.json',config)
  rows=calendar['sessions'][-21:-1]
  body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(security,symbol="BBB",exchangeTimezoneName="America/New_York"),timestamp=[int(datetime.fromisoformat(r['close']).timestamp()) for r in rows],indicators=dict(quote=[dict(close=[100]*20)],adjclose=[dict(adjclose=[100]*20)]))])))
  official=b'<rss version="2.0"><channel><title>Fixture</title><item><title>ZZZ fixture announcement</title><pubDate>Fri, 30 Oct 2026 12:00:00 GMT</pubDate><description>Fixture only</description></item></channel></rss>'
  result=run_rolling_sources(root=root,configuration_bytes=canonical(config),configuration_sha256=cfg['sha256'],execute=True,account_reader=c.store.read,target_reader=lambda:c.target,fetch_daily=lambda *a:dict(status=200,body=body),fetch_official=lambda:dict(status=200,body=official),clock=lambda:c.clock[0])
  self.assertEqual(result['status'],'DAILY_CONDITIONAL_PACKET_SAVED',(result,(root/'rolling-capture/2026-11-02/terminal.json').read_text()))
  reader=ProfiledRollingSessionDailyReaderV3(root=root,configuration_path=cfg['path'],configuration_sha256=cfg['sha256'],archive_root=root/'rolling-archive',release_path=rel['path'],trusted_release_sha256=rel['sha256'])
  c.service=DailyCompositionV3(monthly_service=c.monthly,evidence_reader=reader,execution_provider=c.provider.execution,clock=lambda:c.clock[0],policy_execution_enabled=True,policy_id=POLICY,fee_bps='10')
  return c
 def test_sell_actual_rolling_and_provider_no_account_write(self):
  with TemporaryDirectory() as directory:
   c=self.setup_case(directory);before=c.store.path.read_bytes();target=deepcopy(c.target)
   r=c.service.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])
   self.assertEqual(r['status'],'READY',r);self.assertEqual(r['new_orders'][0]['side'],'SELL');self.assertTrue(r['evidence_archive']);self.assertEqual(c.store.path.read_bytes(),before);self.assertEqual(c.target,target)



 def test_buy_hold_and_missing_packet_with_real_account_rebinding(self):
     for mode in ('BUY','HOLD','WAIT'):
         with self.subTest(mode=mode),TemporaryDirectory() as directory:
             c=self.setup_case(directory)
             half=c.target['payload']['target_quantities']['B']//2
             if mode in ('BUY','HOLD'):
                 quantity=14 if mode=='BUY' else 14-half
                 identity=c.state['events'][0]['payload']['identity_evidence']
                 c.store.append(dict(event_id='sell-after-target',kind='DIRECT_FILL',security_id='B',side='SELL',quantity=quantity,price='10',fees='0',executed_at=c.clock[0].isoformat(),identity_evidence=identity),expected_revision=c.state['revision'])
                 c.store.append(dict(event_id='cash-after-fill',kind='CASH_CONFIRM',amount='1000' if mode=='BUY' else '0',cash_basis='TOTAL_UNINVESTED'),expected_revision=c.store.read()['revision'])
                 c.state=c.store.read()
                 if mode=='BUY':
                     class Identity:
                         def __call__(self,ticker):
                             return dict(ticker=ticker,security_id='B',source_references=['identity-only'],
                                 source_hashes={'identity-only':sha256(b'id').hexdigest()})
                         def _read(self,*args):return b'id'
                     def raw(ticker):
                         opening=int(datetime.fromisoformat('2026-11-02T14:30:00+00:00').timestamp())
                         last=opening+1800
                         return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,
                             currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',
                             dataGranularity='1m',regularMarketPrice=10,regularMarketTime=last,
                             currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400))),
                             timestamp=list(range(opening,last,60)),indicators=dict(quote=[dict(
                                 open=[10]*30,high=[11]*30,low=[9]*30,close=[10]*30,volume=[10]*30)]))])))
                     c.provider.market=StrategyAccountMarketCapture(identity_resolver=Identity(),
                         fetch=raw,clock=lambda:c.clock[0],max_mark_age=120)
             else:
                 (Path(directory)/'rolling-runs/2026-11-02/terminal.json').rename(Path(directory)/'saved-terminal.json')
             before=c.store.path.read_bytes()
             result=c.service.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])
             self.assertEqual(result['status'],'READY' if mode=='BUY' else mode,result)
             self.assertEqual(c.store.path.read_bytes(),before)
             if mode=='BUY':self.assertEqual(result['new_orders'][0]['side'],'BUY')
             else:self.assertEqual(result['new_orders'],[])
 def test_http_real_reader_ready_then_missing_parent_no_quotes(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from api.strategy_daily_preview_v3 import create_router
  with TemporaryDirectory() as directory:
   c=self.setup_case(directory);app=FastAPI();app.include_router(create_router(service=c.service))
   body=dict(expected_revision=c.state['revision'],target_id=c.target['target_id'])
   with TestClient(app) as client:
    response=client.post('/api/strategy-daily-v3/preview',json=body)
    self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['status'],'READY')
    (Path(directory)/'rolling-seed.json').rename(Path(directory)/'removed-seed.json')
    def forbidden(*args,**kwargs):raise AssertionError('must not quote without parent chain')
    c.provider.market.capture=forbidden
    response=client.post('/api/strategy-daily-v3/preview',json=body)
    self.assertEqual(response.status_code,409,response.text);self.assertEqual(response.json()['status'],'WAIT');self.assertEqual(response.json()['new_orders'],[])

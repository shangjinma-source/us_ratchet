from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_first_window_v2 import review_first_window,SOURCES
from data.strategy_daily_security_domain_v1 import locate_unit_baseline_sources
from data.current_quantity_v2_paper_action_sources import daily_url
from scripts.current_research_official_alert_capture import URL
from data.strategy_account_action_capture import StrategyAccountActionCapture
import test_strategy_daily_security_domain_v1 as fixtures

ROOT=Path(__file__).resolve().parents[1]

class FirstWindowTests(unittest.TestCase):
 def case(self,folder,mode=None):
  original=StrategyAccountActionCapture.__init__
  def initialize(instance,**kwargs):
   fetch=kwargs['fetch']
   def augmented(*args,**kw):
    result=fetch(*args,**kw);doc=json.loads(result['body']);row=doc['chart']['result'][0]
    row['meta']['exchangeName']='NMS'
    row.update(timestamp=[int(datetime.fromisoformat(day).timestamp()) for day in ('2026-10-30T13:30:00+00:00','2026-11-02T14:30:00+00:00')],
     indicators=dict(quote=[dict(close=[100,90])],adjclose=[dict(adjclose=[100,90])]))
    if mode=='no_completed':
     row['timestamp']=row['timestamp'][1:];row['indicators']['quote'][0]['close']=[90];row['indicators']['adjclose'][0]['adjclose']=[90]
    if mode=='future_baseline':row['timestamp'][-1]=int(datetime.fromisoformat('2026-11-03T14:30:00+00:00').timestamp())
    return dict(result,body=canonical(doc))
   original(instance,**dict(kwargs,fetch=augmented))
  with patch.object(StrategyAccountActionCapture,'__init__',initialize):
   c=fixtures.DynamicDomainTests().case(folder)
  root=Path(folder);pins=[]
  for name in SOURCES:
   path=root/name;path.parent.mkdir(parents=True,exist_ok=True);body=(ROOT/name).read_bytes();path.write_bytes(body)
   pins.append(dict(path=name,sha256=sha256(body).hexdigest()))
  c.clock[0] += timedelta(days=1)
  cal=json.loads((root/'calendar.json').read_bytes())
  cal['sessions'].append(dict(date='2026-11-03',open='2026-11-03T14:30:00+00:00',close='2026-11-03T21:00:00+00:00'))
  calendar=canonical(cal);(root/'calendar.json').write_bytes(calendar)
  sessions=cal['sessions'];window=sessions[-21:-1]
  config=dict(schema='SERVER_FIRST_DAILY_WINDOW_V2',source_pins=pins,identity=c.identity_reference,
   calendar=dict(path='calendar.json',sha256=sha256(calendar).hexdigest()),security_id='B',release_sha256=None,
   unit_source_paths=locate_unit_baseline_sources(root=root,evidence_root='capture',
    binding=c.target['payload']['decision']['payload']['input_binding']))
  daily=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol='BBB',currency='USD',instrumentType='EQUITY',
   exchangeName='NMS'),events={},timestamp=[int(datetime.fromisoformat(s['open']).timestamp()) for s in window],
   indicators=dict(quote=[dict(close=[100]*20)],adjclose=[dict(adjclose=[100]*20)]))])))
  official=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
  captured={};start=c.clock[0]-timedelta(minutes=1)
  for name,body in [('daily',daily),('official',official)]:
   captured[name+'.response.bin']=body
   captured[name+'.receipt.json']=canonical(dict(status='CAPTURED',attempts=1,http_status=200,
    raw_sha256=sha256(body).hexdigest(),stored_bytes=len(body),started_at=start.isoformat(),received_at=start.isoformat(),
    url=daily_url('BBB',datetime.fromisoformat(window[0]['open'])-timedelta(days=1),start) if name=='daily' else URL))
  return c,config,captured
 def run_case(self,folder,c,config,captured):
  body=canonical(config)
  return review_first_window(root=folder,configuration_bytes=body,configuration_sha256=sha256(body).hexdigest(),
   capture_files=captured,state=c.state,target=c.target,clock=lambda:c.clock[0])
 def test_new_sid_own_baseline_and_saved_twenty_window(self):
  with TemporaryDirectory() as folder:
   c,config,captured=self.case(folder);before=c.store.path.read_bytes()
   result=self.run_case(folder,c,config,captured)
   self.assertEqual(result['status'],'FIRST_WINDOW_CONDITIONALLY_REVIEWED_POLICY_UNRELEASED',result)
   self.assertIsNone(result['receipt']['release_sha256'])
   self.assertFalse(result['receipt']['source_authenticated'])
   units=next(json.loads(raw) for name,raw in result['files'].items() if name.endswith('/units.json'))
   self.assertEqual(units['overlap_exact_dates'],['2026-10-30'])
   self.assertEqual([row['date'] for row in units['excluded_unclosed_baseline_bars']],['2026-11-02'])
   self.assertEqual(c.store.path.read_bytes(),before)
   inputs=json.loads(result['files'][result['receipt']['normalized_inputs_path']])
   self.assertEqual(len(inputs['histories']['B']['closes']),20)
 def test_conflicts_wait_without_policy_or_account_mutation(self):
  with TemporaryDirectory() as folder:
   c,config,captured=self.case(folder)
   for kind in ('price','event','identity','future','future_bar','release'):
    cfg=deepcopy(config);cap=deepcopy(captured)
    if kind=='release':cfg['release_sha256']='a'*64
    elif kind=='future':
     rec=json.loads(cap['daily.receipt.json']);rec['received_at']='2099-01-01T00:00:00Z';cap['daily.receipt.json']=canonical(rec)
    else:
     doc=json.loads(cap['daily.response.bin']);row=doc['chart']['result'][0]
     if kind=='price':
      row['indicators']['quote'][0]['close'][-2]=101;row['indicators']['adjclose'][0]['adjclose'][-2]=101
     if kind=='future_bar':row['timestamp'][-1]=int((c.clock[0]+timedelta(hours=1)).timestamp())
     if kind=='event':row['events']={'splits':{'x':{}}}
     if kind=='identity':row['meta']['symbol']='SNDK'
     body=canonical(doc);cap['daily.response.bin']=body;rec=json.loads(cap['daily.receipt.json'])
     rec.update(raw_sha256=sha256(body).hexdigest(),stored_bytes=len(body));cap['daily.receipt.json']=canonical(rec)
    with self.subTest(kind=kind):
     result=self.run_case(folder,c,cfg,cap);self.assertEqual(result['status'],'WAIT_FIRST_WINDOW_REVIEW',result)
     self.assertIsNone(result['receipt'])

 def test_no_completed_overlap_and_future_baseline_wait(self):
  for mode,reason in [('no_completed','WAIT_BASELINE_RAW_PRICE_OVERLAP'),('future_baseline','FIRST_BASELINE_FUTURE_BAR')]:
   with self.subTest(mode=mode),TemporaryDirectory() as folder:
    c,config,captured=self.case(folder,mode)
    result=self.run_case(folder,c,config,captured)
    self.assertEqual(result['status'],'WAIT_FIRST_WINDOW_REVIEW',result)
    self.assertEqual(result['reason'],reason)

if __name__=='__main__':unittest.main()



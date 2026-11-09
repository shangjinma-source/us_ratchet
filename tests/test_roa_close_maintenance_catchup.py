"""Real composition and recovery; only market/calendar transport replaced."""
import asyncio,json,importlib.util,os,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from unittest.mock import patch
from hashlib import sha256
from api.strategy_account import create_router
from data import roa_account_composition as production
if os.getenv('ROA_COMPOSITION_OVERRIDE'):
 spec=importlib.util.spec_from_file_location('catchup_candidate',os.environ['ROA_COMPOSITION_OVERRIDE']);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
else:module=production
class Signal:
 def __init__(self,**kw):self.refreshes=0
 def frozen_roster(self):return []
 def refresh_completed(self):self.refreshes+=1;return {'status':'UPDATED'}
 def __call__(self):raise ValueError('WAIT_DAILY_MARKET_SIGNAL')
class Calendar:
 def __init__(self,root):self.p=Path(root)/'calendar';self.p.write_text('synthetic')
 def sessions(self):return ['2026-11-05','2026-11-06','2026-11-09','2026-11-10']
 def __call__(self,d):
  if d not in self.sessions():raise ValueError('SESSION_NOT_IN_CALENDAR')
  i=self.sessions().index(d)
  return dict(open_at=d+'T14:30:00Z',close_at=d+'T21:00:00Z',previous_session=self.sessions()[i-1] if i else '2026-11-04',source_hashes={str(self.p):sha256(self.p.read_bytes()).hexdigest()})
class CatchupTests(unittest.TestCase):
 def fixture(self,mode):
  with TemporaryDirectory() as folder:
   root=Path(folder);now=[datetime.fromisoformat('2026-11-06T14:31:00+00:00')]
   router=create_router(database_path=root/'account.db',account_id='A',resolver=lambda _:None,clock=lambda:now[0])
   cfg=dict(account_id='A',strategy_epoch='E',contract_sha256='a'*64,contract_hashes={},daily_signal_path='data/strategy_account/daily',lifecycle_path='data/strategy_account/life',close_evidence_path='data/strategy_account/close',close_recovery_path='data/strategy_account/recovery')
   fetched=[]
   def prices(**kw):
    fetched.append(kw['session'])
    if mode=='missing':raise ValueError('WAIT_CLOSE_PRICE')
    return dict(prices={},evidence={})
   with patch.object(module,'RoaDailySignalProvider',Signal),patch.object(module,'RoaSessionReader',Calendar),patch.object(module,'load_completed_close_prices',prices):
    prepared=module.attach_roa(prepared={'router':router},root=root,configuration=cfg,validate_sources=lambda:None,clock=lambda:now[0]);a=prepared['roa_service'].account_service;a.initialize({'event_id':'init'});a.append(dict(expected_revision=a.store.read()['revision'],event=dict(kind='CASH_CONFIRM',event_id='cash',amount='1000',cash_basis='TOTAL_UNINVESTED')))
    life=prepared['roa_service'].lifecycle
    if mode!='no_plan':
     state=life.plan(signal=dict(signal_date='2026-11-05',decision_date='2026-10-30',risk_on=True,weights={'X':'1/10'},signal_id='b'*64),session='2026-11-06',open_at='2026-11-06T14:30:00Z',open_until='2026-11-06T14:45:00Z',close_at='2026-11-06T20:55:00Z',close_until='2026-11-06T21:00:00Z')
     life.materialize_open(event_id=state['events'][0]['event_id'],account=a.store.read(),opening_prices={'X':'100'},now=now[0].isoformat())
    before=a.store.read();now[0]=datetime.fromisoformat('2026-11-10T14:00:00+00:00' if mode=='multi' else '2026-11-09T14:00:00+00:00');prepared['roa_maintain_completed_session']()
    if mode=='missing':
     self.assertEqual(prepared['roa_maintenance_status']['reason'],'WAIT_CLOSE_PRICE');self.assertIsNone(life.read().get('last_close'));self.assertEqual(prepared['roa_signal_provider'].refreshes,0)
    elif mode=='no_plan':
     self.assertEqual(prepared['roa_signal_provider'].refreshes,1);self.assertEqual(fetched,[])
    else:
     self.assertEqual(life.read()['last_close'],'2026-11-09' if mode=='multi' else '2026-11-06');self.assertEqual(fetched,['2026-11-06','2026-11-09'] if mode=='multi' else ['2026-11-06']);self.assertEqual(prepared['roa_signal_provider'].refreshes,1)
     prepared['roa_maintain_completed_session']();self.assertEqual(len(fetched),2 if mode=='multi' else 1)
    self.assertEqual(a.store.read(),before)
    endpoint=next(r.endpoint for r in prepared['router'].routes if r.path=='/api/strategy-roa/maintenance-status')
    recovery_before=life.read();fetches_before=list(fetched)
    response=asyncio.run(endpoint());health=json.loads(response.body)
    self.assertFalse(health['running']);self.assertFalse(health['worker_alive'])
    self.assertEqual(health['last_finished_at'],now[0].isoformat())
    self.assertEqual(health['status'],'WAIT' if mode=='missing' else 'COMPLETE')
    self.assertEqual(response.headers['cache-control'],'no-store')
    self.assertEqual(a.store.read(),before);self.assertEqual(life.read(),recovery_before);self.assertEqual(fetched,fetches_before)
    if mode=='no_plan':
     async def check_worker():
      async with prepared['router'].lifespan_context(None):
       health=json.loads((await endpoint()).body)
       self.assertTrue(health['worker_alive'])
      self.assertFalse(json.loads((await endpoint()).body)['worker_alive'])
     asyncio.run(check_worker())
     self.assertEqual(a.store.read(),before)
 def test_restart_preopen_recovers_friday(self):self.fixture('single')
 def test_multiple_missed_closes_are_contiguous(self):self.fixture('multi')
 def test_market_updates_without_lifecycle_plan(self):self.fixture('no_plan')
 def test_missing_prices_do_not_mark_complete(self):self.fixture('missing')
if __name__=='__main__':unittest.main()

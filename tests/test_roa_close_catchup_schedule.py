"""Bounded maintenance scheduling tests; real recovery tested separately."""
import ast,copy,os,unittest
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from threading import RLock
from types import SimpleNamespace
import logging
class CatchupTests(unittest.TestCase):
 def run_case(self,now,state,days):
  source=Path(os.environ.get('ROA_COMPOSITION_OVERRIDE','data/roa_account_composition.py')).read_text(encoding='utf-8');tree=ast.parse(source)
  fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='maintain_completed_session')
  calls=[];store=copy.deepcopy(state);status={}
  class Calendar:
   def sessions(self):return list(days)
   def __call__(self,d):return {'close_at':days[d]}
  def observe(d):calls.append(d);store['last_close']=d;return {'account_revision':'r'}
  def require(ok,reason):
   if not ok:raise ValueError(reason)
  env=dict(clock=lambda:datetime.fromisoformat(now),ZoneInfo=ZoneInfo,datetime=datetime,logging=logging,validate_sources=lambda:None,calendar=Calendar(),lifecycle=SimpleNamespace(read=lambda:copy.deepcopy(store)),account=SimpleNamespace(store=SimpleNamespace(read=lambda:{'revision':'r'})),service=SimpleNamespace(lock=RLock()),observe_completed_session=observe,signal=SimpleNamespace(refresh_completed=lambda:{'status':'UPDATED'}),maintenance_status=status,require=require,require_stop_history=lambda:None)
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual-maintenance>','exec'),env);env['maintain_completed_session']();return calls,status
 def test_first_close_none_weekend_and_monday_premarket(self):
  days={'2026-11-06':'2026-11-06T21:00:00+00:00','2026-11-09':'2026-11-09T21:00:00+00:00'}
  state={'last_close':None,'events':[{'phase':'OPEN','session':'2026-11-06','materialized_revision':'r'}]}
  for now in ['2026-11-07T12:00:00+00:00','2026-11-09T14:00:00+00:00']:
   calls,status=self.run_case(now,state,days);self.assertEqual(calls,['2026-11-06']);self.assertEqual(status['status'],'COMPLETE')
 def test_multiple_missing_and_halfday_exact_boundary(self):
  days={'2026-11-25':'2026-11-25T21:00:00+00:00','2026-11-27':'2026-11-27T18:00:00+00:00','2026-11-30':'2026-11-30T21:00:00+00:00'}
  state={'last_close':'2026-11-25','events':[]}
  calls,_=self.run_case('2026-11-27T17:59:59+00:00',state,days);self.assertEqual(calls,['2026-11-25'])
  calls,_=self.run_case('2026-11-27T18:00:00+00:00',state,days);self.assertEqual(calls,['2026-11-25','2026-11-27'])
  calls,_=self.run_case('2026-12-01T12:00:00+00:00',state,days);self.assertEqual(calls,list(days))
 def test_no_fabricated_initial_start_and_materialized_boundary(self):
  days={'2026-11-06':'2026-11-06T21:00:00+00:00','2026-11-09':'2026-11-09T21:00:00+00:00'}
  calls,_=self.run_case('2026-11-10T12:00:00+00:00',{'last_close':None,'events':[]},days);self.assertEqual(calls,[])
  state={'last_close':None,'events':[{'phase':'OPEN','session':'2026-11-06'},{'phase':'OPEN','session':'2026-11-09','materialized_revision':'later'}]}
  calls,status=self.run_case('2026-11-10T12:00:00+00:00',state,days);self.assertEqual(calls,[]);self.assertEqual(status['reason'],'WAIT_CLOSE_HISTORY_RECONCILIATION')
if __name__=='__main__':unittest.main()

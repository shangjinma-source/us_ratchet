"""Actual journal stop completion survives offline recovery without fabricated fills."""
import importlib.util,os,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
if os.environ.get('ROA_RECOVERY_OVERRIDE'):
 spec=importlib.util.spec_from_file_location('data.roa_close_recovery',os.environ['ROA_RECOVERY_OVERRIDE']);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
import test_roa_close_recovery_sqlite_20261106 as fixture
class OfflineStopTests(fixture.SqliteRecoveryTests):
 def completed(self,off=False):
  self.late_buy();self.recovery.observe('2026-11-06');self.now=datetime(2026,11,10,12,tzinfo=timezone.utc)
  self.append(dict(event_id='sell',kind='DIRECT_FILL',security_id='X',side='SELL',quantity=9,price='75',fees='0',executed_at='2026-11-09T20:59:00Z'))
  if off:
   self.life.plan(signal=dict(signal_date='2026-11-06',decision_date='2026-10-30',risk_on=False,weights={'X':'1/10'},signal_id='c'*64),session='2026-11-09',open_at='2026-11-09T14:30:00Z',open_until='2026-11-09T14:45:00Z',close_at='2026-11-09T20:55:00Z',close_until='2026-11-09T21:00:00Z')
   # No synthetic fill or materialization: preserve only recorded OFF plan as original rule exception.
   state=self.life.read();state['events']=[e for e in state['events'] if e['phase']!='CLOSE'];self.life._save(state)
  self.recovery.sessions=['2026-11-05','2026-11-06','2026-11-09'];self.recovery.calendar=lambda d:dict(close_at=d+'T21:00:00Z',previous_session='2026-11-06' if d=='2026-11-09' else '2026-11-05')
  before=self.store.read();events=self.life.read()['events'];self.recovery.observe('2026-11-09');self.assertEqual(self.store.read(),before);self.assertEqual(self.life.read()['events'],events)
 def materialize(self,day,decision):
  self.now=datetime.fromisoformat(day+'T14:31:00+00:00');self.append(dict(event_id='confirm-'+day,kind='CASH_CONFIRM',amount='9000',cash_basis='TOTAL_UNINVESTED'))
  # Explicit market OFF->ON so there is a genuine new OPEN event, retaining same-month stops.
  state=self.life.read();state['risk_on']=False;self.life._save(state)
  state=self.life.plan(signal=dict(signal_date=day[:-2]+'01' if day.endswith('02') else '2026-11-09',decision_date=decision,risk_on=True,weights={'X':'1/10'},signal_id='d'*64),session=day,open_at=day+'T14:30:00Z',open_until=day+'T14:45:00Z',close_at=day+'T20:55:00Z',close_until=day+'T21:00:00Z')
  event=next(e for e in reversed(state['events']) if e['phase']=='OPEN');return self.life.materialize_open(event_id=event['event_id'],account=self.store.read(),opening_prices={'X':'100'},now=day+'T14:31:00Z')
 def test_full_exit_same_month_on_cannot_rebuy(self):
  self.completed();self.assertEqual(self.life.read()['stopped'],['X']);self.assertNotIn('X',self.materialize('2026-11-10','2026-10-30')['targets'])
 def test_next_month_reset_allows(self):
  self.completed();self.assertGreater(self.materialize('2026-12-02','2026-11-30')['targets']['X'],0);self.assertEqual(self.life.read()['stopped'],[])
 def test_same_day_risk_off_exception(self):
  self.completed(off=True);self.assertEqual(self.life.read()['stopped'],[]);self.assertGreater(self.materialize('2026-11-10','2026-10-30')['targets']['X'],0)
if __name__=='__main__':unittest.main()

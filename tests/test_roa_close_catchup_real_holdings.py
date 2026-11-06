"""Actual SQLite fills for historical close recovery; no production writes."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from data.roa_close_recovery import holdings_at
from datetime import datetime,timezone
from test_roa_close_recovery_sqlite_20261106 import SqliteRecoveryTests
class RealHeldRecoveryTests(SqliteRecoveryTests):
 def test_actual_held_stop_date_and_late_recorded_shares(self):
  self.late_buy();before=self.store.read()
  self.now=datetime(2026,11,10,14,tzinfo=timezone.utc)
  self.recovery.sessions=['2026-11-05','2026-11-06','2026-11-09','2026-11-10']
  self.recovery.calendar=lambda d:dict(close_at=d+'T21:00:00Z',previous_session={'2026-11-06':'2026-11-05','2026-11-09':'2026-11-06','2026-11-10':'2026-11-09'}[d])
  captured=[];original=self.capture
  def prices(d,shares):
   captured.append((d,dict(shares)));return dict(original(d,shares),prices={'X':'100' if d=='2026-11-06' else '75'})
  self.recovery.price_reader=prices
  self.recovery.observe('2026-11-06');self.recovery.observe('2026-11-09')
  self.assertEqual(captured,[('2026-11-06',{'X':9}),('2026-11-09',{'X':9})]);self.assertEqual(self.life.read()['pending'],['X'])
  state=self.life.plan(signal=dict(signal_date='2026-11-09',decision_date='2026-10-30',risk_on=True,weights={'X':'1/10'},signal_id='c'*64),session='2026-11-10',open_at='2026-11-10T14:30:00Z',open_until='2026-11-10T14:45:00Z',close_at='2026-11-10T20:55:00Z',close_until='2026-11-10T21:00:00Z')
  closes=[e for e in state['events'] if e['phase']=='CLOSE'];self.assertEqual(len(closes),1);self.assertEqual(closes[0]['session'],'2026-11-10')
  self.assertFalse(self.life.event_view(now='2026-11-10T14:00:00Z')['executable'])
  self.assertEqual(self.life.event_view(now='2026-11-10T20:56:00Z')['event']['session'],'2026-11-10')
  self.assertEqual(self.store.read(),before)
 def test_missed_offline_stop_guard_preserves_actual_pending(self):
  import ast,os
  from core.strategy_account_ledger import require
  self.late_buy();self.recovery.observe('2026-11-06');before=self.store.read()
  self.now=datetime(2026,11,10,12,tzinfo=timezone.utc)
  source=Path(os.environ.get('ROA_COMPOSITION_OVERRIDE','data/roa_account_composition.py')).read_text(encoding='utf-8')
  fn=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=='require_stop_history')
  class Calendar:
   def sessions(inner):return ['2026-11-06','2026-11-09','2026-11-10']
   def __call__(inner,day):return dict(close_at=day+'T21:00:00+00:00')
  env=dict(account=SimpleNamespace(store=self.store),holdings_at=holdings_at,lifecycle=self.life,calendar=Calendar(),clock=lambda:self.now,datetime=datetime,require=require)
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual-guard>','exec'),env)
  with self.assertRaisesRegex(ValueError,'WAIT_CLOSE_HISTORY_RECONCILIATION'):env['require_stop_history']()
  self.assertEqual(self.life.read()['pending'],['X']);self.assertEqual(self.life.read()['last_close'],'2026-11-06');self.assertEqual(self.store.read(),before)
  # The next valid execution close has not yet passed: do not block legitimate next-session planning.
  self.now=datetime(2026,11,9,20,56,tzinfo=timezone.utc);env['require_stop_history']()
 def test_on_time_full_exit_partial_exit_and_late_exit(self):
  import ast,os
  from core.strategy_account_ledger import require
  self.late_buy();self.recovery.observe('2026-11-06');self.now=datetime(2026,11,10,12,tzinfo=timezone.utc)
  fn=next(n for n in ast.walk(ast.parse(Path(os.environ.get('ROA_COMPOSITION_OVERRIDE','data/roa_account_composition.py')).read_text(encoding='utf-8'))) if isinstance(n,ast.FunctionDef) and n.name=='require_stop_history')
  class Calendar:
   def sessions(inner):return ['2026-11-06','2026-11-09','2026-11-10']
   def __call__(inner,day):return dict(close_at=day+'T21:00:00+00:00')
  env=dict(account=SimpleNamespace(store=self.store),holdings_at=holdings_at,lifecycle=self.life,calendar=Calendar(),clock=lambda:self.now,datetime=datetime,require=require)
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual-guard>','exec'),env)
  self.append(dict(event_id='partial',kind='DIRECT_FILL',security_id='X',side='SELL',quantity=4,price='75',fees='0',executed_at='2026-11-09T20:59:00Z'))
  before=self.store.read()
  with self.assertRaisesRegex(ValueError,'WAIT_CLOSE_HISTORY_RECONCILIATION'):env['require_stop_history']()
  self.assertEqual(self.store.read(),before)
  self.append(dict(event_id='rest',kind='DIRECT_FILL',security_id='X',side='SELL',quantity=5,price='75',fees='0',executed_at='2026-11-09T20:59:30Z'))
  before=self.store.read();env['require_stop_history']();self.assertEqual(self.store.read(),before)
  # Independently rebuild a second real store, same fills except final sell after scheduled close.
  from core.strategy_account_store import StrategyAccountStore
  other=StrategyAccountStore(self.root/'late.db',clock=lambda:self.now);other.initialize('A',operation_id='init')
  for row in before['events'][1:]:
   event=dict(row['payload'])
   if event.get('event_id')=='rest':event['executed_at']='2026-11-09T21:01:00Z'
   other.append(event,expected_revision=other.read()['revision'])
  env['account']=SimpleNamespace(store=other)
  with self.assertRaisesRegex(ValueError,'WAIT_CLOSE_HISTORY_RECONCILIATION'):env['require_stop_history']()
if __name__=='__main__':unittest.main()


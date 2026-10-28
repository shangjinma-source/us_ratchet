"""Isolated synthetic atomic-risk tests; no account or network access."""
import os
import importlib.util,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
from copy import deepcopy
STAGE=Path(os.environ.get('REENTRY_CANDIDATE_ROOT', '.'))
for name,path in [('core.reentry_reference_v1',STAGE/'core/reentry_reference_v1.py'),('staged_store',STAGE/'data/monthly_peak_exit_reentry_store_v1.py')]:
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
from core.reentry_reference_v1 import execution_targets,recover
Store=sys.modules['staged_store'].MonthlyPeakExitReentryStore
H='a'*64
class ReferenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'risk.sqlite';self.store=Store(self.path)
  self.store.activate_reference(account_id='A',activation_id=H,activation_at='2026-10-01T12:00:00Z',activation_session='2026-10-01',account_revision='r0',source_configuration_sha256=H)
 def observation(self,day,price,epoch='2026-10-01'):
  return dict(decision_date=epoch,session_date=day,closes={'S':str(price)},unit_ids={'S':'u1'},evidence_sha256=H)
 def context(self,day,held=10):return dict(completed_at=day+'T20:00:00Z',holdings=dict(session_date=day,account_id='A',account_revision='r1',shares={'S':held},unit_ids={'S':'u1'},evidence_sha256=H,event_boundary_sha256=H))
 def advance(self,day,price,held=10,epoch='2026-10-01',**kw):
  old=self.store.read('A');ref=self.store.read_reference('A')
  return self.store.advance(account_id='A',expected_previous_session=old['session_date'] if old else None,observations=[self.observation(day,price,epoch)],baseline_targets={'S':10},expected_reference_version=ref['version'],activation_id=H,session_contexts={day:self.context(day,held)},**kw)
 def locked(self):self.advance('2026-10-01',100);return self.advance('2026-10-02',79)['reference_state']
 def evidence(self,lock,prices=(78,80,70)):
  dates=['2026-10-05','2026-10-06','2026-10-07'][:len(prices)]
  return dict(status='AUTHENTICATED_COMPLETE_REFERENCE_INTERVAL',evidence_sha256=H,exit_session=lock['exit_session'],origin_security_id='S',origin_unit_id='u1',expected_sessions=dates,completed_through=dates[-1],as_of='2026-10-08T12:00:00Z',rows=[dict(session_date=d,completed=True,completed_at=d+'T20:00:00Z',security_id='S',unit_id='u1',close=str(p)) for d,p in zip(dates,prices)])
 def test_unfilled_exit_and_repeated_refresh(self):
  s=self.locked();self.assertEqual(s['locks']['S']['reference_price'],'79');self.assertEqual(self.advance('2026-10-02',79)['reference_state'],s)
  self.assertEqual(self.store.read('A')['exited'],['S'])
 def test_zero_hold_no_later_backfill(self):
  self.advance('2026-10-01',100);r=self.advance('2026-10-02',79,0);self.assertEqual(r['reference_state']['locks'],{})
  # Same historical evidence must be unchanged; a later session can have new shares.
  self.assertEqual(self.advance('2026-10-05',78,10)['reference_state']['locks'],{})
 def test_atomic_failure_after_both_writes(self):
  self.advance('2026-10-01',100);old=self.store.read('A');ref=self.store.read_reference('A')
  def fail(c):
   self.assertIn('S',__import__('json').loads(c.execute('SELECT state FROM reentry_state').fetchone()[0])['locks']);raise RuntimeError('SIMULATED_COMMIT_FAILURE')
  self.store.before_commit=fail
  with self.assertRaises(RuntimeError):self.advance('2026-10-02',79)
  self.assertEqual(self.store.read('A'),old);self.assertEqual(self.store.read_reference('A'),ref)
  self.store.before_commit=None;self.assertIn('S',self.advance('2026-10-02',79)['reference_state']['locks'])
 def test_month_reset_preserves_lock(self):
  s=self.locked();r=self.advance('2026-11-02',75,0,'2026-11-02',authorized_monthly_reset='2026-11-02')
  self.assertEqual(r['reference_state']['locks'],s['locks']);self.assertEqual(r['effective_target_quantities'],{'S':10});self.assertEqual(execution_targets(state=r['reference_state'],effective_targets={'S':10},actual_shares={'S':0},decision_date='2026-10-02'),{'S':0})
 def test_original_sell_not_changed(self):
  s=self.locked();self.assertEqual(execution_targets(state=s,effective_targets={'S':3},actual_shares={'S':8},decision_date='2026-10-02'),{'S':3});self.assertEqual(execution_targets(state=s,effective_targets={'S':12},actual_shares={'S':8},decision_date='2026-10-02'),{'S':8})
 def test_mid_recovery_latches(self):
  s=self.locked();e=self.evidence(s['locks']['S']);r=recover(state=s,security_id='S',evidence=e,decision_session=e['completed_through']);self.assertEqual(r['locks'],{});self.assertEqual(r['releases'][0]['recovered_session'],'2026-10-06')
 def test_split_no_recovery_projects_new_sid(self):
  s=self.locked();e=self.evidence(s['locks']['S'],(7,));row=e['rows'][0];row.update(security_id='N',unit_id='u2',conversion=dict(kind='REVIEWED_INTEGER_SPLIT',timing='BEFORE_OPEN',old_security_id='S',old_unit_id='u1',new_security_id='N',new_unit_id='u2',ratio='10',evidence_sha256=H))
  r=recover(state=s,security_id='S',evidence=e,decision_session=e['completed_through']);self.assertEqual(execution_targets(state=r,effective_targets={'N':10},actual_shares={'N':0},decision_date='2026-10-05'),{'N':0})
 def test_intraday_future_exit_day_rejected(self):
  s=self.locked()
  for mutation in ['completed','future','exitday','unit']:
   e=self.evidence(s['locks']['S'],(100,));row=e['rows'][0]
   if mutation=='completed':row['completed']=False
   if mutation=='future':row['completed_at']='2026-10-09T20:00:00Z'
   if mutation=='exitday':row['session_date']='2026-10-02';e['expected_sessions']=['2026-10-02'];e['completed_through']='2026-10-02'
   if mutation=='unit':row['unit_id']='unknown'
   with self.assertRaises(ValueError):recover(state=s,security_id='S',evidence=e,decision_session=e['completed_through'])
 def test_stale_revision_rejected(self):
  self.locked()
  with self.assertRaisesRegex(ValueError,'STATE_CHANGED'):self.store.advance(account_id='A',expected_previous_session='2026-10-02',observations=[self.observation('2026-10-05',78)],baseline_targets={'S':10},expected_reference_version=0,activation_id=H,session_contexts={'2026-10-05':self.context('2026-10-05')})
 def test_changed_evidence_rejected_restart_same_state(self):
  self.locked();self.store=Store(self.path);old=self.store.read_reference('A');c=self.context('2026-10-02');c['holdings']['account_revision']='different'
  with self.assertRaisesRegex(ValueError,'EVIDENCE_CHANGED'):self.store.advance(account_id='A',expected_previous_session='2026-10-02',observations=[self.observation('2026-10-02',79)],baseline_targets={'S':10},expected_reference_version=old['version'],activation_id=H,session_contexts={'2026-10-02':c})
  self.assertEqual(self.store.read_reference('A'),old)
 def test_activation_catchup_old_close_does_not_lock(self):
  self.store=Store(Path(self.tmp.name)/'late.sqlite')
  self.store.activate_reference(account_id='A',activation_id=H,activation_at='2026-10-05T12:00:00Z',activation_session='2026-10-02',account_revision='r0',source_configuration_sha256=H)
  self.advance('2026-10-01',100)
  r=self.advance('2026-10-02',79)
  self.assertEqual(r['reference_state']['locks'],{});self.assertEqual(r['state']['exited'],['S'])
 def test_missing_current_identity_cannot_allow_successor(self):
  s=self.locked()
  with self.assertRaisesRegex(ValueError,'CURRENT_IDENTITY'):execution_targets(state=s,effective_targets={'N':10},actual_shares={'S':0,'N':0},decision_date='2026-10-05')
 def test_two_stale_writers_only_one_commits(self):
  import threading
  self.advance('2026-10-01',100);barrier=threading.Barrier(2);results=[]
  def writer():
   try:
    barrier.wait();Store(self.path).advance(account_id='A',expected_previous_session='2026-10-01',observations=[self.observation('2026-10-02',79)],baseline_targets={'S':10},expected_reference_version=0,activation_id=H,session_contexts={'2026-10-02':self.context('2026-10-02')});results.append('PASS')
   except ValueError:results.append('STALE')
  threads=[threading.Thread(target=writer) for _ in range(2)]
  for t in threads:t.start()
  for t in threads:t.join()
  self.assertEqual(sorted(results),['PASS','STALE']);self.assertEqual(len(self.store.read_reference('A')['locks']),1)
 def test_corrupt_state_rejected(self):
  import sqlite3,json
  self.locked()
  with closing(sqlite3.connect(self.path)) as c:
   r=json.loads(c.execute('SELECT state FROM reentry_state').fetchone()[0]);r['locks']['S']['reference_price']='1';c.execute('UPDATE reentry_state SET state=?',(json.dumps(r),));c.commit()
  with self.assertRaisesRegex(ValueError,'INTEGRITY'):self.store.read_reference('A')
 def test_intraday_activation_allows_same_day_completed_exit(self):
  from data.monthly_peak_exit_store import MonthlyPeakExitStore
  path=Path(self.tmp.name)/'intraday.sqlite';old=MonthlyPeakExitStore(path)
  old.advance(account_id='A',expected_previous_session=None,observations=[self.observation('2026-10-01',100)],baseline_targets={'S':10})
  self.store=Store(path);self.store.activate_reference(account_id='A',activation_id=H,activation_at='2026-10-02T12:00:00Z',activation_session='2026-10-02',account_revision='r0',source_configuration_sha256=H)
  self.assertIn('S',self.advance('2026-10-02',79)['reference_state']['locks'])
 def test_missing_historical_holdings_rolls_back(self):
  self.advance('2026-10-01',100);before=self.store.read('A')
  with self.assertRaisesRegex(ValueError,'HOLDINGS_EVIDENCE'):self.store.advance(account_id='A',expected_previous_session='2026-10-01',observations=[self.observation('2026-10-02',79)],baseline_targets={'S':10},expected_reference_version=0,activation_id=H,session_contexts={'2026-10-02':{'completed_at':'2026-10-02T20:00:00Z'}})
  self.assertEqual(self.store.read('A'),before)
 def test_sql_failure_between_risk_and_reference_write(self):
  import sqlite3
  self.advance('2026-10-01',100);before=self.store.read('A');reference=self.store.read_reference('A')
  with closing(sqlite3.connect(self.path)) as c:
   c.execute("CREATE TRIGGER synthetic_fail BEFORE UPDATE ON reentry_state BEGIN SELECT RAISE(ABORT,'synthetic storage failure'); END");c.commit()
  with self.assertRaises(sqlite3.DatabaseError):self.advance('2026-10-02',79)
  self.assertEqual(self.store.read('A'),before);self.assertEqual(self.store.read_reference('A'),reference)
  with closing(sqlite3.connect(self.path)) as c:c.execute('DROP TRIGGER synthetic_fail');c.commit()
  self.assertIn('S',self.advance('2026-10-02',79)['reference_state']['locks'])
if __name__=='__main__':unittest.main()

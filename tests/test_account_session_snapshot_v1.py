"""Isolated real SQLite ledger tests; no production account IO."""
import os,importlib.util,unittest,sqlite3
from contextlib import closing
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import datetime,timezone,timedelta
from hashlib import sha256
from core.strategy_account_store import StrategyAccountStore
from core.strategy_account_ledger import canonical
path=os.environ.get('ACCOUNT_SESSION_SNAPSHOT_CANDIDATE_PATH')
if path:
 spec=importlib.util.spec_from_file_location('snapshot_candidate',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
else:
 from data import strategy_account_session_snapshot_v1 as m
class SnapshotTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'account.sqlite3';self.clock=datetime(2026,10,28,19,tzinfo=timezone.utc)
  self.store=StrategyAccountStore(self.path,clock=lambda:self.clock);self.state=self.store.initialize('a',operation_id='init')
  self.boundary={'schema':'ARCHIVED_ACCOUNT_DECISION_BOUNDARY_V1','account_id':'a','session_date':'2026-10-28','session_close_at':'2026-10-28T20:00:00+00:00','decision_at':'2026-10-28T20:05:00+00:00'}
 def tearDown(self):self.temp.cleanup()
 def append(self,kind,**kwargs):self.state,_=self.store.append(dict(kind=kind,event_id=str(len(self.state['events'])),**kwargs),expected_revision=self.state['revision'])
 def snapshot(self,**kwargs):
  raw=canonical(self.boundary);self.clock=max(self.clock,datetime(2026,10,29,tzinfo=timezone.utc))
  return m.account_session_snapshot(self.store,account_id='a',session_date='2026-10-28',expected_latest_revision=kwargs.pop('expected_latest_revision',self.state['revision']),decision_evidence=raw,decision_evidence_sha256=sha256(raw).hexdigest(),security_ids=['s'],**kwargs)
 def test_cash_and_open_are_not_holdings_and_read_does_not_write(self):
  self.append('CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')
  self.append('ORDER_OPEN',order_id='o',security_id='s',side='BUY',quantity=2,limit_price='10',fee_per_share='0')
  original=self.path.read_bytes();result=self.snapshot();self.assertEqual(result['shares'],{'s':0});self.assertFalse(result['units_certified']);self.assertEqual(self.path.read_bytes(),original)
 def test_cutoff_prefix_and_late_fill_wait(self):
  self.append('CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')
  self.append('DIRECT_FILL',security_id='s',side='BUY',quantity=2,price='10',fees='0',executed_at='2026-10-28T18:59:00+00:00')
  self.clock=datetime(2026,10,28,21,tzinfo=timezone.utc);self.append('CASH_CONFIRM',amount='500',cash_basis='TOTAL_UNINVESTED')
  result=self.snapshot();self.assertEqual(result['shares']['s'],2);self.assertEqual(result['last_ordinal'],2);self.assertNotEqual(result['account_revision'],result['latest_revision'])
  self.append('DIRECT_FILL',security_id='s',side='SELL',quantity=1,price='10',fees='0',executed_at='2026-10-28T20:01:00+00:00')
  result=self.snapshot();self.assertEqual(result['reason'],'WAIT_LATE_RECORDED_FILL_RECONCILIATION');self.assertNotIn('shares',result)
 def test_later_cash_does_not_change_historical_evidence(self):
  self.append('CASH_CONFIRM',amount='10',cash_basis='TOTAL_UNINVESTED')
  before=self.snapshot()
  self.append('CASH_CONFIRM',amount='20',cash_basis='TOTAL_UNINVESTED')
  after=self.snapshot()
  self.assertNotEqual(before['latest_revision'],after['latest_revision'])
  for key in ['account_revision','event_boundary_sha256','evidence_sha256','shares']:
   self.assertEqual(before[key],after[key])
 def test_missing_decision_initialization_and_revision(self):
  result=m.account_session_snapshot(self.store,account_id='a',session_date='2026-10-28',expected_latest_revision=self.state['revision']);self.assertEqual(result['reason'],'WAIT_DECISION_BOUNDARY_UNPROVEN')
  self.assertEqual(self.snapshot()['reason'],'WAIT_ACCOUNT_PREFIX_UNPROVEN')
  self.clock=datetime(2026,10,28,19,tzinfo=timezone.utc);self.append('CASH_CONFIRM',amount='1',cash_basis='TOTAL_UNINVESTED')
  with self.assertRaisesRegex(ValueError,'STALE_REVISION'):self.snapshot(expected_latest_revision='old')
 def test_bad_clock_boundaries_and_digest_rejected(self):
  self.boundary['decision_at']='2026-10-28T20:05:00'
  with self.assertRaisesRegex(ValueError,'AWARE'):self.snapshot()
  self.boundary['decision_at']='2026-10-28T19:05:00+00:00'
  with self.assertRaisesRegex(ValueError,'BOUNDARY_ORDER'):self.snapshot()
  with self.assertRaisesRegex(ValueError,'DECISION_HASH'):m.account_session_snapshot(self.store,account_id='a',session_date='2026-10-28',expected_latest_revision=self.state['revision'],decision_evidence=b'{}',decision_evidence_sha256='0'*64)
 def test_real_store_full_history_rejects_receipt_time_reversal(self):
  self.append('CASH_CONFIRM',amount='10',cash_basis='TOTAL_UNINVESTED');self.clock+=timedelta(seconds=1);self.append('CASH_CONFIRM',amount='20',cash_basis='TOTAL_UNINVESTED')
  with closing(sqlite3.connect(self.path,isolation_level=None)) as c:c.execute("UPDATE strategy_events SET received_at='2026-10-28T18:00:00+00:00' WHERE ordinal=2")
  with self.assertRaisesRegex(ValueError,'RECEIPT_TIME_INVALID'):self.snapshot()
if __name__=='__main__':unittest.main()

import unittest,tempfile,sqlite3
from pathlib import Path
from contextlib import contextmanager,closing
from core.roa_capital_commitments import CapitalCommitmentStore,plan_digest

class CommitmentTests(unittest.TestCase):
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
  self.plan=dict(account_id='test',funding_ids=['cash:item'],account_revision='a',decision_date='2026-10-30',targets={'A':12},classification_digest='c')
  @contextmanager
  def operation():yield self.plan
  self.store=CapitalCommitmentStore(path=Path(self.directory.name)/'capital.sqlite',account_id='test',operation=operation);self.store.initialize()
  self.empty=self.store.read()['revision']
 def save(self,revision=None):return self.store.commit(expected_revision=revision or self.empty,expected_plan_digest=plan_digest(self.plan))
 def test_restart_and_retry_do_not_duplicate(self):
  first=self.save();second=self.save();self.assertFalse(first['already_committed']);self.assertTrue(second['already_committed']);self.assertEqual(first['plan_id'],second['plan_id'])
  reopened=CapitalCommitmentStore(path=self.store.path,account_id='test',operation=self.store.operation)
  self.assertEqual(len(reopened.read()['plans']),1)
 def test_changed_account_rejects_preview(self):
  old=plan_digest(self.plan);self.plan['account_revision']='b'
  with self.assertRaisesRegex(ValueError,'STALE_CAPITAL_PLAN'):self.store.commit(expected_revision=self.empty,expected_plan_digest=old)
  self.assertEqual(self.store.read()['plans'],{})
 def test_same_capital_cannot_fund_changed_target(self):
  self.save();revision=self.store.read()['revision'];self.plan['targets']['A']=13
  with self.assertRaisesRegex(ValueError,'CAPITAL_SOURCE_ALREADY_COMMITTED'):self.save(revision)
  self.assertEqual(len(self.store.read()['plans']),1)
 def test_stale_revision_and_duplicate_source_reject(self):
  self.plan['funding_ids']=['same','same']
  with self.assertRaisesRegex(ValueError,'CAPITAL_SOURCE_IDS_REQUIRED'):self.save()
  self.plan['funding_ids']=['new']
  with self.assertRaisesRegex(ValueError,'STALE_CAPITAL_COMMITMENTS'):self.save('wrong')
 def test_other_instance_cannot_commit_stale_snapshot(self):
  other_plan=dict(self.plan,funding_ids=['second-source'])
  @contextmanager
  def other_operation():yield other_plan
  other=CapitalCommitmentStore(path=self.store.path,account_id='test',operation=other_operation)
  stale=other.read()['revision'];self.save()
  with self.assertRaisesRegex(ValueError,'STALE_CAPITAL_COMMITMENTS'):
   other.commit(expected_revision=stale,expected_plan_digest=plan_digest(other_plan))
  self.assertEqual(len(other.read()['plans']),1)
 def test_wrong_account_cannot_read_even_empty_store(self):
  other=CapitalCommitmentStore(path=self.store.path,account_id='different',operation=self.store.operation)
  with self.assertRaisesRegex(ValueError,'CAPITAL_ACCOUNT_MISMATCH'):other.read()
 def test_tampered_index_detected(self):
  self.save()
  with closing(sqlite3.connect(self.store.path)) as connection:
   connection.execute('DELETE FROM sources');connection.commit()
  with self.assertRaisesRegex(ValueError,'CAPITAL_SOURCE_INDEX_INVALID'):self.store.read()
if __name__=='__main__':unittest.main()

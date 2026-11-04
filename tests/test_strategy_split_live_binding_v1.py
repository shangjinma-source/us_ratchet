from contextlib import closing
from hashlib import sha256
import sqlite3
import unittest
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_split_bundle_v1 import prepare_split_bundle
from data.strategy_split_live_binding_v1 import bound_split_sources
import test_strategy_split_bundle_v1 as fixtures

class LiveBindingTests(unittest.TestCase):
    def setUp(self):
        self.base=fixtures.SplitBundleTests();self.base.setUp();self.addCleanup(self.base.doCleanups)
        b=self.base;root=b.source.path.parent
        self.paths=dict(account=b.source.path,target=root/'target.sqlite3',risk=root/'risk.sqlite3')
        target=b.arguments['target']
        StrategyMonthlyTargetStore(self.paths['target']).append(target['payload'])
        rows=b.arguments['observations'][:1]
        from core.saved_monthly_frontier_proposal import build_frontier_proposal
        MonthlyPeakExitStore(self.paths['risk']).advance(account_id='synthetic-account',expected_previous_session=None,
            observations=rows,baseline_targets=build_frontier_proposal(target=target)['payload']['proposed_target_quantities'],target_month=target['payload']['target_month'])
        prepare_split_bundle(**b.arguments)
        self.kwargs=dict(paths=self.paths,bundle_directory=b.directory,
            expected_manifest_sha256=sha256((b.directory/'complete.json').read_bytes()).hexdigest())
    def test_all_bindings_checked_while_writes_blocked(self):
        with bound_split_sources(**self.kwargs) as result:
            self.assertTrue(result['source_consistency_verified']);self.assertFalse(result['production_activated'])
            for path in self.paths.values():
                with closing(sqlite3.connect(path,timeout=0)) as connection:
                    with self.assertRaises(sqlite3.OperationalError):connection.execute('BEGIN IMMEDIATE')
    def test_cash_update_invalidates_preparation(self):
        state=self.base.source.read()
        self.base.source.append(dict(kind='CASH_CONFIRM',event_id='new-cash',amount='100',cash_basis='TOTAL_UNINVESTED'),expected_revision=state['revision'])
        with self.assertRaisesRegex(ValueError,'SPLIT_LIVE_ACCOUNT_CHANGED'):
            with bound_split_sources(**self.kwargs):self.fail()
    def test_wrong_manifest_digest_rejected_and_locks_released(self):
        with self.assertRaisesRegex(ValueError,'MANIFEST_CHANGED'):
            with bound_split_sources(**dict(self.kwargs,expected_manifest_sha256='0'*64)):self.fail()
        with closing(sqlite3.connect(self.paths['account'],timeout=0)) as connection:
            connection.execute('BEGIN IMMEDIATE');connection.rollback()

    def test_new_target_invalidates_preparation(self):
        from copy import deepcopy
        target=self.base.arguments['target']
        payload=deepcopy(target['payload'])
        payload['previous_target_id']=target['target_id']
        payload['request']['event_id']='next-target'
        StrategyMonthlyTargetStore(self.paths['target']).append(payload)
        with self.assertRaisesRegex(ValueError,'SPLIT_LIVE_TARGET_CHANGED'):
            with bound_split_sources(**self.kwargs):self.fail()
    def test_advanced_risk_invalidates_preparation(self):
        from copy import deepcopy
        from core.saved_monthly_frontier_proposal import build_frontier_proposal
        row=deepcopy(self.base.arguments['observations'][0])
        previous=row['session_date'];row['session_date']='2026-10-21';row['closes']['A']='101'
        MonthlyPeakExitStore(self.paths['risk']).advance(account_id='synthetic-account',expected_previous_session=previous,
            observations=[row],baseline_targets=build_frontier_proposal(target=self.base.arguments['target'])['payload']['proposed_target_quantities'],target_month='2026-10')
        with self.assertRaisesRegex(ValueError,'SPLIT_LIVE_RISK_CHANGED'):
            with bound_split_sources(**self.kwargs):self.fail()

if __name__=='__main__':unittest.main()

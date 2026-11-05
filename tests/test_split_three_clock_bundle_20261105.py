"""Three-clock bundle migrates a copy and verifies both stored databases."""
from hashlib import sha256
import json
import unittest
import sqlite3
from contextlib import closing
from core.strategy_account_ledger import canonical
from docs.candidates.split_three_clock_bundle_20261105 import prepare_split_bundle, verify_split_bundle, bound_split_sources
import test_strategy_split_bundle_v1 as fixtures


class Tests(unittest.TestCase):
    def setUp(self):
        self.base=fixtures.SplitBundleTests();self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.args=self.base.arguments
        action=self.args['action'];action['effective_at']='2026-10-28T22:00:00Z'
        calendar=dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=[
            dict(date=d,open=d+'T13:30:00Z',close=d+'T20:00:00Z') for d in ['2026-10-20','2026-10-28','2026-10-29']])
        proof=dict(schema='SPLIT_THREE_CLOCK_EXECUTION_CONTENT_V2',action_id=action['action_id'],
            recorded_action_sha256=sha256(canonical(action)).hexdigest(),distribution_at=action['effective_at'],
            quote_unit_effective_at='2026-10-29T13:30:00Z',broker_tradable_at='2026-10-29T13:35:00Z',
            tradable_evidence_received_at='2026-10-29T13:36:00Z',
            tradable_evidence_semantics='OBSERVED_ACTUALLY_TRADABLE_NOT_FUTURE_NOTICE',
            clock_source_references={k:['s'] for k in ['distribution_at','quote_unit_effective_at',
                'broker_tradable_at','tradable_evidence_received_at']})
        self.args['timing']=dict(review=proof,calendar=calendar,calendar_sha256=sha256(canonical(calendar)).hexdigest(),
            source_hex={'s':b'synthetic'.hex()},source_hashes={'s':sha256(b'synthetic').hexdigest()})

    def test_complete_bundle_replays_and_preserves_source(self):
        before=self.base.source.path.read_bytes()
        result=prepare_split_bundle(**self.args)
        self.assertEqual(verify_split_bundle(self.base.directory),result)
        self.assertEqual(self.base.source.path.read_bytes(),before)
        self.assertFalse(result['production_activated'])
        self.assertEqual(result['schema'],'SPLIT_THREE_CLOCK_PREPARATION_BUNDLE_V1')

    def test_rehashed_timing_cannot_reuse_previous_transition(self):
        prepare_split_bundle(**self.args)
        path=self.base.directory/'inputs.json';inputs=json.loads(path.read_bytes())
        inputs['timing']['review']['broker_tradable_at']='2026-10-29T13:34:00Z'
        path.write_bytes(canonical(inputs))
        manifest_path=self.base.directory/'complete.json';manifest=json.loads(manifest_path.read_bytes())
        manifest['files']['inputs.json']=sha256(path.read_bytes()).hexdigest()
        manifest_path.write_bytes(canonical(manifest))
        with self.assertRaisesRegex(ValueError,'SPLIT_BUNDLE_TRANSITION_BINDING'):
            verify_split_bundle(self.base.directory)

    def test_future_actual_evidence_does_not_publish_bundle(self):
        self.args['timing']['review']['tradable_evidence_received_at']='2026-10-29T16:00:00Z'
        with self.assertRaisesRegex(ValueError,'TIMING_NOT_EXECUTABLE_YET'):
            prepare_split_bundle(**self.args)
        self.assertFalse(self.base.directory.exists())

    def test_source_locks_and_cash_change_prevent_stale_switch(self):
        from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
        from core.saved_monthly_frontier_proposal import build_frontier_proposal
        from data.monthly_peak_exit_store import MonthlyPeakExitStore
        root=self.base.source.path.parent
        paths=dict(account=self.base.source.path,target=root/'target.sqlite3',risk=root/'risk.sqlite3')
        target=self.args['target']
        StrategyMonthlyTargetStore(paths['target']).append(target['payload'])
        MonthlyPeakExitStore(paths['risk']).advance(account_id='synthetic-account',
            expected_previous_session=None,observations=self.args['observations'][:1],
            baseline_targets=build_frontier_proposal(target=target)['payload']['proposed_target_quantities'],
            target_month=target['payload']['target_month'])
        prepare_split_bundle(**self.args)
        arguments=dict(paths=paths,bundle_directory=self.base.directory,
            expected_manifest_sha256=sha256((self.base.directory/'complete.json').read_bytes()).hexdigest())
        with bound_split_sources(**arguments) as bound:
            self.assertTrue(bound['source_consistency_verified'])
            self.assertFalse(bound['production_activated'])
            for path in paths.values():
                with closing(sqlite3.connect(path,timeout=0)) as connection:
                    with self.assertRaises(sqlite3.OperationalError):
                        connection.execute('BEGIN IMMEDIATE')
        # A real journal append after preparation must invalidate that generation.
        state=self.base.source.read()
        self.base.source.append(dict(event_id='later-cash',kind='CASH_CONFIRM',amount='7000',
            cash_basis='TOTAL_UNINVESTED'),expected_revision=state['revision'])
        with self.assertRaisesRegex(ValueError,'SPLIT_LIVE_ACCOUNT_CHANGED'):
            with bound_split_sources(**arguments): self.fail('stale bundle accepted')
        with closing(sqlite3.connect(paths['account'],timeout=0)) as connection:
            connection.execute('BEGIN IMMEDIATE');connection.rollback()


if __name__=='__main__':unittest.main()

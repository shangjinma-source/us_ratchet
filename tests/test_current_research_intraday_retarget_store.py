from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from pathlib import Path
import sqlite3
import tempfile
from threading import Event
import unittest

import test_current_research_intraday_retarget_evidence as evidence_tests
from data.current_research_intraday_buy_plan import _time
from data.current_research_intraday_paper_ledger import _initial
from data.current_research_intraday_paper_store import IntradayPaperStore
from data.current_research_intraday_retarget_evidence import accept_retarget_with_execution_evidence, review_source_verified_retarget


class RetargetStoreTests(unittest.TestCase):
    def fixture(self, root):
        source = Path(root) / 'sources'
        source.mkdir()
        before, proposal, arguments = evidence_tests.FrozenRetargetTests().fixture(str(source))
        initial = _initial(before['acceptance'])
        store = IntradayPaperStore(Path(root) / 'store')
        store.accept(before['account_id'], initial['acceptance']['proposal']['proposal_id'], 'initial', lambda: initial)
        for event in before['events']:
            store.record_event(before['account_id'], event, now=_time(event['recorded_at']))
        def factory(state):
            return accept_retarget_with_execution_evidence(state, proposal, **arguments)
        return store, before, proposal, arguments, factory

    def test_persist_fill_restart_retry_and_original_identity(self):
        with tempfile.TemporaryDirectory() as root:
            store, before, proposal, args, factory = self.fixture(root)
            account = before['account_id']
            call = (account, proposal['proposal_id'], args['operation_id'], before['revision'])
            accepted = store.accept_retarget(*call, factory)
            sell = next(order for order in accepted['orders'].values() if order['side'] == 'SELL')
            event = dict(event_id='sell', kind='FILL', expected_revision=accepted['revision'],
                order_id=sell['order_id'], quantity=2, price='1500', fees='1', executed_at=args['now'].isoformat())
            after = store.record_event(account, event, now=lambda: args['now'])
            self.assertEqual(after['cash'], '20199')
            self.assertEqual(after['acceptance_id'], before['acceptance_id'])
            restored = IntradayPaperStore(store.path.parent)
            self.assertEqual(restored.read(account), after)
            envelope = restored.read_retarget_envelope(account)
            self.assertEqual(review_source_verified_retarget(envelope)['ledger'], after)
            self.assertEqual(restored.accept_retarget(*call, lambda _: self.fail('retry factory')), after)
            self.assertEqual(restored.record_event(account, event, now=lambda: self.fail('retry clock')), after)
            self.assertEqual(restored.accept(account, before['acceptance']['proposal']['proposal_id'], 'initial', lambda: self.fail('initial factory')), after)

    def test_sql_failure_rolls_back_envelope_and_operation(self):
        with tempfile.TemporaryDirectory() as root:
            store, before, proposal, args, factory = self.fixture(root)
            with closing(sqlite3.connect(store.path)) as db:
                db.execute("CREATE TRIGGER reject_retarget BEFORE INSERT ON intraday_retargets BEGIN SELECT RAISE(ABORT,'test rollback'); END")
                db.commit()
            with self.assertRaises(sqlite3.Error):
                store.accept_retarget(before['account_id'], proposal['proposal_id'], args['operation_id'], before['revision'], factory)
            self.assertEqual(store.read(before['account_id']), before)
            with closing(sqlite3.connect(store.path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM intraday_retargets').fetchone()[0], 0)

    def test_stale_conflict_and_invalid_fill_leave_state_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            store, before, proposal, args, factory = self.fixture(root)
            for operation, revision in [('initial', before['revision']), (args['operation_id'], 'old')]:
                with self.assertRaises(ValueError):
                    store.accept_retarget(before['account_id'], proposal['proposal_id'], operation, revision, lambda _: self.fail('invalid factory'))
            state = store.accept_retarget(before['account_id'], proposal['proposal_id'], args['operation_id'], before['revision'], factory)
            sell = next(order for order in state['orders'].values() if order['side'] == 'SELL')
            event = dict(event_id='bad-sell', kind='FILL', expected_revision=state['revision'], order_id=sell['order_id'],
                quantity=3, price='1500', fees='0', executed_at=args['now'].isoformat())
            with self.assertRaises(ValueError):
                store.record_event(before['account_id'], event, now=args['now'])
            self.assertEqual(store.read(before['account_id']), state)
            with self.assertRaises(ValueError):
                store.accept_retarget(before['account_id'], 'wrong', args['operation_id'], before['revision'], factory)

    def test_concurrent_identical_acceptance_runs_factory_once(self):
        with tempfile.TemporaryDirectory() as root:
            store, before, proposal, args, factory = self.fixture(root)
            entered, release, calls = Event(), Event(), []
            def guarded(state):
                calls.append(1)
                entered.set()
                self.assertTrue(release.wait(5))
                return factory(state)
            call = (before['account_id'], proposal['proposal_id'], args['operation_id'], before['revision'], guarded)
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(store.accept_retarget, *call)
                self.assertTrue(entered.wait(5))
                second = pool.submit(store.accept_retarget, *call)
                release.set()
                self.assertEqual(first.result(10), second.result(10))
            self.assertEqual(calls, [1])


if __name__ == '__main__':
    unittest.main()

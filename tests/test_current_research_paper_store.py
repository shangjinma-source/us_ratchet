from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from tempfile import TemporaryDirectory
import unittest

from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_paper_store import ResearchPaperStore


def plan_fixture():
    return build_current_research_limit_plan(
        research_snapshot={'research_id': 'a' * 24, 'as_of': '2026-10-13',
                           'stocks': [{'security_id': 'A', 'ticker': 'AAA'}],
                           'source_hashes': {'quote': 'b' * 64}},
        quotes=[{'security_id': 'A', 'price': '10.00', 'as_of': '2026-10-13',
                 'price_kind': 'DECLARED_DECIMAL_REFERENCE', 'price_basis': 'CONDITIONAL',
                 'source_references': ['quote']}],
        available_cash='100', shares={}, account_revision='initial',
        decision_date='2026-10-13', active_date='2026-10-14',
        calendar=['2026-10-13', '2026-10-14'], strategy_version='paper-v1',
        target_quantities={'A': 9})


def fill_fixture(state, identifier='fill-1'):
    return {'event_id': identifier, 'mode': 'PAPER_MANUAL_FILL',
            'plan_id': state['plan']['plan_id'],
            'order_id': state['plan']['orders'][0]['order_id'], 'qty': 1,
            'price': '10', 'fees': '1', 'session': '2026-10-14',
            'expected_revision': state['revision']}


def close_fixture(state, event_type='CANCEL'):
    event = {'event_id': 'close-1', 'mode': 'PAPER_MANUAL_FILL',
             'plan_id': state['plan']['plan_id'],
             'order_id': state['plan']['orders'][0]['order_id'],
             'event_type': event_type, 'expected_revision': state['revision']}
    if event_type == 'EXPIRE':
        event['completed_session'] = state['plan']['active_date']
    return event


def next_plan_fixture(state):
    causal = state['plan']['causal_inputs']
    quotes = [dict(deepcopy(quote), security_id=identifier, as_of='2026-10-14')
              for identifier, quote in causal['quotes'].items()]
    return build_current_research_limit_plan(
        research_snapshot=causal['research_snapshot'], quotes=quotes,
        available_cash=state['cash'], shares=state['shares'],
        account_revision=state['revision'], decision_date='2026-10-14',
        active_date='2026-10-15', calendar=['2026-10-14', '2026-10-15'],
        strategy_version=causal['strategy_version'],
        target_quantities=causal['target_quantities'])


class PaperStoreTests(unittest.TestCase):
    def test_migration_retry_validates_current_state_without_reset(self):
        with TemporaryDirectory() as directory:
            store = ResearchPaperStore(directory)
            initial = store.create('isolated', plan_fixture())
            self.assertEqual(store.migrate('isolated', initial['revision']), initial)
            filled = store.record_fill('isolated', fill_fixture(initial))
            with self.assertRaisesRegex(ValueError, 'STALE_ACCOUNT_REVISION'):
                store.migrate('isolated', initial['revision'])
            self.assertEqual(store.read('isolated'), filled)

    def test_partial_close_transition_restart_and_old_retry(self):
        with TemporaryDirectory() as directory:
            store = ResearchPaperStore(directory)
            initial = store.create('isolated', plan_fixture())
            original_fill = fill_fixture(initial)
            filled = store.record_fill('isolated', original_fill)
            closed = store.record_order_event('isolated', close_fixture(filled, 'EXPIRE'))
            self.assertEqual(closed['cash'], filled['cash'])
            self.assertEqual(closed['shares'], filled['shares'])
            self.assertEqual(closed['reserved_cash'], '0')
            next_plan = next_plan_fixture(closed)
            activation = {'event_id': 'activate-1', 'mode': 'PAPER_MANUAL_FILL',
                          'event_type': 'ACTIVATE_PLAN', 'plan_id': next_plan['plan_id'],
                          'expected_revision': closed['revision']}
            continued = store.activate_plan('isolated', next_plan, activation)
            self.assertEqual(continued['cash'], '89')
            self.assertEqual(continued['shares'], {'A': 1})
            self.assertEqual(continued['plan']['orders'][0]['quantity'], 8)
            restarted = ResearchPaperStore(directory)
            self.assertEqual(restarted.read('isolated'), continued)
            self.assertEqual(restarted.record_fill('isolated', original_fill), continued)
            self.assertEqual(restarted.activate_plan('isolated', next_plan, activation), continued)

    def test_close_and_fill_same_revision_cannot_both_commit(self):
        with TemporaryDirectory() as directory:
            first, second = ResearchPaperStore(directory), ResearchPaperStore(directory)
            state = first.create('isolated', plan_fixture())
            def submit(kind):
                try:
                    if kind == 'close':
                        first.record_order_event('isolated', close_fixture(state))
                    else:
                        second.record_fill('isolated', fill_fixture(state))
                    return 'accepted'
                except ValueError:
                    return 'rejected'
            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(submit, ['close', 'fill']))
            self.assertCountEqual(statuses, ['accepted', 'rejected'])

    def test_restart_retry_and_recreate_preserve_fills(self):
        with TemporaryDirectory() as directory:
            store = ResearchPaperStore(directory)
            initial = store.create('isolated', plan_fixture())
            event = fill_fixture(initial)
            filled = store.record_fill('isolated', event)
            restarted = ResearchPaperStore(directory)
            self.assertEqual(restarted.read('isolated'), filled)
            self.assertEqual(restarted.record_fill('isolated', event), filled)
            self.assertEqual(restarted.create('isolated', plan_fixture()), filled)
            self.assertEqual(filled['cash'], '89')
            self.assertEqual(filled['shares']['A'], 1)

    def test_rejected_fill_rolls_back(self):
        with TemporaryDirectory() as directory:
            store = ResearchPaperStore(directory)
            initial = store.create('isolated', plan_fixture())
            wrong = fill_fixture(initial)
            wrong['price'] = '11'
            with self.assertRaises(ValueError):
                store.record_fill('isolated', wrong)
            self.assertEqual(store.read('isolated'), initial)
            store.record_fill('isolated', fill_fixture(initial))
            changed = deepcopy(plan_fixture())
            changed['orders'][0]['quantity'] = 999
            with self.assertRaises(ValueError):
                store.create('isolated', changed)

    def test_two_connections_cannot_both_accept_stale_revision(self):
        with TemporaryDirectory() as directory:
            first, second = ResearchPaperStore(directory), ResearchPaperStore(directory)
            state = first.create('isolated', plan_fixture())
            def submit(pair):
                store, event = pair
                try:
                    store.record_fill('isolated', event)
                    return 'accepted'
                except ValueError:
                    return 'rejected'
            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(submit, [
                    (first, fill_fixture(state, 'first')),
                    (second, fill_fixture(state, 'second'))]))
            self.assertCountEqual(statuses, ['accepted', 'rejected'])
            self.assertEqual(first.read('isolated')['shares']['A'], 1)


if __name__ == '__main__':
    unittest.main()

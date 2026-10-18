import unittest
from copy import deepcopy

import pandas as pd

from backtest.ndx_dynamic_frozen_execution_research import simulate_dynamic_frozen_execution_research as simulate


class DynamicFrozenTests(unittest.TestCase):
    def rename_event(self, session):
        return dict(security_id='A', issuer_id='issuer:A', session=session,
            from_ticker='A', to_ticker='X', source_url='https://example.com/rename',
            evidence_sha256='a' * 64)

    def fixture(self, compositions=('AB', 'BCD')):
        dates = pd.bdate_range('2024-01-02', periods=6)
        prices = pd.DataFrame(10., index=dates, columns=list('ABCDX'))
        schedule = []
        chains = {}
        for index, composition in enumerate(compositions):
            decision = dates[index * 2].date().isoformat()
            targets = {key: dict(ticker=key, issuer_id='issuer:' + key, target_weight=1 / len(composition))
                       for key in composition}
            schedule.append(dict(decision_date=decision,
                execution_date=dates[index * 2 + 1].date().isoformat(), targets=targets))
            chains[decision] = {key: 'chain:' + key for key in composition}
        return dict(closes=prices, opens=prices.copy(), schedule=schedule,
            risk_chains_by_decision=chains, corporate_actions=[], initial_cash_usd=1000.,
            minimum_cash_buffer_usd=100., valuation_end_date=dates[-1].date().isoformat(),
            transaction_cost_bps=0., max_single_weight=1., min_single_weight=0.,
            top_weight_cap=1., minimum_effective_n_ratio=0., risk_chain_top1_cap=1.)

    def test_variable_k_exits_entries_and_accounting(self):
        result = simulate(**self.fixture())
        self.assertEqual(result['summary']['k_path'], [2, 3])
        self.assertEqual(set(result['daily'][-1]['shares']), set('BCD'))
        self.assertTrue(any(row['security_id'] == 'A' and row['share_delta'] < 0 for row in result['trades']))
        self.assertEqual(result['summary']['terminal_value_usd'], 1000.)
        self.assertEqual(result['summary']['all_cash_session_count'], 1)
        self.assertFalse(result['promotion_allowed'])

    def test_future_open_never_changes_frozen_first_decision(self):
        args = self.fixture(('AB',))
        first = simulate(**args)
        args['opens'].iloc[1] = 1000.
        changed = simulate(**args)
        self.assertEqual(first['decisions'], changed['decisions'])
        self.assertEqual(changed['executions'][0]['status'], 'REJECTED')
        self.assertIn('CASH_BUFFER', changed['executions'][0]['failure_reasons'])
        self.assertEqual(changed['trades'], [])
        self.assertEqual(len(changed['executions']), 1)

    def test_alias_fails_closed_even_with_declared_evidence(self):
        args = self.fixture(('AB', 'AB'))
        args['schedule'][1]['targets']['A']['ticker'] = 'X'
        args['identity_events'] = [self.rename_event(args['schedule'][1]['decision_date'])]
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            simulate(**args)

    def test_rename_requires_evidence_and_valid_identity(self):
        args = self.fixture(('AB', 'AB'))
        args['schedule'][1]['targets']['A']['ticker'] = 'X'
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            simulate(**args)
        event = self.rename_event(args['schedule'][1]['decision_date'])
        for patch in ({'evidence_sha256': ''}, {'issuer_id': 'wrong'}, {'from_ticker': 'WRONG'},
                      {'source_url': 'https://'}, {'session': args['schedule'][0]['decision_date']}):
            args['identity_events'] = [dict(event, **patch)]
            with self.assertRaises(ValueError):
                simulate(**args)

    def test_rename_nondecision_before_open_no_future_backfill(self):
        args = self.fixture(('AB',))
        session = args['schedule'][0]['execution_date']
        args['identity_events'] = [self.rename_event(session)]
        args['closes'].loc[session:, 'A'] = float('nan')
        args['opens'].loc[session:, 'A'] = float('nan')
        args['closes'].loc[:args['schedule'][0]['decision_date'], 'X'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            simulate(**args)

    def test_false_rename_cannot_create_8100_dollars(self):
        args = self.fixture(('A', 'A'))
        args['schedule'][1]['targets']['A']['ticker'] = 'X'
        args['closes']['X'] = 100.
        args['opens']['X'] = 100.
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            simulate(**args)

    def test_numpy_boolean_price_rejected(self):
        args = self.fixture(('A',))
        args['closes']['A'] = True
        with self.assertRaisesRegex(ValueError, 'Boolean price'):
            simulate(**args)
        args = self.fixture(('A',))
        args['opens']['A'] = True
        with self.assertRaisesRegex(ValueError, 'Boolean price'):
            simulate(**args)

    def test_last_known_exited_chain_not_future_backfilled(self):
        args = self.fixture()
        result = simulate(**args)
        second = result['decisions'][1]
        self.assertEqual(second['risk_chain_observation_dates']['A'], args['schedule'][0]['decision_date'])
        self.assertEqual(second['risk_chains']['A'], 'chain:A')
        args['risk_chains_by_decision'][args['schedule'][0]['decision_date']].pop('A')
        with self.assertRaises(ValueError):
            simulate(**args)

    def test_split_cancels_pending_exact_entitlement(self):
        args = self.fixture(('A', 'A'))
        session = args['schedule'][1]['execution_date']
        args['corporate_actions'] = [dict(security_id='A', session=session, new_shares=2,
            old_shares=1, source_url='https://example.com/split', evidence_sha256='a' * 64)]
        args['closes'].loc[session:, 'A'] = 5.
        args['opens'].loc[session:, 'A'] = 5.
        result = simulate(**args)
        self.assertEqual(result['executions'][-1]['status'], 'CANCELLED_SPLIT')
        self.assertEqual(result['daily'][-1]['shares']['A'], 180)
        self.assertEqual(result['summary']['terminal_value_usd'], 1000.)
        args['corporate_actions'][0].update(new_shares=1, old_shares=7)
        with self.assertRaisesRegex(ValueError, 'FRACTIONAL'):
            simulate(**args)

    def test_bad_clock_identity_boolean_and_input_nonmutation(self):
        args = self.fixture()
        original = deepcopy(args['schedule'])
        simulate(**args)
        self.assertEqual(original, args['schedule'])
        args['schedule'][0]['targets']['A']['target_weight'] = True
        with self.assertRaises(ValueError):
            simulate(**args)
        args = self.fixture()
        args['schedule'][0]['execution_date'] = args['schedule'][1]['execution_date']
        with self.assertRaises(ValueError):
            simulate(**args)

    def test_decision_constraints_not_relaxed(self):
        args = self.fixture(('AB',))
        args['max_single_weight'] = .45
        result = simulate(**args)
        self.assertEqual(result['decisions'][0]['status'], 'NO_PLAN')
        self.assertEqual(result['trades'], [])

    def test_same_issuer_security_replacement_is_economic_trade(self):
        args = self.fixture(('A', 'B'))
        args['schedule'][1]['targets']['B']['issuer_id'] = 'issuer:A'
        result = simulate(**args)
        later = [row for row in result['trades'] if row['session'] == args['schedule'][1]['execution_date']]
        self.assertEqual([(row['security_id'], row['share_delta']) for row in later], [('A', -90), ('B', 90)])


if __name__ == '__main__':
    unittest.main()

import unittest
from backtest.return_priority_frozen_nominal_outcome import frozen_nominal_outcome


def inputs():
    return dict(target_weights={'x': '1'}, metadata={'x': {'issuer_id': 'issuer:x'}},
                entered_cash='100', session_dates=['2024-01-01', '2024-01-02', '2024-01-03'],
                decision_date='2024-01-01', end_date='2024-01-03',
                nominal_prices={'x': {'2024-01-01': {'close': '1'},
                                      '2024-01-02': {'open': '20', 'close': '20'},
                                      '2024-01-03': {'close': '20'}}})


class FrozenOutcomeTests(unittest.TestCase):
    def test_terminated_before_entry_even_when_open_exists(self):
        data = inputs()
        data['cash_merger_events'] = [dict(date='2024-01-02', security_id='x',
                                          share_cash='22', source_references=['official'])]
        result = frozen_nominal_outcome(**data)
        self.assertEqual(result['blocked_reason']['reason'], 'TERMINATED_BEFORE_ENTRY')
        self.assertEqual(result['initial_shares'], {})
        self.assertEqual(result['cash'], '100')
        self.assertEqual(result['state_date'], '2024-01-02')
        self.assertEqual(result['last_valued_date'], '2024-01-01')

    def test_post_split_missing_close_state_date_is_explicit(self):
        data = inputs()
        del data['nominal_prices']['x']['2024-01-03']
        data['split_events'] = [dict(date='2024-01-03', security_id='x', new_shares=10,
                                     old_shares=1, source_references=['official'])]
        result = frozen_nominal_outcome(**data)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['state_date'], '2024-01-03')
        self.assertEqual(result['last_valued_date'], '2024-01-02')
        self.assertEqual(result['final_shares'], {'x': 50})

    def test_next_open_and_no_future_read(self):
        data = inputs()
        data['nominal_prices']['x']['9999-01-01'] = object()
        data['split_events'] = [{'date': '9999-01-01', 'new_shares': object()}]
        outcome = frozen_nominal_outcome(**data)
        self.assertEqual(outcome['initial_shares'], {'x': 5})
        self.assertEqual(outcome['return'], '0')
        self.assertEqual(outcome['cash'], '0')

    def test_split_preserves_wealth(self):
        data = inputs()
        data['nominal_prices']['x']['2024-01-03']['close'] = '2'
        data['split_events'] = [dict(date='2024-01-03', security_id='x', new_shares=10,
                                     old_shares=1, source_references=['official'])]
        result = frozen_nominal_outcome(**data)
        self.assertEqual(result['final_shares'], {'x': 50})
        self.assertEqual(result['equity'], '100')

    def test_merger_needs_no_later_quote_and_does_not_add_cash(self):
        data = inputs()
        del data['nominal_prices']['x']['2024-01-03']
        data['cash_merger_events'] = [dict(date='2024-01-03', security_id='x', share_cash='22', source_references=['official'])]
        result = frozen_nominal_outcome(**data)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['cash'], '0')
        self.assertEqual(result['receivable'], '110')
        self.assertEqual(result['return'], '1/10')

    def test_unknown_and_fractional_events_block_with_ledger(self):
        data = inputs()
        data['unmodelled_action_events'] = [dict(date='2024-01-03', security_id='x', source_references=['spinoff'])]
        result = frozen_nominal_outcome(**data)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(len(result['daily_ledger']), 1)
        self.assertIsNone(result['return'])
        data.pop('unmodelled_action_events')
        data['split_events'] = [dict(date='2024-01-03', security_id='x', new_shares=3, old_shares=2, source_references=['official'])]
        self.assertEqual(frozen_nominal_outcome(**data)['blocked_reason']['reason'], 'FRACTIONAL_SPLIT_ENTITLEMENT')

    def test_all_cash_and_evidence_required(self):
        data = inputs()
        data.update(target_weights={}, nominal_prices={})
        result = frozen_nominal_outcome(**data)
        self.assertEqual(result['equity'], '100')
        self.assertEqual(result['return'], '0')
        data = inputs()
        data['split_events'] = [dict(date='2024-01-03', security_id='x', new_shares=2, old_shares=1)]
        with self.assertRaises(ValueError):
            frozen_nominal_outcome(**data)


if __name__ == '__main__':
    unittest.main()

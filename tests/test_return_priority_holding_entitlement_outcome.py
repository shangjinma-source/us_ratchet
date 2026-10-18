import unittest
from backtest.return_priority_holding_entitlement_outcome import frozen_holding_with_entitlements


def fixture():
    event = dict(event_id='fixture', old_sid='old', new_sid='new', effective_date='2025-07-17',
                 effective_time_confirmed=True, eligibility_confirmed=True, cash_per_share='2',
                 new_shares_per_old_share='0.3399', source_references=['synthetic terms'])
    return dict(target_weights={'old': '1'}, entered_cash='100', metadata={'old': {'issuer_id': 'oldissuer'}},
                nominal_prices={'old': {'2025-07-16': {'open': '10', 'close': '10'}},
                                'new': {'2025-07-17': {'close': '20'}, '2025-07-18': {'close': '21'}}},
                session_dates=['2025-07-15', '2025-07-16', '2025-07-17', '2025-07-18'],
                decision_date='2025-07-15', end_date='2025-07-18', cash_stock_merger_events=[event],
                price_source_references={'new': ['conditional source']},
                fractional_settlements={'fixture': dict(known_asof='2025-07-17',
                    fraction_reference_close=dict(date='2025-07-16', price='20', source_references=['reference']),
                    reference_is_previous_closing_session=True, fraction_cash_rounding='CEIL_CENT', source_references=['terms'])})


class HoldingEntitlementTests(unittest.TestCase):
    def test_off_session_successor_split_blocks_and_retains_rights(self):
        args = fixture()
        args['session_dates'].append('2025-07-21')
        args['end_date'] = '2025-07-21'
        args['split_events'] = [dict(date='2025-07-19', security_id='new',
                                    new_shares=2, old_shares=1, source_references=['synthetic'])]
        result = frozen_holding_with_entitlements(**args)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['blocked_reason'], 'POST_MIXED_ACTION_REQUIRES_EXPLICIT_EXTENSION')
        self.assertEqual(result['last_valued_date'], '2025-07-18')
        self.assertEqual(result['entitlement_state']['merger_entitlements'][0]['pending_whole_shares'], 3)

    def test_same_day_successor_chain_and_nonzero_fee_fail_closed(self):
        args = fixture()
        args['cash_stock_merger_events'].append(dict(event_id='second', old_sid='new', new_sid='third', effective_date='2025-07-17'))
        self.assertEqual(frozen_holding_with_entitlements(**args)['status'], 'BLOCKED')
        args = fixture()
        args['fee_bps'] = '1'
        with self.assertRaisesRegex(ValueError, 'zero fees'):
            frozen_holding_with_entitlements(**args)

    def test_successor_pending_rights_second_merger_blocks(self):
        args = fixture()
        args['cash_stock_merger_events'].append(dict(event_id='second', old_sid='new', new_sid='third',
                                                    effective_date='2025-07-18'))
        result = frozen_holding_with_entitlements(**args)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['blocked_reason'], 'SUBSEQUENT_MIXED_EVENT_ON_ENTITLEMENT_NOT_SUPPORTED')
        self.assertEqual(result['last_valued_date'], '2025-07-17')
        self.assertEqual(result['entitlement_state']['merger_entitlements'][0]['pending_whole_shares'], 3)

    def test_merger_rights_marks_without_reinvestment(self):
        result = frozen_holding_with_entitlements(**fixture())
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['cash'], '0')
        self.assertEqual(result['final_shares']['old'], 0)
        self.assertNotIn('new', result['final_shares'])
        self.assertEqual(result['equity'], '4549/50')
        self.assertEqual(len(result['daily_ledger']), 3)

    def test_missing_successor_or_fraction_blocks_and_retains_rights(self):
        args = fixture()
        del args['nominal_prices']['new']['2025-07-18']
        result = frozen_holding_with_entitlements(**args)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['last_valued_date'], '2025-07-17')
        self.assertEqual(result['entitlement_state']['merger_entitlements'][0]['pending_whole_shares'], 3)
        args = fixture()
        args['fractional_settlements'] = {}
        self.assertEqual(frozen_holding_with_entitlements(**args)['status'], 'BLOCKED')

    def test_ordinary_split_delegates_unchanged(self):
        args = fixture()
        args['cash_stock_merger_events'] = []
        args['nominal_prices']['old'].update({'2025-07-17': {'close': '1'}, '2025-07-18': {'close': '1'}})
        args['split_events'] = [dict(date='2025-07-17', security_id='old', new_shares=10, old_shares=1, source_references=['official'])]
        result = frozen_holding_with_entitlements(**args)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['final_shares']['old'], 100)
        self.assertEqual(result['equity'], '100')

    def test_future_mixed_event_payload_not_read(self):
        args = fixture()
        args['cash_stock_merger_events'].append({'effective_date': '9999-01-01', 'old_sid': object()})
        self.assertEqual(frozen_holding_with_entitlements(**args)['status'], 'COMPLETE')


if __name__ == '__main__':
    unittest.main()

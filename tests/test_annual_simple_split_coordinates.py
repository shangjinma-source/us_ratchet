import unittest
from backtest.annual_simple_split_coordinates import (
    nominal_row, training_close, apply_quantity_event, build_coordinates)


class SplitCoordinatesTests(unittest.TestCase):
    def event(self):
        return dict(date='2024-06-10', ratio='10', share_event_candidate=True, event_id='NVDA_20240610')

    def test_boundary_training_and_quantity_once(self):
        event = self.event()
        before = nominal_row(day='2024-06-07', raw=dict(open='10', high='12', low='9', close='11'),
                             events=[event], capture_end='2024-12-31')
        after = nominal_row(day='2024-06-10', raw=dict(open='11', high='12', low='10', close='11'),
                            events=[event], capture_end='2024-12-31')
        self.assertEqual(before['ohlc']['close'], '110')
        self.assertEqual(after['factor'], '1')
        self.assertEqual(training_close(day='2024-06-07', decision_date='2024-06-10',
                         nominal_close='110', events=[event]), '11')
        self.assertEqual(training_close(day='2024-06-07', decision_date='2024-06-07',
                         nominal_close='110', events=[event]), '110')
        state = apply_quantity_event(day=event['date'], quantity=3, event=event, applied_ids=[])
        self.assertEqual(state['quantity'], 30)
        self.assertEqual(apply_quantity_event(day=event['date'], event=event, **state), state)

    def test_complex_domain_preserved_and_unknown_not_admitted(self):
        for ticker in ('WDC', 'HON', 'CMCSA', 'AZN', 'TRI'):
            row = build_coordinates(ticker=ticker, bars={}, events=[], capture_end='2026-10-13')
            self.assertEqual(row['ticker'], ticker)
            self.assertIsNone(row['nominal_ohlc'])
        event = self.event(); event['share_event_candidate'] = False
        self.assertEqual(build_coordinates(ticker='X', bars={}, events=[event],
                         capture_end='2026-10-13')['status'], 'BLOCKED_COMPLEX_OR_UNREVIEWED')

    def test_future_duplicate_and_fractional_fail_closed(self):
        event = self.event()
        with self.assertRaisesRegex(ValueError, 'FUTURE'):
            training_close(day='2024-06-10', decision_date='2024-06-07', nominal_close='1', events=[event])
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            nominal_row(day='2024-06-07', raw={}, events=[event, event], capture_end='2024-12-31')
        event['ratio'] = '3/2'
        with self.assertRaisesRegex(ValueError, 'FRACTIONAL'):
            apply_quantity_event(day=event['date'], quantity=1, event=event, applied_ids=[])

    def test_all_date_inputs_require_canonical_valid_iso(self):
        raw = dict(open='1', high='1', low='1', close='1')
        for invalid in ('2024-6-1', '20240601', '2024-02-30', '2024-W23-1', None):
            with self.subTest(value=invalid):
                with self.assertRaisesRegex(ValueError, 'CANONICAL'):
                    nominal_row(day=invalid, raw=raw, events=[], capture_end='2024-12-31')
                with self.assertRaisesRegex(ValueError, 'CANONICAL'):
                    nominal_row(day='2024-06-01', raw=raw, events=[], capture_end=invalid)
                with self.assertRaisesRegex(ValueError, 'CANONICAL'):
                    training_close(day='2024-06-01', decision_date=invalid, nominal_close='1', events=[])
                event = self.event(); event['date'] = invalid
                with self.assertRaisesRegex(ValueError, 'CANONICAL'):
                    nominal_row(day='2024-06-01', raw=raw, events=[event], capture_end='2024-12-31')
                with self.assertRaisesRegex(ValueError, 'CANONICAL'):
                    apply_quantity_event(day=invalid, quantity=1, event=self.event(), applied_ids=[])

    def test_missing_rows_are_explicitly_incomplete(self):
        row = build_coordinates(ticker='X', bars={'2024-06-01':dict(open=None)},
                                events=[], capture_end='2024-12-31')
        self.assertFalse(row['supplied_rows_complete'])
        self.assertEqual(row['missing_ohlc_dates'], ['2024-06-01'])
        self.assertFalse(row['execution_admitted'])


if __name__ == '__main__':
    unittest.main()

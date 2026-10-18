import unittest
from datetime import date, timedelta
from scripts.return_priority_historical_swing_inputs import decision_unit_history


class UnitHistoryTests(unittest.TestCase):
    def test_dated_split_and_future_poison(self):
        days = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(21)]
        prices = {'x': {day: dict(open='100', high='100', low='100', close='100') for day in days[:19]}}
        prices['x'][days[19]] = dict(open='10', high='10', low='10', close='10')
        prices['x'][days[20]] = object()
        events = [dict(date=days[19], security_id='x', new_shares=10, old_shares=1, source_references=['official']),
                  dict(date=days[20], new_shares=object())]
        result = decision_unit_history(nominal_ohlc=prices, calendar=days, security_id='x', decision_date=days[19], split_events=events)
        self.assertTrue(all(bar['close'] == '10' for bar in result['bars']))
        self.assertEqual(prices['x'][days[0]]['close'], '100')
        del prices['x'][days[2]]
        with self.assertRaises(KeyError):
            decision_unit_history(nominal_ohlc=prices, calendar=days, security_id='x', decision_date=days[19], split_events=events)


if __name__ == '__main__':
    unittest.main()

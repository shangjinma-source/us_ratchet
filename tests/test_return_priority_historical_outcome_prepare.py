import unittest
from datetime import date, timedelta
from scripts.return_priority_historical_outcome_prepare import prepare_window


class PreparationTests(unittest.TestCase):
    def fixtures(self):
        days = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(22)]
        inputs = {'search_arguments': {'decision_date': days[0], 'entered_cash': '20000',
                                       'metadata': {'s': {'ticker': 'X', 'issuer_id': 'i'}}}}
        search = {'selected': {'actual_weights': {'s': '1/2'}, 'cash_fraction': '1/2'}}
        nominal = {'X': {'basis': 'NOMINAL', 'source_references': ['manifest'],
                         'rows': {day: {'open': '10', 'close': '11'} for day in days}}}
        return inputs, search, days, nominal

    def test_preserves_weights_and_rejects_quote_basis(self):
        inputs, search, days, nominal = self.fixtures()
        result = prepare_window(inputs, search, days, nominal, [])
        self.assertEqual(result['outcome_arguments']['target_weights'], {'s': '1/2'})
        self.assertEqual(result['price_gaps'], [])
        nominal['X']['basis'] = 'PROVIDER_QUOTE'
        result = prepare_window(inputs, search, days, nominal, [])
        self.assertEqual(len(result['price_gaps']), 22)
        self.assertEqual(result['outcome_arguments']['target_weights'], {'s': '1/2'})

    def test_terminal_gaps_and_unmodelled_retained(self):
        inputs, search, days, nominal = self.fixtures()
        nominal['X']['rows'] = {days[1]: {'open': '10', 'close': '11'}}
        events = [dict(ticker='X', date=days[2], kind='merger', share_cash='12', source_references=['official'])]
        result = prepare_window(inputs, search, days, nominal, events)
        self.assertEqual(result['price_gaps'], [])
        self.assertEqual(result['outcome_arguments']['cash_merger_events'][0]['security_id'], 's')
        events[0]['kind'] = 'unmodelled'
        result = prepare_window(inputs, search, days, nominal, events)
        self.assertEqual(len(result['outcome_arguments']['unmodelled_action_events']), 1)
        self.assertEqual(result['frozen_selected'], search['selected'])

    def test_cash_complete_without_prices(self):
        inputs, search, days, nominal = self.fixtures()
        search['selected'] = {'actual_weights': {}, 'cash_fraction': '1'}
        result = prepare_window(inputs, search, days, {}, [])
        self.assertEqual(result['status'], 'PREPARED_NOT_EXECUTED')
        self.assertEqual(result['outcome_calls'], 0)


if __name__ == '__main__':
    unittest.main()

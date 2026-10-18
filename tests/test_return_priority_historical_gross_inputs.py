import copy
import unittest
from datetime import date, timedelta
from scripts.return_priority_historical_gross_inputs import prepare


def fixture():
    dates = [(date(2022, 1, 1) + timedelta(days=i)).isoformat() for i in range(253)]
    candidate = {'ticker': 'X', 'security_id': 'sid:X', 'issuer_id': 'issuer:X',
                 'training_basis': 'NOMINAL', 'training_close': ['100'] * 253,
                 'decision_nominal_close': '77', 'exclusion_reasons': [],
                 'eligible_for_pending_split_validation': True, 'missing_training_dates': []}
    return {'windows': [{'decision_cutoff': dates[-1], 'training_dates': dates,
                         'scenario_start_dates': dates[0:252:21], 'scenario_end_dates': dates[21:253:21],
                         'member_denominator': 1, 'candidates': [candidate]}]}


def event(when):
    return {'ticker': 'X', 'event_date': when, 'new_shares': 2, 'old_shares': 1,
            'conditional_unit_conversion_event': True}


class GrossPreparationTests(unittest.TestCase):
    def test_boundary_duplicate_and_future_poison(self):
        data = fixture()
        dates = data['windows'][0]['training_dates']
        events = [event(dates[0]), event(dates[21]), event(dates[21]),
                  {'event_date': '9999-01-01', 'new_shares': object()}]
        before = copy.deepcopy(data)
        result = prepare(data, events)['windows'][0]['search_arguments']
        self.assertEqual(result['training_scenarios'][0]['sid:X'], '2')
        self.assertEqual(result['training_scenarios'][1]['sid:X'], '1')
        self.assertEqual(result['prices']['sid:X'], '77')
        self.assertEqual(data, before)

    def test_provider_basis_never_double_adjusted(self):
        data = fixture()
        window = data['windows'][0]
        window['candidates'][0]['training_basis'] = 'CONDITIONAL_PROVIDER_QUOTE_SPLIT_ADJUSTED'
        window['candidates'][0]['missing_training_dates'] = ['old-cache-gap']
        args = prepare(data, [event(window['training_dates'][21])])['windows'][0]['search_arguments']
        self.assertEqual(args['training_scenarios'][0]['sid:X'], '1')
        self.assertEqual(args['prices']['sid:X'], '77')

    def test_missing_retains_denominator_and_rejects_conflicts(self):
        data = fixture()
        data['windows'][0]['candidates'][0]['training_close'][5] = None
        result = prepare(data, [])['windows'][0]
        self.assertEqual(result['member_denominator'], 1)
        self.assertEqual(len(result['exclusions']), 1)
        self.assertEqual(result['search_arguments']['prices'], {})
        data = fixture()
        first = event(data['windows'][0]['training_dates'][21])
        second = dict(first, new_shares=3)
        with self.assertRaises(ValueError):
            prepare(data, [first, second])
        with self.assertRaises(ValueError):
            prepare(data, [dict(first, event_type='SPINOFF')])


if __name__ == '__main__':
    unittest.main()

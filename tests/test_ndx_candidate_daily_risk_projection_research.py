from copy import deepcopy
from datetime import date, timedelta
import unittest

from backtest import ndx_candidate_daily_risk_projection_research as module


def fixture():
    calendar = [(date(2026, 1, 1) + timedelta(days=n)).isoformat() for n in range(120)]
    state = dict(calendar=calendar, closes=dict(index=calendar[:], columns=['COL_B', 'COL_A'],
        data=[[5, 20] for _ in calendar]), internal_columns_by_security={'a/1': 'COL_A', 'b': 'COL_B'},
        risk_chains_by_decision={calendar[0]: {'a/1': 'X', 'b': 'Y'}, calendar[60]: {'a/1': 'Z'}})
    daily = [dict(session=day, holdings={} if n == 0 else {'a/1': dict(ticker='COL_A', shares=1),
             'b': dict(ticker='COL_B', shares=2)}) for n, day in enumerate(calendar)]
    return dict(stateful_input=state, daily=daily)


class Tests(unittest.TestCase):
    def test_sid_join_uses_original_column_order_and_asof_dates(self):
        arguments = fixture(); original = deepcopy(arguments)
        result = module.project_path(**arguments)
        self.assertEqual(arguments, original)
        self.assertEqual(result['path_day_count'], 120)
        self.assertIsNone(result['rows'][0]['diagnostic']['metrics'])
        self.assertEqual(result['rows'][1]['diagnostic']['security_weights']['a/1'],
                         dict(numerator='2', denominator='3'))
        self.assertEqual(result['rows'][1]['source_locator_tokens']['a/1']['price_tokens'], ['closes', 'data', 1, 1])
        self.assertEqual(result['rows'][59]['diagnostic']['label_observations']['a/1']['label'], 'X')
        self.assertEqual(result['rows'][60]['diagnostic']['label_observations']['a/1']['label'], 'Z')

    def test_missing_source_or_original_risk_cannot_be_laundered(self):
        for attack in ('day', 'price', 'alias', 'future_label', 'existing_risk', 'column'):
            with self.subTest(attack=attack):
                arguments = fixture(); state, daily = arguments['stateful_input'], arguments['daily']
                if attack == 'day': daily.pop()
                elif attack == 'price': state['closes']['data'][1][1] = None
                elif attack == 'alias': daily[1]['holdings']['a/1']['ticker'] = 'COL_B'
                elif attack == 'future_label': del state['risk_chains_by_decision'][state['calendar'][0]]['a/1']
                elif attack == 'existing_risk': daily[0]['risk'] = None
                else: state['closes']['columns'][1] = 'COL_B'
                with self.assertRaises(ValueError): module.project_path(**arguments)


if __name__ == '__main__':
    unittest.main()

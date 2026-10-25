from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import unittest

from data.monthly_peak_raw_history import normalize_monthly_raw
import test_monthly_peak_exit_history as history_fixture


class MonthlyRawHistoryTests(unittest.TestCase):
    def fixture(self):
        inputs = history_fixture.MonthlyHistoryTests().inputs()
        dates = inputs['session_dates']
        series = dict(meta=dict(symbol='TEST', currency='USD', exchangeName='NMS', instrumentType='EQUITY'),
            timestamp=[int(datetime.fromisoformat(day+'T14:00:00+00:00').timestamp()) for day in dates],
            indicators=dict(quote=[dict(close=[100, 80, 110])], adjclose=[dict(adjclose=[100, 80, 110])]), events={})
        return inputs, series

    def run_source(self, inputs, series):
        raw = json.dumps(dict(chart=dict(error=None, result=[series]))).encode()
        return normalize_monthly_raw(inputs=inputs, sources={'A': raw},
            expected_hashes={'A': sha256(raw).hexdigest()}, identities={'A': dict(ticker='TEST', exchange='NMS')})

    def test_full_raw_restores_missing_normalized_prefix(self):
        inputs, series = self.fixture()
        inputs['histories']['A']['closes'] = inputs['histories']['A']['closes'][-1:]
        result = self.run_source(inputs, series)
        self.assertEqual(len(result['observations']), 3)
        self.assertEqual(result['observations'][1]['closes']['A'], '80')

    def test_missing_raw_day_or_adjustment_rejected(self):
        inputs, series = self.fixture()
        adjusted = deepcopy(series)
        adjusted['indicators']['adjclose'][0]['adjclose'][0] = 90
        missing = deepcopy(series)
        missing['timestamp'] = missing['timestamp'][1:]
        missing['indicators']['quote'][0]['close'] = [80, 110]
        missing['indicators']['adjclose'][0]['adjclose'] = [80, 110]
        for bad in (adjusted, missing):
            with self.assertRaises(ValueError):
                self.run_source(inputs, bad)


if __name__ == '__main__':
    unittest.main()

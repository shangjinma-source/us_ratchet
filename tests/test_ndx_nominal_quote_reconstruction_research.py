from copy import deepcopy
from datetime import datetime, timezone
import json
import unittest

from backtest import ndx_nominal_quote_reconstruction_research as nominal


def fixture():
    days = ['2024-06-03', '2024-06-04', '2024-06-05', '2024-06-06']
    times = [int(datetime.fromisoformat(day + 'T13:30:00+00:00').timestamp()) for day in days]
    end = int(datetime.fromisoformat('2024-06-07T00:00:00+00:00').timestamp())
    payload = dict(chart=dict(error=None, result=[dict(meta=dict(symbol='AAA', currency='USD',
        exchangeTimezoneName='America/New_York', instrumentType='EQUITY', dataGranularity='1d'),
        timestamp=times, indicators=dict(quote=[dict(open=[1., 2., 3., 4.], close=[2., 3., 4., 5.])],
        adjclose=[dict(adjclose=[.1, .2, .3, .4])]),
        events=dict(splits={str(times[1]): dict(date=times[1], numerator=2., denominator=1., splitRatio='2:1'),
                           str(times[3]): dict(date=times[3], numerator=10., denominator=1., splitRatio='10:1')},
                    dividends={str(times[0]): dict(date=times[0], amount=100.)}))]))
    parameters = dict(ticker='AAA', calendar=days[:2],
        request=dict(method='GET', credentials_sent=False,
            url=f'https://query1.finance.yahoo.com/v8/finance/chart/AAA?period1={times[0]-86400}&period2={end}&interval=1d&events=div%2Csplits'),
        received_at_utc='2024-06-07T00:01:00+00:00', quote_field_basis=nominal.BASIS)
    return payload, parameters


def run(payload, parameters):
    return nominal.reconstruct_nominal_quote_ticker(raw=json.dumps(payload).encode(), **parameters)


class NominalReconstructionTests(unittest.TestCase):
    def test_inside_and_after_window_splits_exclude_effective_day_own_split(self):
        payload, parameters = fixture()
        result = run(payload, parameters)
        self.assertEqual([r['split_factor'] for r in result['rows']], [20., 10.])
        self.assertEqual([r['nominal_open'] for r in result['rows']], [20., 20.])
        self.assertEqual([r['nominal_close'] for r in result['rows']], [40., 30.])
        self.assertFalse(result['point_in_time_verified'])

    def test_dividends_and_adjclose_do_not_modify_quote_reconstruction(self):
        payload, parameters = fixture()
        result = run(payload, parameters)
        changed = deepcopy(payload)
        changed['chart']['result'][0]['events']['dividends'] = {}
        changed['chart']['result'][0]['indicators']['adjclose'] = [dict(adjclose=[None]*4)]
        self.assertEqual(result['rows'], run(changed, parameters)['rows'])

    def test_unknown_basis_and_bad_coordinates_rejected(self):
        for fault in ('basis', 'currency', 'symbol', 'request_symbol', 'calendar_gap', 'calendar_duplicate', 'timezone'):
            payload, parameters = fixture()
            data = payload['chart']['result'][0]
            if fault == 'basis': parameters['quote_field_basis'] = 'UNKNOWN'
            if fault == 'currency': data['meta']['currency'] = 'HKD'
            if fault == 'symbol': data['meta']['symbol'] = 'BBB'
            if fault == 'request_symbol': parameters['request']['url'] = parameters['request']['url'].replace('/AAA?', '/BBB?')
            if fault == 'calendar_gap': parameters['calendar'] = ['2024-06-03', '2024-06-07']
            if fault == 'calendar_duplicate': parameters['calendar'] *= 2
            if fault == 'timezone': data['meta']['exchangeTimezoneName'] = 'UTC'
            with self.assertRaises(ValueError, msg=fault): run(payload, parameters)

    def test_null_bool_duplicate_dates_and_split_conflicts_rejected(self):
        for fault in ('null', 'bool', 'duplicate_day', 'timestamp_bool', 'ratio', 'date', 'split_bool', 'future_split'):
            payload, parameters = fixture()
            data = payload['chart']['result'][0]
            event = next(iter(data['events']['splits'].values()))
            if fault == 'null': data['indicators']['quote'][0]['open'][0] = None
            if fault == 'bool': data['indicators']['quote'][0]['close'][0] = True
            if fault == 'duplicate_day': data['timestamp'][1] = data['timestamp'][0] + 60
            if fault == 'timestamp_bool': data['timestamp'][0] = True
            if fault == 'ratio': event['splitRatio'] = '3:1'
            if fault == 'date': event['date'] += 1
            if fault == 'split_bool': event['numerator'] = True
            if fault == 'future_split':
                data['events']['splits'] = {'1900000000': dict(date=1900000000, numerator=2, denominator=1, splitRatio='2:1')}
            with self.assertRaises(ValueError, msg=fault): run(payload, parameters)

    def test_duplicate_json_key_rejected(self):
        payload, parameters = fixture()
        raw = json.dumps(payload).replace('"currency": "USD"', '"currency":"USD","currency":"HKD"').encode()
        with self.assertRaisesRegex(ValueError, 'Duplicate raw JSON key'):
            nominal.reconstruct_nominal_quote_ticker(raw=raw, **parameters)


if __name__ == '__main__':
    unittest.main()

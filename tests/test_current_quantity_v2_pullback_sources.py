from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
import unittest

from data.current_quantity_v2_pullback_sources import candidate_from_yahoo_bytes


def epoch(value):
    return int(datetime.fromisoformat('2026-10-15T' + value + '-04:00').timestamp())


def payload():
    return {'chart': {'error': None, 'result': [{
        'meta': {'symbol': 'SNDK', 'currency': 'USD', 'instrumentType': 'EQUITY',
                 'exchangeTimezoneName': 'America/New_York', 'dataGranularity': '1m',
                 'regularMarketPrice': 1356.8, 'regularMarketTime': epoch('09:32:14'),
                 'currentTradingPeriod': {'regular': {'start': epoch('09:30:00'),
                                                     'end': epoch('16:00:00')}}},
        'timestamp': [epoch('09:30:00'), epoch('09:31:00'), epoch('09:32:00')],
        'indicators': {'quote': [{'open': [1300, 1340, None],
                                 'high': [1350, 1360, None],
                                 'low': [1276.07, 1330, 1],
                                 'close': [1340, 1355, None], 'volume': [100, 100, 0]}]}}]}}


def invoke(data=None, **changes):
    raw = json.dumps(payload() if data is None else data).encode()
    args = dict(raw=raw, expected_sha256=sha256(raw).hexdigest(), security_id='SNDK-ID',
                ticker='SNDK', session='2026-10-15',
                session_open='2026-10-15T09:30:00-04:00',
                session_close='2026-10-15T16:00:00-04:00',
                captured_at='2026-10-15T09:32:15-04:00',
                checked_at='2026-10-15T09:32:16-04:00', now='2026-10-15T09:32:17-04:00',
                rebound_fraction='1/2', minimum_discount='1/200',
                maximum_age_seconds=120, previous_cap=None)
    args.update(changes)
    return candidate_from_yahoo_bytes(**args)


class PullbackSourcesTests(unittest.TestCase):
    def test_strict_provider_last_trade_snapshot_is_not_a_bar(self):
        data = payload()
        result = data['chart']['result'][0]
        result['timestamp'].append(epoch('09:32:14'))
        for key in ('open', 'high', 'low', 'close'):
            # Provider tail uses a binary-float representation unlike metadata.
            result['indicators']['quote'][0][key].append(1356.800048828125)
        result['indicators']['quote'][0]['volume'].append(0)
        decoded = invoke(data)
        self.assertEqual(decoded['receipt']['excluded_rows']['provider_last_trade_snapshot'], 1)
        self.assertEqual(len(decoded['reference']['bars']), 2)
        for mutate in [lambda r: r['timestamp'].__setitem__(-1, epoch('09:32:13')),
                       lambda r: r['indicators']['quote'][0]['volume'].__setitem__(-1, 1),
                       lambda r: r['indicators']['quote'][0]['low'].__setitem__(-1, 1),
                       lambda r: r['timestamp'].__setitem__(0, epoch('09:30:01'))]:
            changed = deepcopy(data)
            mutate(changed['chart']['result'][0])
            with self.assertRaises(ValueError):
                invoke(changed)

    def test_raw_decode_excludes_partial_low_and_is_reproducible(self):
        result = invoke()
        self.assertEqual(result, invoke())
        self.assertEqual(len(result['reference']['bars']), 2)
        self.assertEqual(result['receipt']['excluded_rows']['incomplete_tail'], 1)
        self.assertEqual(Fraction(result['candidate']['observed_session_low']), Fraction('1276.07'))
        self.assertEqual(Fraction(result['candidate']['limit_price']), Fraction('1316.43'))
        self.assertEqual(result['candidate']['input_digest'], result['receipt']['reference_digest'])
        self.assertFalse(result['candidate']['source_authenticated'])

    def test_hash_and_identity_session_mismatches(self):
        for change in [dict(expected_sha256='0' * 64), dict(ticker='MU'),
                       dict(session='2026-10-14'), dict(session_open='2026-10-15T09:29:00-04:00')]:
            with self.assertRaises(ValueError):
                invoke(**change)
        for key, value in [('instrumentType', 'ETF'), ('currency', 'HKD'),
                           ('dataGranularity', '5m'), ('exchangeTimezoneName', 'UTC')]:
            data = payload()
            data['chart']['result'][0]['meta'][key] = value
            with self.assertRaises(ValueError):
                invoke(data)

    def test_complete_bar_gaps_nulls_zero_volume_invalid_ohlc_future_rejected(self):
        mutations = [lambda r: r['timestamp'].__setitem__(0, epoch('09:29:00')),
                     lambda r: r['timestamp'].__setitem__(1, epoch('09:30:00')),
                     lambda r: r['timestamp'].__setitem__(2, epoch('09:33:00')),
                     lambda r: r['indicators']['quote'][0]['low'].__setitem__(0, None),
                     lambda r: r['indicators']['quote'][0]['volume'].__setitem__(0, 0),
                     lambda r: r['indicators']['quote'][0]['low'].__setitem__(0, 9999),
                     lambda r: r.update(events={'splits': {'x': {'splitRatio': '2:1'}}})]
        for mutate in mutations:
            data = payload()
            mutate(data['chart']['result'][0])
            with self.assertRaises(ValueError):
                invoke(data)

    def test_json_nonfinite_duplicate_keys_bad_lengths_and_string_numbers(self):
        for raw in [b'{"chart":{},"chart":{}}', b'{"chart":NaN}']:
            with self.assertRaises(ValueError):
                invoke(raw=raw, expected_sha256=sha256(raw).hexdigest())
        for value in ['1356.8', True, float('inf')]:
            data = payload()
            data['chart']['result'][0]['meta']['regularMarketPrice'] = value
            with self.assertRaises(ValueError):
                invoke(data)
        data = payload()
        data['chart']['result'][0]['indicators']['quote'][0]['low'].pop()
        with self.assertRaises(ValueError):
            invoke(data)

    def test_stale_and_policy_cap_binding_replayed_through_adapter(self):
        with self.assertRaises(ValueError):
            invoke(now='2026-10-15T09:34:00-04:00')
        result = invoke()
        cap = deepcopy(result['candidate']['cap_declaration'])
        data = payload()
        data['chart']['result'][0]['meta']['regularMarketPrice'] = 1450
        raised = invoke(data, previous_cap=cap)
        self.assertEqual(raised['candidate']['limit_price'], result['candidate']['limit_price'])
        with self.assertRaises(ValueError):
            invoke(data, previous_cap=cap, rebound_fraction='1/4')


if __name__ == '__main__':
    unittest.main()

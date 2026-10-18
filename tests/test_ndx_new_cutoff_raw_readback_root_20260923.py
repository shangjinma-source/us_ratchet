from datetime import datetime, timezone
import json
import unittest

from scripts import ndx_new_cutoff_raw_readback_20260923 as module


class RootRawReadbackTests(unittest.TestCase):
    def payload(self):
        return {'chart': {'error': None, 'result': [{
            'meta': {'symbol': 'TEST', 'exchangeTimezoneName': 'America/New_York'},
            'timestamp': [int(datetime(2026, 9, 22, 23, tzinfo=timezone.utc).timestamp()),
                          int(datetime(2026, 9, 23, 13, tzinfo=timezone.utc).timestamp())],
            'indicators': {'quote': [{'open': [20, 21], 'high': [21, 22], 'low': [19, 20],
                                     'close': [20, 21], 'volume': [100, 200]}]},
            'events': {'splits': {'x': {'numerator': 10, 'denominator': 1}}}
        }]}}

    def test_raw_observation_never_promotes_events_or_units(self):
        result = module.parse_channel(json.dumps(self.payload()).encode(), 'TEST', '2026-09-23')
        self.assertEqual(result['last_completed_date'], '2026-09-22')
        self.assertEqual([row['excluded_receipt_day_or_later'] for row in result['rows']], [False, True])
        self.assertEqual(result['rows'][0]['raw_provider_fields']['close'], 20)
        self.assertEqual(result['volume_unit'], 'UNKNOWN_PROVIDER_UNIT_NO_SPLIT_ADJUSTMENT_ASSUMED')
        self.assertTrue(all(result[flag] is False for flag in module.FLAGS))

    def test_provider_error_and_boolean_timestamp_fail(self):
        payload = self.payload()
        payload['chart']['error'] = {'description': 'unavailable'}
        with self.assertRaises(ValueError):
            module.parse_channel(json.dumps(payload).encode(), 'TEST', '2026-09-23')
        payload = self.payload()
        payload['chart']['result'][0]['timestamp'][0] = True
        with self.assertRaises(ValueError):
            module.parse_channel(json.dumps(payload).encode(), 'TEST', '2026-09-23')


if __name__ == '__main__':
    unittest.main()

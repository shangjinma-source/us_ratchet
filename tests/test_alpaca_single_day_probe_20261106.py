import copy
import unittest
import tempfile
from unittest.mock import patch
from scripts.research.alpaca_single_day_probe_20261106 import inspect, main


class ProbeChecks(unittest.TestCase):
    def test_dry_run_does_not_read_credentials_or_request(self):
        with patch('sys.argv', ['probe']), patch('builtins.print'), \
             patch('requests.get', side_effect=AssertionError('network request')), \
             patch('scripts.research.alpaca_single_day_probe_20261106.os') as local_os:
            local_os.environ.get.side_effect = AssertionError('credential read')
            self.assertEqual(main(), 0)

    def test_existing_output_rejected_before_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('sys.argv', ['probe', '--execute', '--output', directory]), \
                 patch('builtins.print'), \
                 patch('requests.get', side_effect=AssertionError('network request')), \
                 patch('scripts.research.alpaca_single_day_probe_20261106.os') as local_os:
                local_os.environ.get.side_effect = AssertionError('credential read')
                self.assertEqual(main(), 2)

    def payload(self):
        return {'bars': {'AAPL': [dict(t='2022-01-03T14:30:00Z', o=10, h=12,
                                      l=9, c=11, v=100)]}, 'next_page_token': None}

    def test_missing_not_filled(self):
        result = inspect(self.payload())
        self.assertTrue(result['accepted'])
        self.assertEqual(result['missing_minutes'], 389)
        self.assertFalse(result['full_regular_session'])
        self.assertEqual(result['status'], 'INCOMPLETE_OR_INVALID')

    def test_malformed_shapes_rejected_without_exception(self):
        for p in [[], {'bars': []}, {'bars': {'AAPL': [None]}}, {'bars': {'AAPL': [{'t': 123}]}}]:
            self.assertFalse(inspect(p)['accepted'])

    def test_duplicate_and_order(self):
        p = self.payload()
        p['bars']['AAPL'] *= 2
        self.assertIn('duplicate_timestamps', inspect(p)['errors'])
        p = self.payload()
        later = copy.deepcopy(p['bars']['AAPL'][0])
        later['t'] = '2022-01-03T14:31:00Z'
        p['bars']['AAPL'].insert(0, later)
        self.assertIn('not_strictly_ordered', inspect(p)['errors'])

    def test_out_of_bounds_and_bad_timestamp(self):
        for timestamp in ['2022-01-03T21:00:00Z', '2022-01-03T14:30:00', 'bad']:
            p = self.payload()
            p['bars']['AAPL'][0]['t'] = timestamp
            self.assertFalse(inspect(p)['accepted'])

    def test_invalid_ohlcv(self):
        for key, value in [('h', 8), ('l', 0), ('v', -1), ('v', 0.5), ('c', float('nan')), ('v', True)]:
            p = self.payload()
            p['bars']['AAPL'][0][key] = value
            self.assertFalse(inspect(p)['accepted'])

    def test_incomplete_pagination(self):
        p = self.payload()
        p['next_page_token'] = 'synthetic-next-page'
        self.assertIn('pagination_incomplete', inspect(p)['errors'])


if __name__ == '__main__':
    unittest.main()

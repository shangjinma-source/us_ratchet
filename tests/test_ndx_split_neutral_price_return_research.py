from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backtest.ndx_split_neutral_price_return_research import (
    calculate_split_neutral_price_returns as calculate,
    build_split_neutral_price_return_research as build)


def fixture(closes=(100, 10.08, 20.56), ratios=(1, 10, .5), basis='NOMINAL_CLOSE'):
    days = ['2024-06-07', '2024-06-10', '2024-06-11']
    return dict(schema='ndx_split_neutral_return_input_v1', basis=basis, calendar=days,
        securities={'security:A': {'issuer_id': 'issuer:A'}}, dividend_adjustment_in_close=False,
        event_denominator_scope='EXPLICIT_ALL_SUBMITTED_SECURITY_SESSIONS',
        rows=[dict(security_id='security:A', issuer_id='issuer:A', ticker='A', session=d, close=c)
              for d, c in zip(days, closes)],
        daily_share_ratios=[dict(security_id='security:A', session=d, new_shares=r, old_shares=1)
                            for d, r in zip(days, ratios)])


class SplitNeutralReturnTests(unittest.TestCase):
    def test_real_crash_without_event_is_not_reclassified_as_split(self):
        for after, expected in [(50, -.5), (10, -.9)]:
            rows = calculate(fixture((100, after, after), (1, 1, 1)))['rows']
            self.assertEqual(rows[0]['price_return'], expected)
        self.assertEqual(calculate(fixture((100, 10.1, 10.1), (1, 10, 1)))['rows'][0]['price_return'], .01)

    def test_forward_then_reverse_split_retains_actual_market_move(self):
        rows = calculate(fixture())['rows']
        self.assertAlmostEqual(rows[0]['price_return'], .008)
        self.assertAlmostEqual(rows[1]['price_return'], 10.28 / 10.08 - 1)

    def test_already_adjusted_never_double_multiplies(self):
        rows = calculate(fixture((10, 10.08, 10.28), basis='SPLIT_ONLY_ADJUSTED_CLOSE'))['rows']
        self.assertAlmostEqual(rows[0]['price_return'], .008)
        self.assertTrue(all(row['applied_share_ratio'] == '1' for row in rows))

    def test_no_split_equals_pct_change(self):
        values = (100, 103, 99)
        rows = calculate(fixture(values, (1, 1, 1)))['rows']
        for i, row in enumerate(rows):
            self.assertAlmostEqual(row['price_return'], values[i + 1] / values[i] - 1)

    def test_later_uniform_price_rescale_does_not_change_prior_returns(self):
        first = calculate(fixture())['rows']
        second = calculate(fixture((1000, 100.8, 205.6)))['rows']
        self.assertEqual([r['price_return'] for r in first], [r['price_return'] for r in second])

    def test_unknown_basis_or_dividend_adjustment_rejected(self):
        for key, value in [('basis', 'UNKNOWN'), ('dividend_adjustment_in_close', True)]:
            payload = fixture(); payload[key] = value
            with self.assertRaises(ValueError): calculate(payload)

    def test_incomplete_or_duplicate_event_denominator_rejected(self):
        for change in ('missing', 'duplicate'):
            payload = fixture()
            if change == 'missing': payload['daily_share_ratios'].pop()
            else: payload['daily_share_ratios'].append(deepcopy(payload['daily_share_ratios'][0]))
            with self.assertRaises(ValueError): calculate(payload)

    def test_nan_boolean_zero_prices_and_ratios_rejected(self):
        for value in (float('nan'), float('inf'), True, 0, -1):
            for table, field in [('rows', 'close'), ('daily_share_ratios', 'new_shares')]:
                payload = fixture(); payload[table][1][field] = value
                with self.assertRaises(ValueError): calculate(payload)

    def test_rename_preserves_sid_but_wrong_issuer_rejected(self):
        payload = fixture(); payload['rows'][1]['ticker'] = 'B'
        result = calculate(payload)
        self.assertEqual(result['rows'][0]['security_id'], 'security:A')
        self.assertEqual(result['rows'][0]['ticker'], 'B')
        payload['rows'][1]['issuer_id'] = 'issuer:B'
        with self.assertRaises(ValueError): calculate(payload)

    def test_bound_source_changed_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'raw'; source.write_bytes(b'evidence')
            payload = fixture(); payload['source_hashes'] = {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
            path = Path(directory) / 'input.json'; path.write_text(json.dumps(payload))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(build(input_path=path, expected_sha256=digest)['output_return_count'], 2)
            source.write_bytes(b'changed')
            with self.assertRaises(ValueError): build(input_path=path, expected_sha256=digest)


if __name__ == '__main__':
    unittest.main()

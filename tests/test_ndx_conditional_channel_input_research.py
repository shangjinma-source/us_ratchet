import copy
import json
import unittest
from datetime import datetime, timedelta
from fractions import Fraction
from zoneinfo import ZoneInfo

from backtest.ndx_conditional_channel_input_research import build_channel_input


def fixture(event_index=None, kind='ORDINARY_SPLIT', floor_index=None):
    start = datetime(2026, 1, 1, 9, 30, tzinfo=ZoneInfo('America/New_York'))
    dates = [(start + timedelta(days=i)).date().isoformat() for i in range(128)]
    stamps = [int((start + timedelta(days=i)).timestamp()) for i in range(128)]
    values = [100 + i / 10 for i in range(128)]
    policy = []
    splits = {}
    if event_index is not None:
        stamp = stamps[event_index]
        splits[str(stamp)] = dict(date=stamp, numerator=2, denominator=1, splitRatio='2:1')
        policy = [dict(session=dates[event_index], numerator=2, denominator=1, kind=kind)]
    rows = []
    for i, session in enumerate(dates[:-1]):
        factor = 2 if event_index is not None and event_index > i else 1
        rows.append(dict(session=session, ticker='TEST', currency='USD', provider_timestamp=stamps[i],
                         quote_open=values[i], quote_close=values[i], nominal_open=values[i] * factor,
                         nominal_close=values[i] * factor, split_factor=factor,
                         split_factor_numerator=str(factor), split_factor_denominator='1',
                         later_split_effective_sessions=[dates[event_index]] if factor == 2 else []))
    data = dict(meta=dict(symbol='TEST', currency='USD', instrumentType='EQUITY',
                         exchangeTimezoneName='America/New_York', dataGranularity='1d'),
                timestamp=stamps, events=dict(splits=splits, dividends={}),
                indicators=dict(quote=[dict(open=values, close=values, volume=[1000000] * 128)]))
    return dict(ticker='TEST', raw_bytes=json.dumps(dict(chart=dict(error=None, result=[data]))).encode(),
                quote_rows=rows, calendar=dates[:-1], cutoff=dates[-2], exclude_on_or_after=dates[-1],
                event_policy=policy, regular_floor=dates[floor_index] if floor_index is not None else None)


class ChannelTests(unittest.TestCase):
    def test_no_event_channel_is_not_a_security_or_admission(self):
        result = build_channel_input(**fixture())
        self.assertEqual(len(result['price_returns']), 126)
        self.assertEqual(len(result['liquidity']['rows']), 63)
        self.assertTrue(result['liquidity']['numerical_threshold_passed'])
        self.assertFalse(result['legal_training_input_admitted'])
        self.assertFalse(result['security_identity_verified'])
        self.assertNotIn('security_id', result)

    def test_returned_cash_dividend_preserved_in_serializable_non_total_return_output(self):
        inputs = fixture()
        body = json.loads(inputs['raw_bytes'])
        channel = body['chart']['result'][0]
        stamp = channel['timestamp'][80]
        channel['events']['dividends'] = {str(stamp): dict(date=stamp, amount=0.23)}
        inputs['raw_bytes'] = json.dumps(body).encode()
        result = build_channel_input(**inputs)
        restored = json.loads(json.dumps(result, allow_nan=False))
        self.assertEqual(restored['returned_events'], channel['events'])
        self.assertFalse(restored['dividend_cash_flows_included'])

    def test_split_neutral_return_and_separate_liquidity_disposition(self):
        for split_index in (40, 80):
            with self.subTest(split_index=split_index):
                result = build_channel_input(**fixture(split_index))
                row = result['price_returns'][split_index - 1]
                expected = float(Fraction(str(100 + split_index / 10)) /
                                 Fraction(str(100 + (split_index - 1) / 10)) - 1)
                self.assertAlmostEqual(row['price_return'], expected, places=14)
                self.assertEqual(row['declared_share_ratio'], '2')
                if split_index == 80:
                    self.assertEqual(result['liquidity']['status'], 'BLOCKED_VOLUME_UNIT_UNKNOWN')
                    self.assertIsNone(result['liquidity']['numerical_threshold_passed'])
                    self.assertIsNone(result['liquidity']['rows'])
                else:
                    self.assertEqual(len(result['liquidity']['rows']), 63)

    def test_event_after_cutoff_still_blocks_volume_and_restores_prices(self):
        result = build_channel_input(**fixture(127))
        self.assertEqual(result['price_rows'][0]['nominal_close'], 200)
        self.assertEqual(result['liquidity']['status'], 'BLOCKED_VOLUME_UNIT_UNKNOWN')

    def test_partition_never_crosses_unmodelled_event(self):
        result = build_channel_input(**fixture(0, 'BEFORE_PARTITION_UNMODELLED', 0))
        self.assertEqual(len(result['price_returns']), 126)
        with self.assertRaises(ValueError):
            build_channel_input(**fixture(1, 'BEFORE_PARTITION_UNMODELLED', 0))
        with self.assertRaises(ValueError):
            build_channel_input(**fixture(None, floor_index=1))

    def test_missing_events_prices_and_duplicate_rows_reject(self):
        original = fixture(40)
        variants = []
        changed = copy.deepcopy(original); changed['event_policy'] = []; variants.append(changed)
        changed = copy.deepcopy(original); changed['quote_rows'].pop(40); variants.append(changed)
        changed = copy.deepcopy(original); changed['quote_rows'].append(changed['quote_rows'][-1]); variants.append(changed)
        changed = copy.deepcopy(original); changed['event_policy'][0]['numerator'] = True; variants.append(changed)
        changed = copy.deepcopy(original); changed['quote_rows'][0]['later_split_effective_sessions'] = []; variants.append(changed)
        for changed in variants:
            with self.assertRaises(ValueError):
                build_channel_input(**changed)


if __name__ == '__main__':
    unittest.main()

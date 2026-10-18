"""Saved JSON in memory only; never decode raw or publish a manifest."""
from copy import deepcopy
import json
import unittest
from scripts import ndx_new_cutoff_completeness_20260923 as m


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.docs={role:json.loads((m.BASE/path).read_bytes()) for role,(path,_) in m.BOUND.items()}

    def test_reference_not_short_listing_intersection(self):
        result=m.assemble(**self.docs);rows={r['ticker']:r for r in result['rows']}
        self.assertEqual(len(result['observed_reference_calendar_127']),127)
        self.assertEqual(result['observed_reference_calendar_127'][0],'2026-03-20')
        self.assertLess(len(result['common_complete_dates_diagnostic_only']),127)
        for ticker,count in (('SPCX',69),('HONA',68)):
            self.assertEqual(rows[ticker]['ohlc_127']['complete_day_count'],count)
            self.assertEqual(len(rows[ticker]['ohlc_127']['missing_dates']),127-count)
            self.assertEqual(rows[ticker]['return_126_use']['numerically_available_ohlc_pairs'],count-1)
        self.assertEqual([r['ticker'] for r in result['rows'][-3:]],['TSM','QQQ','SPY'])

    def test_early_price_gap_cannot_shorten_volume_reference(self):
        docs=deepcopy(self.docs);ticker=docs['readback']['rows'][1]['ticker']
        bars=docs['readback']['rows'][1]['observation']['rows'];missing='2026-03-20'
        bars[:]=[r for r in bars if r['new_york_date']!=missing]
        result=m.assemble(**docs);row=next(r for r in result['rows'] if r['ticker']==ticker)
        self.assertEqual(row['ohlc_127']['complete_day_count'],126)
        self.assertEqual(row['ohlc_127']['missing_dates'],[missing])
        self.assertEqual(row['volume_63']['complete_day_count'],63)
        self.assertEqual(result['observed_volume_calendar_63'][0],'2026-06-23')
        self.assertEqual(row['return_126_use']['missing_pair_count'],1)

    def test_latest_nulls_not_filled_or_claimed_complete(self):
        result=m.assemble(**self.docs)
        for row in result['rows'][:102]:
            self.assertEqual(row['latest_present_date'],'2026-09-22')
            self.assertEqual(row['latest_complete_ohlcv_date'],'2026-09-21')
            self.assertFalse(row['september22']['complete_ohlcv'])
            self.assertIsNone(row['september22']['raw_provider_fields']['close'])
            self.assertIsNone(row['september22']['raw_provider_fields']['adjclose'])
        docs=deepcopy(self.docs);bar=next(r for r in docs['readback']['rows'][0]['observation']['rows'] if r['new_york_date']=='2026-09-22')
        bar['raw_provider_fields']['close']=100;bar['missing_fields'].remove('close')
        with self.assertRaisesRegex(ValueError,'September 22'):m.assemble(**docs)

    def test_field_omission_exclusion_and_role_attacks_fail_closed(self):
        for attack in ('field','exclusion','role','reference_missing'):
            docs=deepcopy(self.docs);bar=docs['readback']['rows'][0]['observation']['rows'][0]
            if attack=='field':del bar['raw_provider_fields']['adjclose']
            if attack=='exclusion':bar['excluded_receipt_day_or_later']=True
            if attack=='role':docs['plan']['queue'][-1]['role']='OBSERVED_MEMBER_PROVIDER_CHANNEL'
            if attack=='reference_missing':docs['plan']['queue'].pop(-1)
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(**docs)


if __name__=='__main__':unittest.main()

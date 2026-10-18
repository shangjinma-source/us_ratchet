import json
import unittest
from backtest import ndx_current_regular_segment_quote_research as module


class Tests(unittest.TestCase):
    def args(self,ticker):
        r=json.loads((module.original.BASE/'current_22_price_capture_20260919_v1'/(ticker+'.receipt.json')).read_bytes())
        return dict(ticker=ticker,raw_path=r['raw_path'],raw_sha256=r['raw_sha256'],calendar=['2026-09-17'],quote_field_basis=module.original.nominal.BASIS)

    def test_real_three_regular_quotes_full_raw_retained_and_globals_unchanged(self):
        before=dict(module.original.PARTITION_REQUIRED)
        for ticker in module.FLOORS:
            with self.subTest(ticker=ticker):
                result=module.reconstruct_regular_segment_quote(**self.args(ticker))
                self.assertGreater(result['pre_regular_provider_date_count'],0)
                self.assertEqual(result['reconstruction']['row_count'],1)
                self.assertFalse(result['raw_rows_deleted_or_rewritten'])
                self.assertFalse(result['price_identity_verified'])
                self.assertFalse(result['historical_full_source_closure_verified'])
                self.assertEqual(result['regular_way_floor'],module.FLOORS[ticker])
                with self.assertRaisesRegex(ValueError,'PARTITION_REQUIRED'):
                    module.original.reconstruct_current_receipt_quote(**self.args(ticker))
        self.assertEqual(module.original.PARTITION_REQUIRED,before)

    def test_cross_floor_not_silently_filtered(self):
        for ticker in module.FLOORS:
            with self.assertRaisesRegex(ValueError,'crosses'):
                module.reconstruct_regular_segment_quote(**dict(self.args(ticker),calendar=['2022-01-03','2026-09-17']))

    def test_outside_scope_and_bad_calendar_basis(self):
        for change in ({'ticker':'TRI'},{'ticker':'WDC'},{'calendar':[]},{'calendar':['2026-09-17']*2},{'calendar':[True]},{'quote_field_basis':'UNKNOWN'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                module.reconstruct_regular_segment_quote(**dict(self.args('HONA'),**change))


if __name__=='__main__':unittest.main()

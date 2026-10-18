from decimal import Decimal
import unittest
from scripts import ndx_latest_avgo_sample_independent_audit_20260919 as m
from test_ndx_latest_avgo_sample_independent_audit_20260919 import fixture,RECEIPT


class Tests(unittest.TestCase):
    def test_nested_return_scope_cannot_authorize_execution_or_training(self):
        for flag in ('execution_price_use_authorized','old_training_reuse_authorized','point_in_time_verified','promotion_allowed',
                     'source_assertions_authenticated','stable_coordinate_authenticity_verified','event_completeness_independently_verified'):
            sample,raw=fixture();sample['numerical']['price_returns'][flag]=True
            with self.subTest(flag=flag),self.assertRaises(ValueError):m.inspect(sample,raw,RECEIPT)

    def test_postsplit_volume_cannot_be_multiplied_again_by_ten(self):
        sample,raw=fixture();numerical=sample['numerical']
        for row in numerical['liquidity_rows']:
            row['volume_shares']*=10
            row['dollar_volume']=str(Decimal(row['dollar_volume'])*10)
        numerical['median_dollar_volume_usd']=str(Decimal(numerical['median_dollar_volume_usd'])*10)
        with self.assertRaises(ValueError):m.inspect(sample,raw,RECEIPT)


if __name__=='__main__':unittest.main()

import copy
import unittest
from scripts import ndx_latest_cdns_input_sample_20260919 as m
from test_ndx_latest_cdns_input_sample_20260919 import fixture


class ReviewTests(unittest.TestCase):
    def test_nested_scope_ratio_count_and_basis_cannot_upgrade(self):
        args,_,_=fixture();value=m.calculate(**args)
        changes=[lambda v:v.update(liquidity_legality_or_corporate_action_unit_independently_certified=True),
            lambda v:v['price_returns'].update(execution_price_use_authorized=True),
            lambda v:v['price_returns'].update(explicit_event_cell_count=True),
            lambda v:v['price_returns'].update(event_completeness_independently_verified=True),
            lambda v:v['input_payload']['daily_share_ratios'][0].update(new_shares=True),
            lambda v:v['input_payload'].update(basis='SPLIT_ADJUSTED_CLOSE')]
        for change in changes:
            result=copy.deepcopy(value);change(result)
            with self.subTest(change=change),self.assertRaises(ValueError):m.validate_numerical(result)

    def test_reported_independent_error_is_finite_nonnegative_bounded(self):
        args,_,_=fixture();value=m.calculate(**args)
        for error in ('NaN','Infinity','-0.001','0.01'):
            result=copy.deepcopy(value);result['independent_decimal_return_max_error']=error
            with self.subTest(error=error),self.assertRaises(ValueError):m.validate_numerical(result)


if __name__=='__main__':unittest.main()

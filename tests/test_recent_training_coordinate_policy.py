"""Focused safeguards for price coordinates versus actual share actions."""
from fractions import Fraction
import unittest
from scripts.prepare_recent_training_windows import reviewed_coordinate_event

class CoordinatePolicyTests(unittest.TestCase):
    def test_mtch_factor_never_changes_nominal_scale(self):
        review=reviewed_coordinate_event('MTCH','2020-07-01',Fraction('3.502'))
        self.assertFalse(review['apply_nominal_scale'])
        self.assertTrue(review['training_allowed'])
        self.assertIn('$3',review['limitation'])

    def test_no_blanket_complex_event_admission(self):
        for ticker,day,factor in [('EXC','2022-02-03','1.402'),('MTCH','2020-07-01','3.501'),('OTHER','2020-07-01','3.502')]:
            self.assertFalse(reviewed_coordinate_event(ticker,day,Fraction(factor))['training_allowed'])

    def test_exc_is_price_coordinate_not_share_split(self):
        review=reviewed_coordinate_event('EXC','2022-02-02',Fraction('1.402'))
        self.assertTrue(review['training_allowed'])
        self.assertTrue(review['apply_nominal_scale'])
        self.assertIn('NOT_TOTAL_RETURN',review['interpretation'])
        self.assertIn('quantity remains unchanged',review['limitation'])

if __name__=='__main__':
    unittest.main()

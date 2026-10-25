import unittest
from fractions import Fraction

from scripts.prepare_recent_execution_prices import coordinate_factor


class CoordinateTests(unittest.TestCase):
    def test_rejected_provider_event_does_not_change_scale(self):
        event = {'date': '2022-01-03', 'factor': '1751/500', 'apply_nominal_scale': False}
        anchor = {'date': '2021-12-31', 'factor': '1'}
        self.assertEqual(coordinate_factor(anchor, [event], '2022-01-04'), 1)

    def test_split_boundary_and_inverse_from_later_anchor(self):
        events = [{'date': '2022-06-23', 'factor': '5'}]
        before = {'date': '2021-12-31', 'factor': '5'}
        after = {'date': '2022-12-30', 'factor': '1'}
        for anchor in (before, after):
            self.assertEqual(coordinate_factor(anchor, events, '2022-06-22'), 5)
            self.assertEqual(coordinate_factor(anchor, events, '2022-06-23'), 1)

    def test_reverse_and_complex_coordinates_remain_rational(self):
        events = [{'date': '2023-02-01', 'factor': '1/10'},
                  {'date': '2023-03-01', 'factor': '1067/1000'}]
        anchor = {'date': '2023-04-01', 'factor': '1'}
        self.assertEqual(coordinate_factor(anchor, events, '2023-01-31'), Fraction(1067, 10000))
        self.assertEqual(coordinate_factor(anchor, events, '2023-02-01'), Fraction(1067, 1000))


if __name__ == '__main__':
    unittest.main()

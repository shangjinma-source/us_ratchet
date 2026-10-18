"""Independent exact-value and representation checks; no actual selection IO."""
from copy import deepcopy
from fractions import Fraction
import unittest

from backtest import ndx_cash_neighbor_combined_stream_selection_v2_research as pure
from scripts import ndx_cash_neighbor_combined_selection_independent_readback_v2_20261008 as reader


class Tests(unittest.TestCase):
    def test_cross_representation_exact_and_no_mutation(self):
        for numerator in (0, 1, 2**53 + 1, 10**120 + 17):
            for denominator in (1, 7, 10**111 + 3):
                for n in (numerator, str(numerator)):
                    for d in (denominator, str(denominator)):
                        saved = dict(numerator=n, denominator=d)
                        original = deepcopy(saved)
                        for module in (pure, reader):
                            self.assertEqual(module.ratio(saved), Fraction(numerator, denominator))
                            self.assertEqual(saved, original)
                            self.assertIs(type(saved['numerator']), type(n))
                            self.assertIs(type(saved['denominator']), type(d))

    def test_both_independent_parsers_reject_noncanonical_atoms(self):
        for bad in ('1\n', '\t1', '\u00a01', '00', '٠', '𝟙', '1_000',
                    '+0', '-0', True, False, 1.0, None, [], {}):
            for field in ('numerator', 'denominator'):
                for module in (pure, reader):
                    saved = dict(numerator=1, denominator=2)
                    saved[field] = bad
                    with self.subTest(module=module.__name__, field=field, bad=bad):
                        with self.assertRaises(ValueError):
                            module.ratio(saved)
        for module in (pure, reader):
            for saved in ({'numerator': 1, 'denominator': 2, 'extra': 0},
                          {'numerator': 1}, {'numerator': '0', 'denominator': '0'}):
                with self.assertRaises(ValueError):
                    module.ratio(saved)


if __name__ == '__main__':
    unittest.main()

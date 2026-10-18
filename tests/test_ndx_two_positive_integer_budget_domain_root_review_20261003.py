"""Independent closed forms and exact boundaries, without production counting."""
from fractions import Fraction
import unittest

from backtest.ndx_two_positive_integer_budget_domain_research import (
    count_points, page_points, rank_point, unrank_point,
)


class RootClosedFormReview(unittest.TestCase):
    def test_huge_equal_cost_triangle_and_last_ten_points(self):
        size = 10**60 + 7
        arguments = dict(a=Fraction(7, 13), b=Fraction(7, 13),
                         budget=Fraction(7 * size, 13))
        total = size * (size - 1) // 2
        self.assertEqual(count_points(**arguments), total)
        self.assertEqual(unrank_point(**arguments, rank=0), (1, 1))
        self.assertEqual(unrank_point(**arguments, rank=total - 1), (size - 1, 1))
        expected = [(first, second) for first in range(size - 4, size)
                    for second in range(1, size - first + 1)]
        page = page_points(**arguments, start=total - 10, limit=10)
        self.assertEqual(page, dict(schema='EXACT_TWO_POSITIVE_INTEGER_BUDGET_PAGE_V1',
            order='Q1_ASCENDING_THEN_Q2_ASCENDING', total_count=total, start=total - 10,
            stop=total, rows=[dict(rank=total - 10 + index, q1=first, q2=second)
                             for index, (first, second) in enumerate(expected)],
            returned_count=10, empty_domain=False, has_more=False,
            full_domain_truncated=False, economic_policy_registered=False,
            risk_evaluated=False, account_executed=False))
        for index, (first, second) in enumerate(expected):
            self.assertEqual(rank_point(**arguments, q1=first, q2=second),
                             total - 10 + index)

    def test_huge_unequal_cost_closed_form_and_transpose(self):
        size = 10**45 + 21
        total = size * size * (size - 1) // 2
        arguments = dict(a=1, b=size, budget=size * size)
        self.assertEqual(count_points(**arguments), total)
        self.assertEqual(count_points(a=size, b=1, budget=size * size), total)
        self.assertEqual(unrank_point(**arguments, rank=size - 2), (1, size - 1))
        self.assertEqual(unrank_point(**arguments, rank=size - 1), (2, 1))
        self.assertEqual(unrank_point(**arguments, rank=total - 1),
                         (size * size - size, 1))
        self.assertEqual(rank_point(**arguments, q1=size * size - size, q2=1),
                         total - 1)
        with self.assertRaises(ValueError):
            rank_point(**arguments, q1=size * size - size + 1, q2=1)

    def test_tiny_rational_margin_is_not_rounded_into_a_point(self):
        first, second = Fraction(1, 7), Fraction(2, 11)
        threshold = first + second
        self.assertEqual(count_points(a=first, b=second, budget=threshold), 1)
        self.assertEqual(count_points(a=first, b=second,
                                     budget=threshold - Fraction(1, 10**90)), 0)
        self.assertEqual(count_points(a=first, b=second, budget=-threshold), 0)
        with self.assertRaises(ValueError):
            unrank_point(a=first, b=second,
                         budget=threshold - Fraction(1, 10**90), rank=0)


if __name__ == '__main__':
    unittest.main()

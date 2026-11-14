import unittest
from scripts.research.reserved_limit_reference_replay import execute


def session(fill_minute=None):
    data = dict(o=[100]*390, c=[100]*390, h=[101]*390, l=[100]*390, v=[1]*390)
    if fill_minute is not None:
        data['l'][fill_minute] = 99
    return dict(data=data)


class ReservationsTests(unittest.TestCase):
    def test_unfilled_order_keeps_reservation(self):
        cash, fills, unfilled = execute(100, {}, {'AAA': 1, 'BBB': 1}, {'AAA': session(), 'BBB': session(60)}, 0, start=60, policy='OPEN')
        self.assertEqual(cash, 100)
        self.assertEqual(fills, [])
        self.assertEqual(unfilled[1]['reason'], 'NO_CASH_AT_SUBMISSION')

    def test_fill_order_does_not_choose_who_gets_capital(self):
        held = {}
        cash, fills, _ = execute(100, held, {'AAA': 1, 'BBB': 1}, {'AAA': session(200), 'BBB': session(60)}, 0, start=60, policy='OPEN')
        self.assertEqual(held, {'AAA': 1})
        self.assertEqual(fills[0]['minute'], 200)

    def test_later_sale_not_spendable_at_submission(self):
        held = {'ZZZ': 1}
        cash, fills, _ = execute(0, held, {'AAA': 1}, {'AAA': session(61), 'ZZZ': session()}, 0, start=60, policy='OPEN')
        self.assertEqual(held.get('AAA', 0), 0)
        self.assertEqual(cash, 100)


if __name__ == '__main__':
    unittest.main()

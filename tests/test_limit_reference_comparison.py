import unittest
from scripts.research.limit_reference_comparison import simulate


class LimitReferenceTests(unittest.TestCase):
    def test_high_buy_limit_can_fill_below_limit(self):
        data = dict(o=[100]*390, c=[90]*390, h=[91]*390, l=[89]*390, v=[1]*390)
        data['o'][60] = 89.5
        old = simulate(data, 'BUY', 60, 'OPEN')
        new = simulate(data, 'BUY', 60, 'LATEST_COMPLETED')
        self.assertEqual(old['limit'], 100)
        self.assertEqual(new['limit'], 90)
        self.assertEqual(old['fill']['price'], new['fill']['price'])

    def test_future_low_does_not_set_reference_or_fill_early(self):
        data = dict(o=[100]*390, c=[100]*390, h=[101]*390, l=[100]*390, v=[1]*390)
        data['l'][59] = 80
        data['l'][200] = 85
        result = simulate(data, 'BUY', 60, 'LATEST_COMPLETED')
        self.assertEqual(result['limit'], 100)
        self.assertEqual(result['fill']['minute'], 200)


if __name__ == '__main__':
    unittest.main()

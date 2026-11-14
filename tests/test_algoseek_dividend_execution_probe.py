import unittest
from scripts.research.algoseek_dividend_execution_probe import accrue, pay, replay


class DividendTimingTests(unittest.TestCase):
    def test_entitlement_uses_pretrade_holdings_and_is_not_spendable(self):
        event = dict(event_id='one', security_id='research:security:aapl', ex_date='2021-02-05',
                     payment_date='2021-02-11', amount_per_share='41/200', withholding_rate='0')
        holdings, pending = {'AAPL': 10}, []
        accrue([event], '2021-02-05', holdings, pending)
        holdings['AAPL'] = 0
        self.assertAlmostEqual(pending[0]['amount'], 2.05)
        self.assertEqual(pay('2021-02-10', pending), 0)
        self.assertAlmostEqual(pay('2021-02-11', pending), 2.05)
        self.assertEqual(pay('2021-02-11', pending), 0)

    def test_ex_date_purchase_does_not_receive_dividend(self):
        event = dict(event_id='one', security_id='research:security:aapl', ex_date='2021-02-05',
                     payment_date='2021-02-11', amount_per_share='41/200', withholding_rate='0')
        pending = []
        accrue([event], '2021-02-05', {}, pending)
        self.assertEqual(pay('2021-02-11', pending), 0)

    def test_replay_preserves_entitlement_after_sale(self):
        days = ['2021-02-04', '2021-02-05', '2021-02-08']
        target = {days[0]: {'AAPL': 1}, days[1]: {}}
        prices = {'AAPL': {'checked': {side: {'arms': [dict(name='OPEN_REFERENCE', fill=dict(minute=1, price=100))]}
                                        for side in ('BUY', 'SELL')}}}
        sessions = {day: prices for day in target}
        marks = {day: {'AAPL': {'price': 100}} for day in days}
        original = {day: {'shares': {'research:security:aapl': 1} if index == 0 else {}} for index, day in enumerate(days)}
        event = dict(event_id='one', security_id='research:security:aapl', ex_date=days[1],
                     payment_date=days[2], amount_per_share='1', withholding_rate='0')
        result = replay(days, target, sessions, marks, original, [event], 'OPEN_REFERENCE', 'OPEN_REFERENCE', 0, 200)
        self.assertEqual(result['ledger'][1]['cash'], 200)
        self.assertEqual(result['ledger'][1]['dividend_receivable'], 1)
        self.assertEqual(result['ledger'][2]['cash'], 201)
        self.assertEqual(result['ending_dividend_receivable'], 0)


if __name__ == '__main__':
    unittest.main()

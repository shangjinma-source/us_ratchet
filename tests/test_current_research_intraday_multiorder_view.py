from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
import json
import unittest

import test_current_research_intraday_retarget_continuation_chain as fixtures
from data.current_research_intraday_multiorder_view import compact_multiorder_account


class MultiorderViewTests(unittest.TestCase):
    def test_original_sell_and_buy_are_distinct_and_sources_are_omitted(self):
        helper = fixtures.ChainTests()
        envelope, evidence, now = helper.fixture()
        original = deepcopy(envelope)
        view = compact_multiorder_account(envelope)
        self.assertEqual(view['cash'], '16300')
        self.assertEqual(view['recorded_buy_notional'], '6700')
        self.assertEqual(view['recorded_sell_notional'], '3000')
        self.assertEqual({e['side'] for e in view['events'] if e['kind']=='FILL'}, {'BUY', 'SELL'})
        self.assertFalse(view['price_is_current_quote'])
        self.assertNotIn('files', json.dumps(view))
        self.assertNotIn('execution_evidence', json.dumps(view))
        self.assertEqual(envelope, original)

    def test_repeated_orders_and_fees_keep_cumulative_cash_identity(self):
        helper = fixtures.ChainTests()
        envelope, evidence, now = helper.fixture()
        t = now + timedelta(minutes=1)
        evidence = helper.append_quote(evidence, t, 39, 38)
        chain, _, _ = helper.accept(envelope, evidence, t, 'view-cycle-1')
        t += timedelta(seconds=1)
        chain, _ = helper.event(chain, 'FILL', t, quantity=100, price='37', fees='1', executed_at=t.isoformat())
        t += timedelta(seconds=1)
        chain, _ = helper.event(chain, 'CANCEL', t, cancelled_at=t.isoformat())
        t = now + timedelta(minutes=2)
        evidence = helper.append_quote(evidence, t, 50, 49)
        chain, _, _ = helper.accept(chain, evidence, t, 'view-cycle-2')
        before = deepcopy(chain)
        view = compact_multiorder_account(chain)
        self.assertEqual(view['cash'], '12599')
        self.assertEqual(view['fees'], '1')
        self.assertEqual(view['recorded_buy_notional'], '10400')
        self.assertEqual(view['recorded_sell_notional'], '3000')
        self.assertEqual(Fraction(view['available_cash']), Fraction('1009'))
        self.assertEqual(view['orders'][0]['quantity'], 305)
        self.assertEqual(view['orders'][0]['limit_price'], '38')
        self.assertEqual(view['orders'][0]['status'], 'OPEN')
        self.assertFalse(view['orders'][0]['price_is_current_quote'])
        self.assertEqual(next(p for p in view['positions'] if p['security_id']=='new')['quantity'], 200)
        self.assertEqual(chain, before)
        corrupt = deepcopy(chain)
        corrupt['ledger']['cash'] = '20000'
        with self.assertRaises(ValueError):
            compact_multiorder_account(corrupt)


if __name__ == '__main__':
    unittest.main()

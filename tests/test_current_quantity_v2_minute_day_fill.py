from copy import deepcopy
import unittest
from backtest.current_quantity_v2_minute_day_fill import evaluate, MODEL


def fixture():
    def bar(minute, low='10', high='11'):
        return dict(start=f'2026-10-14T19:{minute:02}:00+00:00',end=f'2026-10-14T19:{minute+1:02}:00+00:00',open='10',close='10',low=low,high=high)
    return dict(model=MODEL,order=dict(order_id='order',side='BUY',quantity=3,filled_quantity=0,closed=None,limit_price='10',
            accepted_at='2026-10-14T19:57:30+00:00',session_close='2026-10-14T20:00:00+00:00'),
            minutes=[bar(57,'9'),bar(58)],observed_through='2026-10-14T20:00:00+00:00',
            evaluated_at='2026-10-14T20:00:00+00:00',
            fees='0.25',available_cash='100',available_shares=3,event_id='sim1',expected_revision='r1')


class MinuteFillTests(unittest.TestCase):
    def test_before_acceptance_and_missing_minute_are_not_fills(self):
        args=fixture(); result=evaluate(**args)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertIsNone(result['event_proposal'])
        args['minutes']=[dict(start='2026-10-14T19:59:00+00:00',end='2026-10-14T20:00:00+00:00',open='10',close='10',low='9',high='11')]
        self.assertEqual(evaluate(**args)['reason'],'MISSING_MINUTE_BEFORE_OUTCOME')

    def test_exact_touch_expires_only_with_complete_day(self):
        args=fixture(); last=deepcopy(args['minutes'][-1]); last.update(start='2026-10-14T19:59:00+00:00',end='2026-10-14T20:00:00+00:00')
        args['minutes'].append(last)
        self.assertEqual(evaluate(**args)['status'],'EXPIRE')
        args['observed_through']='2026-10-14T19:59:59+00:00'
        self.assertEqual(evaluate(**args)['status'],'UNKNOWN')

    def test_buy_sell_exact_money_and_no_resource_assumption(self):
        args=fixture(); args['minutes'][-1]['low']='9.99'
        result=evaluate(**args)
        self.assertEqual(result['status'],'SIMULATED_FILL'); self.assertEqual(result['cash_change'],'-121/4')
        self.assertEqual(result['event_proposal']['price'],'10')
        args['available_cash']='30'
        self.assertEqual(evaluate(**args)['status'],'UNKNOWN')
        args['order']['side']='SELL'; args['order']['limit_price']='10.5'; args['available_cash']='0'
        self.assertEqual(evaluate(**args)['cash_change'],'125/4')
        args['available_shares']=2
        self.assertEqual(evaluate(**args)['status'],'UNKNOWN')

    def test_future_and_invalid_minutes(self):
        args=fixture(); args['evaluated_at']='2026-10-14T19:59:59+00:00'
        self.assertEqual(evaluate(**args)['reason'],'FUTURE_OBSERVATION_BOUNDARY')
        args=fixture(); args['minutes'][-1]['low']='9'; args['observed_through']='2026-10-14T19:58:59+00:00'
        self.assertEqual(evaluate(**args)['status'],'UNKNOWN')
        args['minutes'].append(deepcopy(args['minutes'][-1]))
        with self.assertRaises(ValueError): evaluate(**args)

    def test_partial_closed_orders_rejected_and_ledger_event_fields(self):
        args=fixture(); args['minutes'][-1]['low']='9'; args['order']['filled_quantity']=2
        with self.assertRaisesRegex(ValueError,'PARTIALLY_FILLED'): evaluate(**args)
        args['order']['filled_quantity']=0
        result=evaluate(**args)
        self.assertEqual(result['event_proposal']['quantity'],3)
        self.assertEqual(set(result['event_proposal']),{'type','event_id','expected_revision','order_id','quantity','price','fees','executed_at','recorded_at'})
        self.assertEqual(result['event_proposal']['type'],'FILL')
        args['order']['closed']='CANCELLED'
        with self.assertRaisesRegex(ValueError,'ORDER_CLOSED'): evaluate(**args)

    def test_real_ledger_apply_fill_fee_and_expiry(self):
        from data.current_quantity_v2_paper_ledger import apply, reserves
        def state(args):
            order=dict(args['order'],security_id='sid:A')
            value=dict(orders={'order':order},revision='r1',cash='100',shares={'sid:A':3},
                       recorded_fees='0',events=[],last_recorded_at=order['accepted_at'],last_effective_at=order['accepted_at'])
            reserves(value)
            return value
        args=fixture(); args['minutes'][-1]['low']='9'
        # Explicit early close: the final minute's synthetic effective time is < close.
        args['order']['session_close']='2026-10-14T19:59:00+00:00'
        result=evaluate(**args); ledger=apply(state(args),result['event_proposal'])
        self.assertEqual(ledger['cash'],'279/4'); self.assertEqual(ledger['shares']['sid:A'],6)
        self.assertEqual(ledger['recorded_fees'],'1/4'); self.assertEqual(ledger['reserved_cash'],'0')
        args['minutes'][-1]['low']='10'
        result=evaluate(**args); self.assertEqual(result['status'],'EXPIRE')
        ledger=apply(state(args),result['event_proposal'])
        self.assertEqual(ledger['orders']['order']['closed'],'EXPIRED')
        self.assertEqual(ledger['cash'],'100'); self.assertEqual(ledger['shares']['sid:A'],3)


if __name__=='__main__': unittest.main()

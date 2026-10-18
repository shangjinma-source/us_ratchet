import unittest
from copy import deepcopy
from core.strategy_account_difference import build_strategy_difference


def fixture():
    return dict(account_id='strategy',account_revision=3,holdings_revision=2,cash_confirmed_for_holdings_revision=2,
        cash_balance='100',cash_basis='TOTAL_UNINVESTED',strategy_shares={'A':4},legacy_shares={'A':100},pending_orders=[],
        marks={'A':dict(security_id='A',currency='USD',price_basis='current',observed_at='2026-10-16T14:00:00Z',price='10')},
        limits={'A':dict(security_id='A',price_basis='current',observed_at='2026-10-16T14:00:00Z',buy='10',sell='10')},
        target_quantities={'A':10},now='2026-10-16T14:00:30Z',maximum_mark_age_seconds=60,fee_bps='0')


def pending(side='BUY',quantity=5,filled=2):
    return dict(account_id='strategy',scope='STRATEGY',order_id='o1',security_id='A',side=side,
        quantity=quantity,filled_quantity=filled,remaining_quantity=quantity-filled,limit_price='10',
        reserved_cash=str((quantity-filled)*10) if side=='BUY' else '0',remaining_fee_reserve='0')


class StrategyDifferenceTests(unittest.TestCase):
    def test_sell_only_placeholder_cannot_be_used_for_buy(self):
        args=fixture();args['limits']['A']['buy_evaluated']=False
        with self.assertRaisesRegex(ValueError,'BUY_LIMIT_NOT_EVALUATED'):
            build_strategy_difference(**args)
        args['target_quantities']={}
        result=build_strategy_difference(**args)
        self.assertEqual(result['new_orders'][0]['side'],'SELL')
        self.assertEqual(result['new_orders'][0]['quantity'],4)

    def test_legacy_same_sid_excluded_and_manual_cash_is_replacement(self):
        args=fixture();original=deepcopy(args);first=build_strategy_difference(**args)
        self.assertEqual(first['strategy_equity'],'140');self.assertEqual(first['new_orders'][0]['quantity'],6)
        self.assertEqual(args,original)
        args['cash_balance']='20';second=build_strategy_difference(**args)
        self.assertEqual(second['strategy_equity'],'60');self.assertEqual(second['new_orders'][0]['quantity'],2)
        self.assertEqual(second['status'],'WAIT_CASH');self.assertEqual(second['binding']['account_revision'],3)
        args['target_quantities']={};third=build_strategy_difference(**args)
        self.assertEqual(third['new_orders'][0]['quantity'],4) # never sell legacy 100

    def test_cash_bases_equivalent_partial_fill_remaining_reserved_once(self):
        args=fixture();args['pending_orders']=[pending()]
        total=build_strategy_difference(**args)
        args['cash_basis']='AVAILABLE_AFTER_RESERVATIONS';args['cash_balance']='70'
        available=build_strategy_difference(**args)
        for key in ('strategy_equity','spendable_cash','new_orders','pending_buy_reserved_cash'):
            self.assertEqual(total[key],available[key])
        self.assertEqual(total['new_orders'][0]['quantity'],3) # target10-held4-pending3
        self.assertEqual(total['new_buy_cash_required'],'30')

    def test_reverse_and_excess_pending_requires_cancel(self):
        for order,target in [(pending(),3),(pending(),6),(pending('SELL',3,0),6)]:
            args=fixture();args['pending_orders']=[order];args['target_quantities']={'A':target}
            result=build_strategy_difference(**args)
            self.assertEqual(result['status'],'CANCEL_THEN_RECALCULATE');self.assertEqual(result['new_orders'],[])

    def test_sell_pending_does_not_fund_buys_zero_cash_valid(self):
        args=fixture();args['cash_balance']='0';args['pending_orders']=[pending('SELL',2,0)];args['target_quantities']={'A':0,'B':5}
        args['marks']['B']=dict(args['marks']['A'],security_id='B');args['limits']['B']=dict(args['limits']['A'],security_id='B')
        result=build_strategy_difference(**args)
        self.assertEqual(result['strategy_equity'],'40');self.assertEqual(result['status'],'WAIT_CASH')
        self.assertEqual([(o['side'],o['quantity']) for o in result['new_orders']],[('SELL',2)])
        self.assertEqual(result['new_buy_cash_required'],'0')

    def test_stale_cash_marks_and_invalid_reserves_rejected(self):
        for kind in ('cash','mark','future','reserve','missing_reserve','oversell','basis'):
            args=fixture()
            if kind=='cash':args['cash_confirmed_for_holdings_revision']=1
            if kind=='mark':args['marks']['A']['observed_at']='2026-10-15T14:00:00Z'
            if kind=='future':args['marks']['A']['observed_at']='2026-10-16T15:00:00Z'
            if kind in ('reserve','missing_reserve'):
                args['pending_orders']=[pending()]
                if kind=='reserve':args['pending_orders'][0]['reserved_cash']='29'
                else:args['pending_orders'][0].pop('reserved_cash')
            if kind=='oversell':args['pending_orders']=[pending('SELL',7,0)]
            if kind=='basis':args['cash_basis']='UNSPECIFIED'
            with self.subTest(kind=kind),self.assertRaises((ValueError,KeyError)):build_strategy_difference(**args)

    def test_fee_buffer_and_multiple_buys_do_not_exceed_cash(self):
        args=fixture();args['strategy_shares']={};args['cash_balance']='21';args['fee_bps']='1000';args['target_quantities']={'A':2,'B':2}
        args['marks']['B']=dict(args['marks']['A'],security_id='B');args['limits']['B']=dict(args['limits']['A'],security_id='B')
        result=build_strategy_difference(**args)
        self.assertEqual(result['new_orders'],[]);self.assertEqual(result['status'],'WAIT_CASH')
        args['cash_balance']='22';result=build_strategy_difference(**args)
        self.assertEqual(result['new_buy_cash_required'],'22');self.assertEqual([o['quantity'] for o in result['new_orders']],[1,1])


if __name__=='__main__':unittest.main()

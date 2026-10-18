from copy import deepcopy
from fractions import Fraction
import unittest
from backtest import return_priority_paper_continuous_book_research as subject


def fixture():
    calendar=['2026-10-09','2026-10-12','2026-10-13']
    return dict(calendar=calendar,open_prices={day:dict(A=100,B=50) for day in calendar},
        close_prices={day:dict(A=100,B=50) for day in calendar},
        metadata=dict(A=dict(ticker='A',issuer_id='IA',risk_chain='CA'),B=dict(ticker='B',issuer_id='IB',risk_chain='CB')),
        initial_shares=dict(A=10),initial_cash=1000,fee_bps=10,minimum_cash_buffer=100,
        decisions=[dict(id='switch',decision_date='2026-10-09',target_shares=dict(B=30))],cash_events=[],
        risk_parameters=dict(max_single_weight=.45,min_single_weight=.05,top_three_cap=.8,min_neff_ratio=.7,chain_cap=.55),
        enforce_initial_target_risk=False,declared_price_basis='CONDITIONAL_OHLC_NOT_CERTIFIED')


class PaperBook(unittest.TestCase):
    def test_next_common_open_sell_then_buy_two_fees_cash_and_continuity(self):
        result=subject.simulate_paper_book(**fixture());execution=result['executions'][0]
        self.assertEqual(result['daily_rows'][0]['shares'],dict(A=10))
        self.assertEqual(execution['execution_date'],'2026-10-12')
        self.assertEqual(execution['decision_date'],'2026-10-09')
        self.assertEqual(execution['sells'],dict(A=10))
        self.assertEqual(execution['buys'],dict(B=30))
        self.assertEqual(Fraction(execution['sell_fee']),1)
        self.assertEqual(Fraction(execution['buy_fee']),Fraction(3,2))
        self.assertEqual(Fraction(execution['cash_after_sells']),1999)
        self.assertEqual(Fraction(result['final_cash']),Fraction(995,2))
        self.assertEqual(Fraction(result['daily_rows'][-1]['close_equity']),Fraction(3995,2))
        self.assertEqual(result['final_shares'],dict(B=30))

    def test_weight_floor_fee_reserve_and_once_only_flow_not_a_pool_discount(self):
        data=fixture();data['initial_shares']={};data['initial_cash']=1000
        data['decisions']=[dict(id='weights',decision_date='2026-10-09',target_weights=dict(A='1/2',B='1/4'))]
        data['cash_events']=[dict(id='newcash',session='2026-10-12',amount=1000)]
        result=subject.simulate_paper_book(**data);execution=result['executions'][0]
        self.assertEqual(Fraction(execution['weight_sizing_capacity']),1896)
        self.assertEqual(result['final_shares'],dict(A=9,B=9))
        self.assertEqual(Fraction(result['final_cash']),Fraction(12973,20))
        self.assertEqual(result['consumed_cash_event_ids'],['newcash'])
        self.assertEqual(Fraction(result['daily_rows'][-1]['close_equity']),Fraction(39973,20))
        self.assertEqual(Fraction(result['daily_rows'][-1]['cumulative_time_weighted_return']),Fraction(-27,40000))
        data['cash_events'].append(deepcopy(data['cash_events'][0]))
        with self.assertRaises(ValueError):subject.simulate_paper_book(**data)

    def test_unaffordable_fixed_shares_atomic_and_positive_missing_open_block(self):
        data=fixture();data['decisions'][0]['target_shares']={'B':50}
        result=subject.simulate_paper_book(**data)
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(result['final_shares'],dict(A=10))
        self.assertEqual(Fraction(result['final_cash']),1000)
        self.assertEqual(result['executions'][0]['status'],'BLOCKED_ATOMIC_NO_TRADES_COMMITTED')
        data=fixture();data['open_prices']['2026-10-12']['B']=None
        result=subject.simulate_paper_book(**data)
        self.assertEqual(result['reason'],'NEXT_OBSERVED_OPEN_OR_HELD_POSITION_MARK_MISSING')
        self.assertEqual(result['final_shares'],dict(A=10))

    def test_future_prices_do_not_change_earlier_rows_and_last_decision_remains_pending(self):
        data=fixture();original=subject.simulate_paper_book(**data)
        data['close_prices']['2026-10-13']['B']=500
        mutated=subject.simulate_paper_book(**data)
        self.assertEqual(original['daily_rows'][:2],mutated['daily_rows'][:2])
        self.assertEqual(original['executions'],mutated['executions'])
        data=fixture();data['decisions']=[dict(id='late',decision_date='2026-10-13',target_shares=dict(B=30))]
        result=subject.simulate_paper_book(**data)
        self.assertEqual(result['status'],'PENDING_NEXT_OBSERVATION_OPEN')
        self.assertEqual(result['executions'],[])


if __name__=='__main__':unittest.main()

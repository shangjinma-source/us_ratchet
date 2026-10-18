import unittest
from copy import deepcopy
from datetime import date,timedelta
from fractions import Fraction
from scripts.return_priority_fixed12_comparison import construct_books,frozen_weights
from backtest.return_priority_holding_entitlement_outcome import frozen_holding_with_entitlements


def fixture():
    dates=[(date(2024,1,15)+timedelta(days=i)).isoformat() for i in range(22)]
    args=dict(prices={'a':'100','b':'150'},metadata={'a':dict(ticker='A',issuer_id='ia'),'b':dict(ticker='B',issuer_id='ib')},
        training_scenarios=[{'a':'1','b':'11/10'} for _ in range(12)],scenario_dates=[f'2024-01-{i:02}' for i in range(1,13)],
        entered_cash='20000',fee_bps='0',minimum_cash_buffer='0',decision_date=dates[0])
    outcome=dict(nominal_prices={'a':{d:dict(open='200',close='210') for d in dates[1:]}},metadata=args['metadata'],
        session_dates=dates,decision_date=dates[0],end_date=dates[-1],entered_cash='20000',fee_bps='0')
    holding=dict(outcome_arguments_without_target_weights=outcome,price_gaps=[dict(security_id='b',reason='synthetic missing winner')],
        qqq_reference=dict(outcome_arguments=dict(outcome,target_weights={'a':'1'}),missing_dates=[]))
    selected=dict(quantities={'a':100},actual_weights={'a':'1/2'},notional='10000',residual_cash='10000',fees='0',actual_k=1)
    return dict(decision_cutoff=dates[0],search_arguments=args),holding,selected


class Fixed12ComparisonTests(unittest.TestCase):
    def test_frozen_weight_uses_cash_budget_and_next_open(self):
        t,h,s=fixture();books=construct_books(t,h,s)
        outcome=frozen_holding_with_entitlements(**books[0]['outcome_arguments'])
        self.assertEqual(outcome['initial_shares'],{'a':50})
        self.assertEqual(Fraction(outcome['cash']),10000)
        self.assertEqual(Fraction(outcome['equity']),20500)

    def test_missing_winning_future_source_never_substitutes(self):
        t,h,s=fixture();before=deepcopy(h);books=construct_books(t,h,s)
        self.assertEqual(books[1]['frozen_selection']['security_id'],'b')
        self.assertEqual(books[1]['outcome_arguments']['target_weights'],{'b':'399/400'})
        self.assertEqual(h,before)

    def test_exact_tie_sid_order_and_cash_selection(self):
        t,h,s=fixture()
        t['search_arguments']['training_scenarios']=[{'a':'1','b':'1'} for _ in range(12)]
        cash=dict(quantities={},actual_weights={},notional='0',residual_cash='20000',fees='0',actual_k=0)
        books=construct_books(t,h,cash)
        self.assertEqual(books[1]['frozen_selection']['security_id'],'a')
        self.assertEqual(books[0]['outcome_arguments']['target_weights'],{})
        outcome=frozen_holding_with_entitlements(**books[0]['outcome_arguments'])
        self.assertEqual(outcome['status'],'COMPLETE')
        self.assertEqual(Fraction(outcome['equity']),20000)

    def test_tampered_weights_or_cash_rejected(self):
        t,h,s=fixture();s['actual_weights']['a']='1'
        with self.assertRaises(ValueError):frozen_weights(t['search_arguments'],s)
        t,h,s=fixture();s['residual_cash']='10001'
        with self.assertRaises(ValueError):frozen_weights(t['search_arguments'],s)


if __name__=='__main__':unittest.main()

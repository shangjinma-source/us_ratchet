import unittest
from unittest.mock import patch
from backtest.return_priority_monthly_top1_provider import build_monthly_top1_provider
from backtest.return_priority_monthly_top1_selector import VERSION


class Top1ProviderTests(unittest.TestCase):
    def make(self):
        days=['2025-12-31','2026-01-01','2026-01-02']
        args=dict(prices={'A':'10','B':'30'},metadata={'A':dict(ticker='AAA',issuer_id='I'),'B':dict(ticker='BBB',issuer_id='J')},
            training_scenarios=[{'A':'1.1','B':'1.2'} for _ in range(12)],
            scenario_dates=[f'2025-{m:02d}-01' for m in range(1,13)],decision_date=days[0],
            entered_cash='20000',fee_bps=0,minimum_cash_buffer=0,quote_as_of=days[0],price_basis='UNIT')
        quotes=[dict(security_id=s,price=p,as_of=days[0],price_basis='UNIT',source_references=['raw']) for s,p in args['prices'].items()]
        provider=build_monthly_top1_provider(session_dates=days,monthly_inputs=[dict(decision_date=days[0],search_arguments=args,valuation_quotes=quotes,
            source_hashes={'raw':'a'*64,'backtest/return_priority_fresh_cash_quantity_search.py':'b'*64,'backtest/return_priority_monthly_top1_selector.py':'c'*64})],
            close_prices={s:{d:p for d in days} for s,p in args['prices'].items()})
        return provider,days

    def test_monthly_one_daily_zero_and_correct_method(self):
        p,d=self.make()
        first=p(decision_date=d[0],active_date=d[1],state=dict(asof=d[0],cash='100',shares={}))
        daily=p(decision_date=d[1],active_date=d[2],state=dict(asof=d[1],cash='10',shares={'B':3}))
        self.assertEqual(first['target_shares'],{'B':3})
        self.assertEqual((first['selector_calls'],daily['selector_calls']),(1,0))
        self.assertEqual((first['capital_decision_attempts'],daily['capital_decision_attempts']),(1,0))
        for result in [first,daily]:
            self.assertEqual(result['method'],VERSION)
            self.assertEqual(result['core_calls'],0)
            self.assertEqual(result['total_capital_decision_attempts'],1)
        self.assertEqual(daily['orders'],[])

    def test_failed_attempt_unknown_selector_count_no_orders_or_retry(self):
        p,d=self.make();args=dict(decision_date=d[0],active_date=d[1],state=dict(asof=d[0],cash='100',shares={}))
        with patch('backtest.return_priority_monthly_top1_provider.decide_top1_for_account',side_effect=ValueError('synthetic failure')) as called:
            failed=p(**args);again=p(**args)
        called.assert_called_once()
        self.assertEqual(failed['status'],'BLOCKED');self.assertEqual(failed['orders'],[])
        self.assertEqual(failed['capital_decision_attempts'],1);self.assertIsNone(failed['selector_calls'])
        self.assertEqual(again['selector_calls'],0);self.assertEqual(again['capital_decision_attempts'],0)
        self.assertEqual(again['orders'],[]);self.assertEqual(failed['core_calls'],0)
        self.assertEqual(failed['method'],VERSION)


if __name__=='__main__':unittest.main()

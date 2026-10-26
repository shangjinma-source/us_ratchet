import unittest
from fractions import Fraction
from unittest.mock import patch
from backtest.historical_dividend_identity_independent_review_v1 import review


class IdentityLiquidationTests(unittest.TestCase):
    def fixture(self):
        action=dict(type='split_identity', date='2024-10-01',security_id='old',new_security_id='new',new_shares='10',old_shares='1',source_references=['official'])
        order=dict(id='sell',side='SELL',security_id='old',quantity=1,active_date='2024-10-01',decision_mark='100')
        row=dict(date='2024-10-01',cash='100',shares={'old':0,'new':0},stock_value='0',equity='100')
        book=dict(status='COMPLETE',daily_ledger=[row],provider_audit=[dict(orders=[order],selection={})],fee_bps='0',slippage_bps='0',cash='100',shares=row['shares'],fees='0',receivable='0',total_return='0',drawdown={'maximum_close_drawdown':'0'})
        assembled=dict(session_dates=['2024-09-30','2024-10-01'],actions=[action],provider_actions=[action],close_prices={'old':{'2024-09-30':'100'}},monthly_inputs=[])
        return dict(book=book,assembled=assembled,bars={'new':{'2024-10-01':dict(open='10',close='10')}},initial_cash='0',initial_shares={'old':1},dividend_events=[],verify_selections=False,expected_fee_bps='0',expected_slippage_bps='0')

    def run_case(self, case, target=None):
        with patch('backtest.historical_dividend_identity_independent_review_v1.review_selection',return_value={'target_quantities':target or {}}):
            return review(**case)

    def test_integer_full_liquidation(self):
        self.assertEqual(self.run_case(self.fixture())['integer_identity_liquidations_checked'],1)

    def test_wrong_cash_rejected(self):
        case=self.fixture();case['book']['daily_ledger'][0]['cash']='10'
        with self.assertRaisesRegex(ValueError,'CASH_SHARES'):self.run_case(case)

    def test_old_position_not_cleared_rejected(self):
        case=self.fixture();case['book']['daily_ledger'][0]['shares']={'old':1,'new':0}
        with self.assertRaisesRegex(ValueError,'CASH_SHARES'):self.run_case(case)

    def test_retained_target_rejected(self):
        with self.assertRaisesRegex(ValueError,'IDENTITY_FULL_LIQUIDATION_ONLY'):self.run_case(self.fixture(),{'old':1})

    def test_fractional_holding_rejected(self):
        case=self.fixture();case['assembled']['actions'][0]['new_shares']='1';case['assembled']['actions'][0]['old_shares']='10'
        with self.assertRaisesRegex(ValueError,'FRACTIONAL_SPLIT_HOLDING'):self.run_case(case)

    def test_same_sid_identity_rejected(self):
        case=self.fixture();case['assembled']['actions'][0]['new_security_id']='old'
        with self.assertRaisesRegex(ValueError,'IDENTITY_SUCCESSOR'):self.run_case(case)

    def test_terminated_successor_rejected(self):
        from copy import deepcopy
        case=self.fixture();book=case['book'];domain=case['assembled']
        case['initial_shares']['third']=1
        domain['close_prices']['third']={'2024-09-30':'100'}
        domain['session_dates'].append('2024-10-02')
        event=dict(type='split_identity',date='2024-10-02',security_id='third',new_security_id='old',new_shares='1',old_shares='1',source_references=['official'])
        domain['actions'].append(event);domain['provider_actions'].append(event)
        # Fixture lists initially share event objects but not the lists.
        row=book['daily_ledger'][0];row['shares']=dict(old=0,new=0,third=1);row['stock_value']='100';row['equity']='200'
        book['daily_ledger'].append(dict(row,date='2024-10-02'))
        case['bars']['third']={'2024-10-01':dict(open='100',close='100')}
        order=dict(id='second',side='SELL',security_id='third',quantity=1,active_date='2024-10-02',decision_mark='100')
        book['provider_audit'].append(dict(orders=[order],selection={}))
        with self.assertRaisesRegex(ValueError,'TERMINATED_SUCCESSOR'):self.run_case(case)

    def test_real_kernel_provider_and_risk_five_bp(self):
        from backtest.historical_dividend_frontier_research import run_frontier_capped_next_open
        from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
        from backtest.historical_dividend_identity_independent_review_v1 import _review_risk_orders
        days=['2024-09-27','2024-09-30','2024-10-01']
        event=self.fixture()['assembled']['actions'][0]
        bars={'old':{d:dict(open='100',high='100',low='100',close='100') for d in days[:2]},
              'new':{days[2]:dict(open='10',high='10',low='10',close='10')}}
        plans=[dict(decision_date=d,active_date=days[i+1],search_arguments={'fee_bps':'0'},
                    valuation_quotes=[dict(security_id='old',price='100')],source_hashes={}) for i,d in enumerate(days[:2])]
        assembled=dict(session_dates=days,monthly_inputs=plans,close_prices={'old':{d:'100' for d in days[:2]},'new':{days[2]:'10'}},
            actions=[event],provider_actions=[event],cash_stock_merger_events=[],distribution_events=[],fractional_settlements={},price_source_references={},distribution_fractional_cash_values={})
        # Only the economic selector is deterministic synthetic input. Provider,
        # MonthlyExitCoreResearchAdapter and next-open execution are real code.
        def select(**args):
            account=args['account_state']
            equity=Fraction(account['cash'])+sum(account['shares'].values())*100
            return dict(target_quantities={'old':1} if args['decision_date']==days[0] else {},investable_equity=str(equity))
        with patch('backtest.historical_dividend_frontier_research.decide_continuous_guided_for_account',side_effect=select),patch('backtest.historical_dividend_frontier_research.rerank',side_effect=lambda value:value):
            book=run_frontier_capped_next_open(assembled=assembled,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='5',risk=MonthlyExitCoreResearchAdapter([event]),max_new_searches=2)
        self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
        self.assertEqual(Fraction(book['cash']),Fraction('999.9'))
        state=dict(baseline=None,peaks={},exited=set(),month=None)
        for i,audit in enumerate(book['provider_audit']):
            _review_risk_orders(audit,days[i],days[i+1],{} if i==0 else {'old':1},assembled['close_prices'],[event],{'old':1} if i==0 else {},state)
        with patch('backtest.historical_dividend_identity_independent_review_v1.review_selection',side_effect=lambda selected,**kwargs:dict(target_quantities=selected['target_quantities'])):
            proof=review(book,assembled,bars,initial_cash='1000',dividend_events=[],verify_selections=False,expected_fee_bps='0',expected_slippage_bps='5')
        self.assertEqual(proof['integer_identity_liquidations_checked'],1)


if __name__=='__main__':unittest.main()

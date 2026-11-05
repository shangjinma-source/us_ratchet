import unittest
from fractions import Fraction as F
from unittest.mock import patch
from docs.candidates import qqq_risk_budget_account_runner as runner
from docs.candidates.momentum_action_bridge_20261105 import ActionRisk, build_provider, require_cash_merger_settlement_evidence


class IntegrationTests(unittest.TestCase):
    def replay(self, kind):
        days = ['2024-09-27','2024-09-30','2024-10-01','2024-10-02','2024-10-03']
        event = dict(type=kind,date=days[2],security_id='A',source_references=['fixture-official'])
        successor = 'B' if kind == 'split_identity' else 'A'
        if kind == 'merger': event['share_cash']='229'
        else: event.update(old_shares=1,new_shares=10)
        if kind == 'split_identity': event['new_security_id']='B'
        prices = {'A':{days[0]:'100',days[1]:'100'},'C':dict.fromkeys(days,'10')}
        if kind != 'merger': prices.setdefault(successor,{}).update({days[2]:'10',days[3]:'8',days[4]:'8'})
        bars = {s:{d:dict(open=p,high=p,low=p,close=p) for d,p in ps.items()} for s,ps in prices.items()}
        plans=[dict(decision_date=days[0],search_arguments={'fee_bps':'0'},
                    valuation_quotes=[dict(security_id=s,price=prices[s][days[0]]) for s in ('A','C')],source_hashes={})]
        assembled=dict(session_dates=days,monthly_inputs=plans,close_prices=prices,
                       actions=[event],provider_actions=[event],cash_stock_merger_events=[],fractional_settlements=None,
                       price_source_references={},distribution_events=[],distribution_fractional_cash_values=None)
        def select(**kw):
            account=kw['account_state']
            return dict(target_quantities={'A':2,'C':1},investable_equity=account['cash'])
        risk=ActionRisk([event])
        with patch.object(runner,'build_cost_monthly_quantity_provider',side_effect=build_provider), \
             patch.object(runner,'decide_continuous_guided_for_account',side_effect=select), \
             patch.object(runner,'rerank',side_effect=lambda x:x):
            book=runner.run_frontier_capped_next_open(assembled=assembled,ohlc=bars,initial_cash='1000',
                                                     fee_bps='0',slippage_bps='5',risk=risk,max_new_searches=1)
        return book,risk,event

    def test_same_sid_split_real_book_then_exit(self):
        book,risk,_=self.replay('split')
        self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
        self.assertEqual(book['daily_ledger'][2]['shares']['A'],20)
        self.assertEqual(book['daily_ledger'][-1]['shares']['A'],0)
        self.assertIn('A',risk.state['exited'])

    def test_identity_split_real_book_then_new_sid_exit_and_lock(self):
        book,risk,event=self.replay('split_identity')
        self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
        self.assertEqual(book['daily_ledger'][2]['shares']['B'],20)
        self.assertEqual(book['daily_ledger'][-1]['shares']['B'],0)
        self.assertNotIn('A',risk.state['peaks'])
        self.assertIn('B',risk.state['exited'])
        # A pre-existing exit is also migrated, not reset by the split.
        locked=ActionRisk([event])
        locked.apply(day='2024-09-27',month='2024-09-27',target={'A':2},closes={'A':'100'})
        locked.apply(day='2024-09-30',month='2024-09-27',target={'A':2},closes={'A':'80'})
        target,_=locked.apply(day='2024-10-01',month='2024-09-27',target={'B':20},closes={'B':'12'},
                             adjustments=[dict(date='2024-10-01',security_id='A',new_security_id='B')])
        self.assertEqual(target,{'B':0})

    def test_merger_terminates_orders_risk_and_preserves_unavailable_cash(self):
        book,risk,event=self.replay('merger')
        self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
        last=book['daily_ledger'][-1]
        self.assertEqual(last['shares']['A'],0)
        self.assertEqual(F(last['receivable']),458)
        self.assertEqual(F(last['cash']),F(book['daily_ledger'][1]['cash']))
        self.assertEqual(set(risk.state['peaks']),{'C'})
        with self.assertRaisesRegex(ValueError,'AVAILABLE_DATE_AND_RELEASE_NOT_VERIFIED'):
            require_cash_merger_settlement_evidence([event])


if __name__ == '__main__': unittest.main()

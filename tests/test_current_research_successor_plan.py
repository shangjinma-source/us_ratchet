from copy import deepcopy
import unittest

from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_fill_ledger import initialize_paper_ledger, apply_paper_fill, activate_paper_plan
from data.current_research_successor_plan import build_research_successor_plan


class SuccessorTests(unittest.TestCase):
    def setUp(self):
        plan=build_current_research_limit_plan(research_snapshot=dict(research_id='a'*24,as_of='2026-10-13',stocks=[dict(security_id='X',ticker='XXX')],source_hashes={'q':'b'*64}),
            quotes=[dict(security_id='X',price='50',as_of='2026-10-13',price_kind='DECLARED_DECIMAL_REFERENCE',price_basis='UNIT',source_references=['q'])],
            available_cash='100',shares={},account_revision='initial',decision_date='2026-10-13',active_date='2026-10-14',
            calendar=['2026-10-13','2026-10-14'],strategy_version='old',target_quantities={'X':2})
        self.initial=initialize_paper_ledger(plan,'account')
        self.state=apply_paper_fill(self.initial,dict(event_id='f',mode='PAPER_MANUAL_FILL',plan_id=plan['plan_id'],order_id=plan['orders'][0]['order_id'],qty=2,price='50',fees='0',session='2026-10-14',expected_revision=self.initial['revision']))
        self.args=dict(prices={'B':'20'},metadata={'B':dict(ticker='BBB',issuer_id='IB')},entered_cash='20000',fee_bps='0',minimum_cash_buffer='0',training_scenarios=[{'B':'1.2'}],scenario_dates=['2026-10-14'],decision_date='2026-10-14',max_objective_evaluations=12,fixed_seed='fixed',quote_as_of='2026-10-14',price_basis='UNIT')
        self.quotes=[dict(security_id=s,price=p,as_of='2026-10-14',price_basis='UNIT',source_references=['q']) for s,p in [('B','20'),('X','50')]]
        self.continuity={'X':dict(from_date='2026-10-13',to_date='2026-10-14',price_basis='UNIT',status='NO_UNPROCESSED_ACTIONS',source_references=['q'])}
        self.pins={'q':'b'*64,'backtest/return_priority_fresh_cash_quantity_search.py':'c'*64}
        self.calls=[]

    def stub(self,**args):
        self.calls.append(args)
        return dict(decision_date=args['decision_date'],entered_cash=args['entered_cash'],status='BUDGET_STOPPED',selected=dict(quantities={'B':5},actual_k=1,notional='100',fees='0',residual_cash='0',actual_weights={'B':'1'}))

    def build(self,state=None):
        return build_research_successor_plan(self.state if state is None else state,expected_revision=(self.state if state is None else state)['revision'],decision_date='2026-10-14',active_date='2026-10-15',calendar=['2026-10-14','2026-10-15'],valuation_quotes=self.quotes,search_arguments=self.args,source_hashes=self.pins,held_unit_continuity=self.continuity,search=self.stub)

    def test_exit_outside_pool_waits_for_cash_and_activation_preserves_history(self):
        before=deepcopy(self.state);result=self.build();plan=result['plan']
        self.assertEqual(plan['target_quantities'],{'B':5})
        self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in plan['orders']],[('X','SELL',2)])
        self.assertEqual(plan['wait_cash'][0]['remaining_deficit'],5)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(set(self.calls[0]['prices']),{'B'})
        activated=activate_paper_plan(self.state,plan,dict(event_id='activate',mode='PAPER_MANUAL_FILL',event_type='ACTIVATE_PLAN',plan_id=plan['plan_id'],expected_revision=self.state['revision']))
        self.assertEqual(activated['cash'],self.state['cash'])
        self.assertEqual(activated['shares'],{'X':2})
        self.assertEqual(len(activated['plans']),2)
        self.assertEqual(activated['events'][0],self.state['events'][0])
        self.assertEqual(self.state,before)

    def test_stale_revision_cannot_activate_and_untrusted_capital_not_input(self):
        plan=self.build()['plan']
        with self.assertRaises(ValueError):
            activate_paper_plan(self.state,plan,dict(event_id='activate',mode='PAPER_MANUAL_FILL',event_type='ACTIVATE_PLAN',plan_id=plan['plan_id'],expected_revision='stale'))
        with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_REVISION'):
            build_research_successor_plan(self.state,expected_revision='stale',decision_date='2026-10-14',active_date='2026-10-15',calendar=['2026-10-14','2026-10-15'],valuation_quotes=self.quotes,search_arguments=self.args,source_hashes=self.pins,held_unit_continuity=self.continuity,search=self.stub)
        altered=deepcopy(self.state);altered['revision']='stale'
        self.calls=[]
        with self.assertRaises(ValueError):self.build(altered)
        self.assertEqual(self.calls,[])

    def test_nonterminating_decimal_and_open_orders_rejected_before_search(self):
        self.quotes[0]['price']='1/3'
        with self.assertRaisesRegex(ValueError,'NONTERMINATING'):self.build()
        self.assertEqual(self.calls,[])
        self.quotes[0]['price']='20'
        with self.assertRaisesRegex(ValueError,'OPEN_ORDERS'):self.build(self.initial)
        self.assertEqual(self.calls,[])

    def test_stale_price_rejected_without_search(self):
        self.quotes[1]['as_of']='2026-10-13'
        with self.assertRaises(ValueError):self.build()
        self.assertEqual(self.calls,[])

    def test_identity_units_commission_and_continuity_block_before_core(self):
        def same_domain_wrong_ticker():
            self.args['prices']['X']='50'
            self.args['metadata']['X']=dict(ticker='WRONG',issuer_id='IX')
            self.args['training_scenarios'][0]['X']='1.1'
        changes=[same_domain_wrong_ticker,
                 lambda:self.quotes[1].update(price_basis='NEW_UNIT'),
                 lambda:self.args.update(fee_bps='1'),
                 lambda:self.continuity.clear(),
                 lambda:self.continuity['X'].update(source_references=['unknown']),
                 lambda:self.continuity['X'].update(status='ASSUMED')]
        for change in changes:
            self.setUp();change()
            with self.assertRaises(ValueError):self.build()
            self.assertEqual(self.calls,[])

    def test_real_tiny_core_sell_then_later_buy_without_cash_injection(self):
        # Only one synthetic candidate, twelve evaluations per explicit decision.
        original = deepcopy(self.state)
        first = build_research_successor_plan(self.state, expected_revision=self.state['revision'],
            decision_date='2026-10-14', active_date='2026-10-15',
            calendar=['2026-10-14','2026-10-15'], valuation_quotes=self.quotes,
            search_arguments=self.args, source_hashes=self.pins,held_unit_continuity=self.continuity)
        self.assertEqual(first['capital_decision']['investable_equity'],'100')
        self.assertEqual(first['plan']['target_quantities'],{'B':5})
        self.assertEqual([(o['side'],o['security_id']) for o in first['plan']['orders']],[('SELL','X')])
        def activate(state, plan, identifier):
            return activate_paper_plan(state,plan,dict(event_id=identifier,mode='PAPER_MANUAL_FILL',
                event_type='ACTIVATE_PLAN',plan_id=plan['plan_id'],expected_revision=state['revision']))
        def fill(state, quantity, price, identifier):
            plan=state['plan'];order=plan['orders'][0]
            return apply_paper_fill(state,dict(event_id=identifier,mode='PAPER_MANUAL_FILL',
                plan_id=plan['plan_id'],order_id=order['order_id'],qty=quantity,price=price,fees='0',
                session=order['active_date'],expected_revision=state['revision']))
        active=activate(self.state,first['plan'],'activate-sell')
        self.assertEqual(active['cash'],'0')
        sold=fill(active,2,'50','sell-x')
        self.assertEqual(sold['cash'],'100')
        self.assertEqual(sold['shares'].get('X',0),0)
        args=deepcopy(self.args)
        args.update(decision_date='2026-10-15',quote_as_of='2026-10-15',scenario_dates=['2026-10-15'])
        quotes=[dict(q,as_of='2026-10-15') for q in self.quotes]
        second=build_research_successor_plan(sold,expected_revision=sold['revision'],
            decision_date='2026-10-15',active_date='2026-10-16',calendar=['2026-10-15','2026-10-16'],
            valuation_quotes=quotes,search_arguments=args,source_hashes=self.pins,held_unit_continuity=self.continuity)
        self.assertEqual(second['capital_decision']['investable_equity'],'100')
        self.assertEqual(second['plan']['target_quantities'],{'B':5})
        self.assertEqual([(o['side'],o['security_id'],o['quantity']) for o in second['plan']['orders']],[('BUY','B',5)])
        final=fill(activate(sold,second['plan'],'activate-buy'),5,'20','buy-b')
        self.assertEqual(final['cash'],'0')
        self.assertEqual({s:q for s,q in final['shares'].items() if q},{'B':5})
        self.assertEqual(len(final['plans']),3)
        self.assertEqual([e['event_id'] for e in final['events']],['f','activate-sell','sell-x','activate-buy','buy-b'])
        self.assertEqual(self.state,original)


if __name__=='__main__':unittest.main()

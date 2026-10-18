from copy import deepcopy
from fractions import Fraction
import unittest

from data.current_research_capital_decision import decide_quantity_for_account


class CapitalDecisionTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.args = dict(prices={'A':'10','B':'20'},metadata={'A':{'ticker':'AAA','issuer_id':'IA'},'B':{'ticker':'BBB','issuer_id':'IB'}},
            entered_cash='20000',fee_bps='0',minimum_cash_buffer='0',training_scenarios=[{'A':'1.1','B':'1.2'}],
            scenario_dates=['2026-10-13'],decision_date='2026-10-13',max_objective_evaluations=8192,fixed_seed='fixed',
            quote_as_of='2026-10-13',price_basis='CURRENT_SHARE_USD')
        self.state = dict(asof='2026-10-13',revision='r1',cash='100',shares={},reserved_cash='0')
        self.quotes = [dict(security_id=s,price=p,as_of='2026-10-13',price_basis='CURRENT_SHARE_USD',source_references=['quote']) for s,p in [('A','10'),('B','20'),('X','50')]]
        self.pins = {'quote':'a'*64,'backtest/return_priority_fresh_cash_quantity_search.py':'b'*64}

    def stub(self, **args):
        self.calls.append(deepcopy(args))
        quantities = {'A':7} if args['entered_cash']=='100' else {'B':8}
        notional = sum(Fraction(args['prices'][s])*q for s,q in quantities.items())
        fees = notional*Fraction(args['fee_bps'])/10000
        return dict(decision_date=args['decision_date'], entered_cash=args['entered_cash'],
            status='BUDGET_STOPPED', selected=dict(quantities=quantities, actual_k=len(quantities),
            notional=str(notional), fees=str(fees), residual_cash=str(Fraction(args['entered_cash'])-notional-fees),
            actual_weights={s:str(Fraction(args['prices'][s])*q/Fraction(args['entered_cash'])) for s,q in quantities.items()}))

    def run_adapter(self):
        return decide_quantity_for_account(decision_date='2026-10-13',account_state=self.state,
            valuation_quotes=self.quotes,search_arguments=self.args,source_hashes=self.pins,search=self.stub)

    def test_equity_changes_support_and_no_old_weight_scaling(self):
        before=deepcopy(self.args)
        first=self.run_adapter()
        self.state['cash']='200';second=self.run_adapter()
        self.assertEqual(first['target_quantities'],{'A':7})
        self.assertEqual(second['target_quantities'],{'B':8})
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.args,before)
        sent=deepcopy(self.args);sent.pop('price_basis');sent.pop('quote_as_of');sent['entered_cash']='200'
        self.assertEqual(self.calls[-1],sent)

    def test_outside_holding_only_marks_equity_not_domain(self):
        self.state.update(cash='0',shares={'X':2})
        first=self.run_adapter()
        self.assertEqual(first['available_cash'],'0')
        self.assertEqual(first['investable_equity'],'100')
        self.assertEqual(set(self.calls[-1]['prices']),{'A','B'})
        self.state.update(cash='100',shares={},revision='r2')
        second=self.run_adapter()
        self.assertEqual(first['target_quantities'],second['target_quantities'])
        self.assertNotEqual(first['research_id'],second['research_id'])

    def test_invalid_capital_or_quote_rejected_before_core(self):
        cases=[lambda:setattr(self,'state',dict(self.state,cash='0')),
               lambda:self.state.update(shares={'A':True}),
               lambda:self.state.update(reserved_cash='1'),
               lambda:self.state.update(shares={'MISSING':1}),
               lambda:self.quotes[0].update(as_of='2026-10-12'),
               lambda:self.quotes[0].update(price='11'),
               lambda:self.quotes[0].update(price_basis='OTHER_UNIT'),
               lambda:self.args['training_scenarios'][0].pop('B')]
        for mutate in cases:
            self.setUp();mutate()
            with self.assertRaises(ValueError):self.run_adapter()
            self.assertEqual(self.calls,[])

    def test_deterministic_binding_and_source_revision_changes(self):
        first=self.run_adapter();again=self.run_adapter()
        self.assertEqual(first['research_id'],again['research_id'])
        self.assertRegex(first['research_id'], r'^[0-9a-f]{24}$')
        self.assertRegex(first['decision_id'], r'^[0-9a-f]{64}$')
        self.assertEqual(first['research_id'], first['decision_id'][:24])
        self.pins['quote']='c'*64
        changed=self.run_adapter()
        self.assertNotEqual(first['research_id'],changed['research_id'])
        self.state['revision']='new'
        self.assertNotEqual(changed['research_id'],self.run_adapter()['research_id'])

    def test_real_core_on_tiny_synthetic_universe_conserves_marked_equity(self):
        from fractions import Fraction
        self.state.update(cash='20', shares={'X':2})
        self.args['max_objective_evaluations'] = 12
        result = decide_quantity_for_account(decision_date='2026-10-13',
            account_state=self.state, valuation_quotes=self.quotes,
            search_arguments=self.args, source_hashes=self.pins)
        self.assertEqual(result['available_cash'], '20')
        self.assertEqual(result['investable_equity'], '120')
        selected = result['search_result']['selected']
        self.assertEqual(Fraction(selected['notional']) + Fraction(selected['fees'])
                         + Fraction(selected['residual_cash']), Fraction(120))
        self.assertTrue(set(result['target_quantities']) <= {'A', 'B'})
        self.assertEqual(result['target_quantities'], selected['quantities'])
        self.assertEqual(result['core_calls'], 1)

    def test_real_core_all_cash_below_buffer_is_still_valid(self):
        self.args['minimum_cash_buffer'] = '101'
        self.args['max_objective_evaluations'] = 12
        result = decide_quantity_for_account(decision_date='2026-10-13',
            account_state=self.state, valuation_quotes=self.quotes,
            search_arguments=self.args, source_hashes=self.pins)
        self.assertEqual(result['target_quantities'], {})
        self.assertEqual(result['search_result']['selected']['residual_cash'], '100')

    def test_hostile_core_outputs_rejected(self):
        mutations = [lambda r:r.update(decision_date='2026-10-12'),
            lambda r:r.update(entered_cash='101'), lambda r:r.update(status='SYNTHETIC'),
            lambda r:r['selected'].update(quantities={'X':1}),
            lambda r:r['selected'].update(quantities={'A':True}),
            lambda r:r['selected'].update(quantities={'A':11}),
            lambda r:r['selected'].update(notional='1'),
            lambda r:r['selected'].update(fees='1'),
            lambda r:r['selected'].update(residual_cash='31'),
            lambda r:r['selected'].update(actual_k=True),
            lambda r:r['selected'].update(actual_weights={'A':'1'}),
            lambda r:r.update(selected=None)]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                def bad(**args):
                    result=self.stub(**args);mutation(result);return result
                with self.assertRaises(ValueError):
                    decide_quantity_for_account(decision_date='2026-10-13',account_state=self.state,
                        valuation_quotes=self.quotes,search_arguments=self.args,source_hashes=self.pins,search=bad)

    def test_none_allcash_and_same_issuer_or_buffer(self):
        def none(**args):
            return dict(decision_date=args['decision_date'],entered_cash=args['entered_cash'],
                        status='INSUFFICIENT_BUDGET_FOR_ALL_K_INITIALIZATION',selected=None)
        def call(search):
            return decide_quantity_for_account(decision_date='2026-10-13',account_state=self.state,
                valuation_quotes=self.quotes,search_arguments=self.args,source_hashes=self.pins,search=search)
        self.assertIsNone(call(none)['target_quantities'])
        def cash(**args):
            return dict(decision_date=args['decision_date'],entered_cash=args['entered_cash'],status='LOCAL_NEIGHBORHOODS_EXHAUSTED',
                selected=dict(quantities={},actual_k=0,notional='0',fees='0',residual_cash=args['entered_cash'],actual_weights={}))
        self.assertEqual(call(cash)['target_quantities'],{})
        self.args['minimum_cash_buffer']='31'
        with self.assertRaises(ValueError):call(self.stub)
        self.args['minimum_cash_buffer']='0'
        self.args['metadata']['B']['issuer_id']='IA'
        def duplicate(**args):
            result=self.stub(**args);result['selected']['quantities']={'A':1,'B':1};return result
        with self.assertRaises(ValueError):call(duplicate)


if __name__=='__main__':unittest.main()

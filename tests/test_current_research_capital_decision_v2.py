from copy import deepcopy
import unittest

from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account, REQUIRED_PINS, VERSION


class CapitalV2Tests(unittest.TestCase):
    def arguments(self):
        day='2026-10-13'
        return dict(decision_date=day,
            account_state=dict(asof=day,revision='synthetic',cash='100',shares={},reserved_cash='0'),
            valuation_quotes=[dict(security_id=s,as_of=day,price=p,price_basis='SYNTHETIC_USD',source_references=['quote'])
                              for s,p in [('A','1'),('X','50')]],
            source_hashes={p:'a'*64 for p in (*REQUIRED_PINS,'quote','backtest/return_priority_fresh_cash_quantity_search.py')},
            search_arguments=dict(decision_date=day,quote_as_of=day,price_basis='SYNTHETIC_USD',
                prices={'A':'1'},metadata={'A':{'ticker':'AAA','issuer_id':'IA'}},entered_cash='999',
                fee_bps='0',minimum_cash_buffer='0',training_scenarios=[{'A':'2'},{'A':'1/2'}],
                scenario_dates=['2026-09-30',day],max_objective_evaluations=128,fixed_seed='synthetic'))

    def test_real_v2_interior_optimum_and_cash_rebinding(self):
        args=self.arguments();before=deepcopy(args)
        result=decide_quantity_v2_for_account(**args)
        self.assertEqual(result['target_quantities'],{'A':50})
        self.assertEqual(result['investable_equity'],'100')
        self.assertEqual(result['method'],VERSION)
        self.assertEqual(result['search_result']['status'],'PER_K_SEARCH_STOPPED_WITH_UNUSED_BUDGET')
        self.assertEqual(args,before)
        args['account_state']['cash']='200'
        changed=decide_quantity_v2_for_account(**args)
        self.assertEqual(changed['target_quantities'],{'A':100})
        self.assertNotEqual(changed['research_id'],result['research_id'])

    def test_outside_holding_only_values_equity(self):
        args=self.arguments();args['account_state'].update(cash='0',shares={'X':2})
        result=decide_quantity_v2_for_account(**args)
        self.assertEqual(result['target_quantities'],{'A':50})
        self.assertEqual(result['available_cash'],'0')
        self.assertEqual(set(result['binding']['search_arguments']['prices']),{'A'})

    def test_insufficient_budget_remains_unselected(self):
        args=self.arguments();args['search_arguments']['max_objective_evaluations']=1
        result=decide_quantity_v2_for_account(**args)
        self.assertIsNone(result['target_quantities'])
        self.assertEqual(result['search_result']['status'],'INSUFFICIENT_BUDGET_FOR_MANDATORY_COVERAGE')
        self.assertEqual(result['search_result']['objective_evaluations'],0)

    def test_missing_pin_rejected(self):
        args=self.arguments();del args['source_hashes'][REQUIRED_PINS[-1]]
        with self.assertRaisesRegex(ValueError,'SOURCE_PINS_REQUIRED'):
            decide_quantity_v2_for_account(**args)

    def test_v4_execution_keeps_unsettled_sales_out_of_buy_cash(self):
        from backtest.return_priority_monthly_quantity_provider_v4 import build_monthly_quantity_provider_v4
        args=self.arguments();days=['2026-10-13','2026-10-14']
        provider=build_monthly_quantity_provider_v4(session_dates=days,
            monthly_inputs=[dict(decision_date=days[0],valuation_quotes=args['valuation_quotes'],
                search_arguments=args['search_arguments'],source_hashes=args['source_hashes'])],
            close_prices={'A':dict.fromkeys(days,'1'),'X':dict.fromkeys(days,'50')},
            decide=decide_quantity_v2_for_account)
        result=provider(decision_date=days[0],active_date=days[1],
            state=dict(asof=days[0],cash='0',shares={'X':2}))
        self.assertEqual(result['status'],'READY')
        self.assertEqual(result['target_shares'],{'A':50})
        self.assertEqual([(o['side'],o['security_id'],o['quantity']) for o in result['orders']],
                         [('SELL','X',2)])
        self.assertEqual(result['wait_cash'][0]['remaining_deficit'],50)
        self.assertEqual(result['selection']['method'],VERSION)

    def test_cash_changes_composition_and_display_preserves_coverage(self):
        from data.current_quantity_projection_v2 import project_capital_decision_v2
        args=self.arguments()
        args['search_arguments'].update(prices={'A':'60','B':'40'},
            metadata={'A':{'ticker':'AAA','issuer_id':'IA'},'B':{'ticker':'BBB','issuer_id':'IB'}},
            training_scenarios=[{'A':'2','B':'1/2'},{'A':'1/2','B':'2'}])
        quote=deepcopy(args['valuation_quotes'][0])
        args['valuation_quotes']=[dict(quote,security_id='A',price='60'),dict(quote,security_id='B',price='40')]
        args['account_state']['cash']='60'
        first=decide_quantity_v2_for_account(**args)
        self.assertEqual(first['target_quantities'],{'B':1})
        args['account_state']['cash']='100'
        second=decide_quantity_v2_for_account(**args)
        self.assertEqual(second['target_quantities'],{'A':1,'B':1})
        view=project_capital_decision_v2(second)
        self.assertEqual(len(view['stocks']),2)
        self.assertEqual(view['search_coverage']['local_search_budget_by_k'],
                         second['search_result']['local_search_budget_by_k'])
        self.assertFalse(view['global_optimum_established'])
        self.assertIsNone(view['executable_buy_quantities'])

    def test_projection_insufficient_budget_and_equity_not_cash(self):
        from data.current_quantity_projection_v2 import project_capital_decision_v2
        args=self.arguments();args['account_state'].update(cash='0',shares={'X':2})
        view=project_capital_decision_v2(decide_quantity_v2_for_account(**args))
        self.assertEqual(view['available_cash_exact'],'0')
        self.assertEqual(view['budget_identity_exact']['entered_cash'],'100')
        self.assertIsNone(view['executable_buy_quantities'])
        args['search_arguments']['max_objective_evaluations']=1
        decision=decide_quantity_v2_for_account(**args)
        view=project_capital_decision_v2(decision)
        self.assertEqual(view['status'],'INCOMPLETE')
        self.assertEqual(view['stocks'],[])
        decision['method']='LEGACY'
        with self.assertRaisesRegex(ValueError,'method binding'):
            project_capital_decision_v2(decision)

    def test_projection_rejects_mixed_snapshot_fields(self):
        from data.current_quantity_projection_v2 import project_capital_decision_v2
        original=decide_quantity_v2_for_account(**self.arguments())
        mutations=[lambda d:d.update(research_id='b'*24),
            lambda d:d.update(decision_id='b'*64),
            lambda d:d.update(available_cash='200'),
            lambda d:d.update(investable_equity='200'),
            lambda d:d.update(target_quantities={'A':49}),
            lambda d:d.update(holding_market_values={'X':'50'}),
            lambda d:d.update(state_revision='other'),
            lambda d:d.update(execution_blocked=False),
            lambda d:d['binding']['search_arguments'].update(entered_cash='200')]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                mixed=deepcopy(original);mutate(mixed)
                with self.assertRaises(ValueError):project_capital_decision_v2(mixed)
        self.assertEqual(project_capital_decision_v2(original)['target_quantities'],{'A':50})


if __name__=='__main__':unittest.main()

import math
import unittest
from backtest import ndx_return_priority_first_candidate_research as subject

POLICY = dict(max_single_weight=.45, min_single_weight=.05, top_three_cap=.8, min_neff_ratio=.7, chain_cap=.55)
SCOPE = 'INITIAL_DEPLOYMENT_DAILY_DIAGNOSTICS_ONLY'


def fixture(n=4):
    securities = [dict(security_id=f'S{i}', issuer_id=f'I{i}', ticker=f'T{i}', risk_chain=f'C{i}') for i in range(n)]
    initial = {f'S{i}': 50. for i in range(n)}
    target = {f'S{i}': 101. for i in range(n)}
    returns = {f'S{i}': [.02, -.01] for i in range(n)}
    return securities, initial, target, returns


class FirstCandidate(unittest.TestCase):
    def test_net_cash_cagr_and_initial_peak_drawdown(self):
        securities, _, _, _ = fixture(2)
        metadata = {row['security_id']: row for row in securities}
        budget = subject.Budget(1, 0)
        result = subject.evaluate_allocation(quantities={'S0':50,'S1':25}, initial_prices={'S0':100.,'S1':200.},
            returns={'S0':[-.5,1.],'S1':[-.4,2/3]}, metadata=metadata, policy=POLICY,
            cash=20000, fee_bps=10, buffer=100, budget=budget, enforce_risk=False, risk_scope=SCOPE)
        self.assertEqual(result['net_wealth_path'], [20000.,19990.,15490.,19990.])
        self.assertEqual(result['reconciliation_total'], 20000)
        self.assertAlmostEqual(result['training_metrics']['maximum_drawdown'], .2255)
        self.assertAlmostEqual(subject.wealth_metrics([20000,19990]+[15490]*125+[19990],126)['cagr'], -.00099975)
        self.assertEqual(budget.objective_calls, 1)

    def test_risk_rules_and_duplicate_issuer(self):
        securities, _, _, _ = fixture()
        metadata = {row['security_id']: row for row in securities}
        self.assertTrue(subject.risk_checks({key:100 for key in metadata}, metadata, POLICY)['all_passed'])
        self.assertFalse(subject.risk_checks(dict(S0=970,S1=10,S2=10,S3=10),metadata,POLICY)['all_passed'])
        metadata['S1']['issuer_id'] = metadata['S0']['issuer_id']
        with self.assertRaises(ValueError):subject.risk_checks({key:100 for key in metadata},metadata,POLICY)

    def test_every_k_has_analytic_or_searched_record_and_target_current_prices(self):
        securities, initial, target, returns = fixture()
        result = subject.run_bounded_search(securities=securities,initial_prices=initial,target_prices=target,returns=returns,
            return_dates=['2026-09-18','2026-09-21'],cutoff='2026-09-21', policy=POLICY,cash=20000,fee_bps=10,buffer=100,
            risk_scope=SCOPE,support_limit=2,per_support_objectives=8,per_support_integers=12,global_objectives=8,global_integers=12)
        self.assertEqual([row['k'] for row in result['per_k_coverage']],[1,2,3,4])
        self.assertTrue(result['co_winners'])
        for candidate in result['co_winners']:
            self.assertEqual(candidate['invested_notional'], sum(candidate['quantities'].values())*101)
            self.assertLessEqual(candidate['invested_notional']+candidate['fees']+100,20000+1e-8)
            self.assertTrue(all(type(q) is int for q in candidate['quantities'].values()))
            self.assertEqual(candidate['hypothetical_training_initial_economic_units']['S0'],candidate['quantities']['S0']*101/50)
        self.assertLessEqual(result['budget']['objective_calls'],8)
        self.assertLessEqual(result['budget']['integer_proposals'],12)

    def test_no_post_cutoff_or_missing_sessions(self):
        securities, initial, _, returns = fixture()
        with self.assertRaises(ValueError):subject.validate_inputs(securities,initial,returns,['2026-09-21','2026-09-22'],'2026-09-21')
        returns['S0'] = [0.]
        with self.assertRaises(ValueError):subject.validate_inputs(securities,initial,returns,['2026-09-18','2026-09-21'],'2026-09-21')

    def test_budget_refuses_before_unregistered_extra_objective(self):
        budget=subject.Budget(0,0)
        with self.assertRaises(subject.BudgetExhausted):budget.objective()
        with self.assertRaises(subject.BudgetExhausted):budget.integer()
        self.assertEqual((budget.objective_calls,budget.integer_proposals),(0,0))
        with self.assertRaises(ValueError):subject.Budget(True,5)

    def test_daily_concentration_is_diagnostic_not_a_hidden_rebalance_gate(self):
        securities, initial, _, _=fixture()
        result=subject.evaluate_allocation(quantities={f'S{i}':1 for i in range(4)},initial_prices=initial,
            returns={f'S{i}':[10. if i==0 else 0.,0.] for i in range(4)},metadata={row['security_id']:row for row in securities},policy=POLICY,
            cash=1000,fee_bps=10,buffer=100,budget=subject.Budget(1,0),enforce_risk=True,risk_scope=SCOPE)
        self.assertTrue(result['feasible'])
        self.assertEqual(result['daily_risk_failed_indices'],[0,1])
        self.assertAlmostEqual(result['net_wealth_path'][-1],1499.8)

    def test_no_arbitrary_cardinality_cap_and_all_class_alternatives_exist(self):
        self.assertEqual(subject.analytic_k_status(21,POLICY),['K_TIMES_MIN_WEIGHT_ABOVE_ONE'])
        securities,_,_,_=fixture()
        securities.append(dict(security_id='S4',issuer_id='I0',ticker='T4',risk_chain='C0'))
        supports=list(subject.supports_for_k(securities,4,8,__import__('random').Random(1)))
        self.assertTrue(any('S0' in support for support in supports))
        self.assertTrue(any('S4' in support for support in supports))
        self.assertTrue(all(not ('S0' in support and 'S4' in support) for support in supports))


if __name__ == '__main__':unittest.main()

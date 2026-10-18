import copy
import itertools
import unittest

from backtest.ndx_integer_allocation_research import search_integer_allocation_domain


def fixture():
    names=['A','B','C','D']
    return dict(prices={t:10. for t in names},target_weights={t:.25 for t in names},
        current_shares={t:0 for t in names},current_cash=100.,transaction_cost_bps=0.,minimum_cash_buffer_usd=0.,
        risk_chain_by_ticker={t:t for t in names},constraints=dict(max_single_weight=.5,min_single_weight=.1,
            top_weight_cap=.9,minimum_effective_n_ratio=.5,risk_chain_top1_cap=.5),
        share_domains={t:[1,2] for t in names},max_evaluations=16)


class IntegerAllocationResearchTests(unittest.TestCase):
    def test_complete_domain_tracking_penalizes_idle_cash(self):
        inputs=fixture();before=copy.deepcopy(inputs)
        result=search_integer_allocation_domain(**inputs)
        self.assertEqual((result['finite_domain_size'],result['evaluated'],result['unexamined']),(16,16,0))
        self.assertTrue(result['pareto_complete_within_explicit_domain'])
        self.assertFalse(result['global_optimality_claim_allowed'])
        self.assertEqual(len(result['pareto']),1)
        best=result['pareto'][0]
        self.assertEqual(best['shares'],{t:2 for t in inputs['prices']})
        self.assertAlmostEqual(best['security_only_tracking_error'],0.)
        self.assertAlmostEqual(best['total_tracking_error_including_cash'],.05)
        self.assertEqual(inputs,before)

    def test_budget_preserves_full_denominator_and_lex_order(self):
        inputs=fixture();inputs['max_evaluations']=1
        partial=search_integer_allocation_domain(**inputs)
        self.assertEqual((partial['finite_domain_size'],partial['evaluated'],partial['unexamined']),(16,1,15))
        self.assertFalse(partial['pareto_complete_within_explicit_domain'])
        self.assertEqual(partial['pareto'][0]['shares'],{t:1 for t in inputs['prices']})
        inputs['share_domains']={t:[2,1] for t in inputs['prices']}
        self.assertEqual(partial,search_integer_allocation_domain(**inputs))

    def test_two_objective_frontier_matches_independent_cartesian_oracle(self):
        inputs=fixture();inputs.update(current_shares={t:1 for t in inputs['prices']},current_cash=60.,transaction_cost_bps=10.)
        actual=search_integer_allocation_domain(**inputs)
        rows=[]
        for vector in itertools.product([1,2],repeat=4):
            invested=10*sum(vector);fees=10*(sum(vector)-4)*.001
            equity=100-fees;cash=equity-invested
            weights=[10*n/invested for n in vector]
            if min(weights)<.1 or max(weights)>.5 or sum(sorted(weights,reverse=True)[:3])>.9:
                continue
            tracking=sum((10*n/equity-.25)**2 for n in vector)+(cash/equity)**2
            rows.append((vector,tracking,fees))
        expected={row[0] for row in rows if not any(other[1]<=row[1] and other[2]<=row[2]
                    and (other[1]<row[1] or other[2]<row[2]) for other in rows)}
        self.assertEqual({tuple(row['shares'].values()) for row in actual['pareto']},expected)
        self.assertIn((1,1,1,1),expected)
        self.assertIn((2,2,2,2),expected)

    def test_sale_cash_and_fee_accounting_and_zero_share_rejection(self):
        inputs=fixture();inputs.update(current_shares={t:2 for t in inputs['prices']},current_cash=0.,transaction_cost_bps=10.,
            share_domains={t:[1] for t in inputs['prices']},max_evaluations=1)
        result=search_integer_allocation_domain(**inputs)['pareto'][0]
        self.assertAlmostEqual(result['sales_usd'],40.)
        self.assertAlmostEqual(result['fees_usd'],.04)
        self.assertAlmostEqual(result['posttrade_cash_usd'],39.96)
        self.assertAlmostEqual(result['posttrade_equity_usd'],79.96)
        inputs['share_domains']={t:[0] for t in inputs['prices']}
        result=search_integer_allocation_domain(**inputs)
        self.assertEqual(result['feasible_evaluated'],0)
        self.assertEqual(result['failure_counts']['MINIMUM_ONE_SHARE'],1)

    def test_invalid_types_domains_and_cash_fail_closed(self):
        mutations=[lambda x:x['prices'].update(A=0),lambda x:x['prices'].update(A=True),
            lambda x:x['current_shares'].update(A=-1),lambda x:x['current_shares'].update(A=1.),
            lambda x:x['share_domains'].update(A=[1,1]),lambda x:x['share_domains'].update(A=[True]),
            lambda x:x.update(current_cash=float('nan')),lambda x:x.update(transaction_cost_bps=True),
            lambda x:x.update(max_evaluations=0),lambda x:x['target_weights'].update(A=.5)]
        for mutation in mutations:
            inputs=fixture();mutation(inputs)
            with self.assertRaises(ValueError):search_integer_allocation_domain(**inputs)


if __name__=='__main__':
    unittest.main()

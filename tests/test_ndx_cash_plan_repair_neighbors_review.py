import itertools
import unittest
from copy import deepcopy
from backtest import ndx_cash_plan_repair_neighbors_research as subject

class RepairReview(unittest.TestCase):
    def test_small_full_domains_and_every_budget_prefix(self):
        for caps in ((0,), (2,), (1,2), (2,1,2)):
            sids = [chr(65+i) for i in range(len(caps))]
            limits = dict(reversed(list(zip(sids,caps))))
            points = list(itertools.product(*(range(c+1) for c in caps)))
            seeds = points[::2]
            excluded = set(points[1::3])
            seen = set(); ordered = []; outside = duplicate = blocked = 0
            # Independent vector-space construction, not production move helpers.
            vectors = [v for v in itertools.product((-1,0,1), repeat=len(caps)) if 1 <= sum(x != 0 for x in v) <= 2]
            vectors.sort(key=lambda v:(sum(x != 0 for x in v),tuple(i for i,x in enumerate(v) if x),tuple(x for x in v if x)))
            for seed_index, seed in enumerate(seeds):
                for move_index, delta in enumerate(vectors):
                    point = tuple(a+b for a,b in zip(seed,delta))
                    if any(q < 0 or q > cap for q,cap in zip(point,caps)): outside += 1; continue
                    if point in seen: duplicate += 1; continue
                    seen.add(point)
                    if point in excluded: blocked += 1; continue
                    ordered.append((point,seed_index,move_index,delta))
            args = dict(buy_limits=limits,seed_plans=[dict(zip(sids,p)) for p in seeds],excluded_plans=[dict(zip(sids,p)) for p in sorted(excluded)])
            original = deepcopy(args)
            for budget in (0,1,3,10000):
                result = subject.generate_repair_neighbors(**args,max_generated_plans=budget)
                self.assertEqual(args,original)
                self.assertEqual(result['out_of_bounds_attempt_count'],outside)
                self.assertEqual(result['duplicate_valid_coordinate_attempt_count'],duplicate)
                self.assertEqual(result['unique_excluded_coordinate_count'],blocked)
                self.assertEqual(result['distinct_remaining_plan_count'],len(ordered))
                self.assertEqual(result['ungenerated_plan_count'],max(0,len(ordered)-budget))
                for got, (point,si,mi,delta) in zip(result['generated_plans'],ordered[:budget]):
                    self.assertEqual(got['buy_shares'],dict(zip(sids,point)))
                    self.assertEqual((got['first_seed_index'],got['first_move_index']),(si,mi))
                    self.assertEqual(got['first_move_deltas'],{s:x for s,x in zip(sids,delta) if x})
                self.assertEqual(len(result['generated_plans']),len(ordered[:budget]))
                for flag in ('global_integer_domain_enumerated','candidate_feasibility_evaluated','old_holdings_modified','promotion_allowed'):
                    self.assertIs(result[flag],False)

    def test_bad_suffix_and_types_rejected_even_zero_budget(self):
        baseline=dict(buy_limits={'A':2},seed_plans=[{'A':1}],excluded_plans=[],max_generated_plans=0)
        mutations=[('seed_plans',[{'A':1},{'A':True}]),('seed_plans',[{'A':1},{'A':1}]),('excluded_plans',[{'A':1.0}]),('excluded_plans',[{'B':0}]),('buy_limits',{'A':True}),('buy_limits',{' A':2}),('max_generated_plans',False),('max_generated_plans',10001)]
        for key,value in mutations:
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                subject.generate_repair_neighbors(**dict(baseline,**{key:value}))
        with self.assertRaises(ValueError):
            subject.generate_repair_neighbors(buy_limits={str(i):1 for i in range(71)},seed_plans=[{str(i):0 for i in range(71)}],excluded_plans=[],max_generated_plans=0)

    def test_empty_and_cap_boundaries_do_not_claim_feasibility(self):
        result=subject.generate_repair_neighbors(buy_limits={},seed_plans=[{}],excluded_plans=[{}],max_generated_plans=0)
        self.assertEqual(result['total_move_attempts'],0)
        self.assertEqual(result['generated_plans'],[])
        result=subject.generate_repair_neighbors(buy_limits={'A':10**12},seed_plans=[{'A':10**12}],excluded_plans=[],max_generated_plans=10)
        self.assertEqual([x['buy_shares'] for x in result['generated_plans']],[{'A':10**12-1}])

if __name__ == '__main__': unittest.main()

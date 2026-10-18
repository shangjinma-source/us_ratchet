"""Fresh independent bounded cases. No author fixtures, real pool, IO host or API."""
import hashlib
import importlib.util
import itertools
import math
from datetime import date, timedelta
from fractions import Fraction as F
from pathlib import Path
import random
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'backtest/ndx_return_priority_first_candidate_research.py'
raw = SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '2b9c2fe2d863698fcea8e903ea22bbe3f3792a85afc01244beb30eae28bfdb43'
spec = importlib.util.spec_from_file_location('independent_return_subject', SOURCE)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
POLICY = dict(max_single_weight=.45, min_single_weight=.05, top_three_cap=.8, min_neff_ratio=.7, chain_cap=.55)
SCOPE = 'INITIAL_DEPLOYMENT_DAILY_DIAGNOSTICS_ONLY'


def inventory():
    rows = [dict(security_id=f'Q{i}', issuer_id=f'J{i}', ticker=f'N{i}', risk_chain=f'R{i}') for i in range(6)]
    rows.append(dict(security_id='ALT', issuer_id='J0', ticker='CLASSALT', risk_chain='R0'))
    return rows


def run_case(rows, *, returns=None, objective=180, integer=180, local=16, seed=44):
    ids = [row['security_id'] for row in rows]
    return s.run_bounded_search(securities=rows, initial_prices={sid:73. for sid in ids},
        target_prices={sid:100. for sid in ids},
        returns=returns or {sid:[.01 + i*.002, -.004] for i,sid in enumerate(ids)},
        return_dates=['2026-09-18','2026-09-21'], cutoff='2026-09-21', policy=POLICY,
        cash=20000, fee_bps=0, buffer=100, risk_scope=SCOPE, support_limit=3,
        per_support_objectives=local, per_support_integers=14,
        global_objectives=objective, global_integers=integer, seed=seed)


class IndependentSmall(unittest.TestCase):
    def test_changed_hand_money_126_intervals_peak_and_fixed_units(self):
        rows=inventory()[:2]; metadata={r['security_id']:r for r in rows}
        returns={'Q0':[-.2]+[0.]*124+[.25], 'Q1':[-.1]+[0.]*124+[1/9]}
        b=s.Budget(1,0)
        result=s.evaluate_allocation(quantities={'Q0':37,'Q1':19}, initial_prices={'Q0':127.,'Q1':263.},
            returns=returns, metadata=metadata, policy=POLICY, cash=20000, fee_bps=10,
            buffer=100,budget=b,enforce_risk=False,risk_scope=SCOPE)
        gross=F(37*127+19*263); fee=gross/F(1000); idle=F(20000)-gross-fee
        expected=[F(20000),F(20000)-fee]+[idle+F(37*127)*F(4,5)+F(19*263)*F(9,10)]*125+[F(20000)-fee]
        self.assertEqual(len(expected),128)
        for observed,want in zip(result['net_wealth_path'],expected):self.assertAlmostEqual(observed,float(want),places=9)
        self.assertAlmostEqual(result['training_metrics']['cagr'],float((expected[-1]/20000)**2-1),places=13)
        self.assertAlmostEqual(result['training_metrics']['maximum_drawdown'],float(1-min(expected)/20000),places=13)
        self.assertAlmostEqual(result['remaining_cash'],float(idle),places=9)
        self.assertEqual(b.objective_calls,1)

    def test_polynomial_domain_and_real_multisupport_integer_search(self):
        rows=inventory(); actual_supports=[]; candidates=[]; original=s.evaluate_allocation
        def observed(**kw):
            r=original(**kw)
            if r:
                actual_supports.append(tuple(sorted(kw['quantities'])))
                candidates.append((dict(kw['quantities']),r))
            return r
        with patch.object(s,'evaluate_allocation',side_effect=observed):result=run_case(rows)
        counts={k:sum(len({row['issuer_id'] for row in combo})==k for combo in itertools.combinations(rows,k)) for k in range(1,7)}
        self.assertEqual([int(r['total_issuer_unique_compositions']) for r in result['per_k_coverage']],[counts[k] for k in range(1,7)])
        self.assertGreaterEqual(len(set(actual_supports)),2)
        self.assertTrue(any(any(type(q) is float and not q.is_integer() for q in quantities.values()) for quantities,_ in candidates))
        integer_candidates=[q for q,_ in candidates if all(type(v)is int for v in q.values())]
        self.assertGreater(len({tuple(sorted(q.items())) for q in integer_candidates}),2)
        for winner in result['co_winners']:
            self.assertEqual(winner['k'],len(winner['quantities']))
            self.assertEqual(winner['k'],len(set(winner['issuers'].values())))
            self.assertNotIn({'Q0','ALT'},[set(winner['quantities'])])
            for sid,q in winner['quantities'].items():self.assertAlmostEqual(winner['hypothetical_training_initial_economic_units'][sid]*73,q*100)
            self.assertAlmostEqual(winner['reconciliation_total'],20000)
        independently_best=max(r['training_metrics']['cagr'] for q,r in candidates if all(type(v)is int for v in q.values()))
        self.assertEqual({w['training_metrics']['cagr'] for w in result['co_winners']},{independently_best})

    def test_equal_cagr_keeps_supports_with_distinct_drawdowns(self):
        rows=inventory()[:6]
        returns={r['security_id']:([1.,-.5] if i<2 else [0.,0.]) for i,r in enumerate(rows)}
        result=run_case(rows,returns=returns,objective=240,integer=240,local=18,seed=97)
        winners=result['co_winners']
        self.assertTrue(winners)
        self.assertEqual({w['training_metrics']['cagr'] for w in winners},{0.})
        self.assertGreater(len({w['training_metrics']['maximum_drawdown'] for w in winners}),1)
        self.assertGreater(len({tuple(w['support_security_ids']) for w in winners}),1)

    def test_no_extra_local_global_objectives_and_zero_budget(self):
        calls=[]; original=s.evaluate_allocation
        def traced(**kw):
            before=kw['budget'].objective_calls
            r=original(**kw)
            calls.append((tuple(sorted(kw['quantities'])),kw['budget'].objective_calls-before))
            return r
        with patch.object(s,'evaluate_allocation',side_effect=traced):r=run_case(inventory(),objective=13,integer=20,local=7)
        self.assertEqual(sum(delta for _,delta in calls),r['budget']['objective_calls'])
        self.assertLessEqual(r['budget']['objective_calls'],13)
        self.assertLessEqual(r['budget']['integer_proposals'],20)
        per_support={}
        for support,delta in calls:per_support[support]=per_support.get(support,0)+delta
        self.assertTrue(all(v<=7 for v in per_support.values()))
        zero=run_case(inventory(),objective=0,integer=0)
        self.assertEqual(zero['budget']['objective_calls'],0)
        self.assertEqual(zero['co_winners'],[])
        self.assertEqual(len(zero['per_k_coverage']),6)

    def test_bad_inputs_and_float_risk_boundaries_no_account_authority(self):
        rows=inventory(); ids=[r['security_id'] for r in rows]; prices={sid:100 for sid in ids};returns={sid:[0,0] for sid in ids}
        for changes in ('future','minusone','bool','identity'):
            import copy
            rr=copy.deepcopy(rows);rets=copy.deepcopy(returns);days=['2026-09-18','2026-09-21']
            if changes=='future':days[-1]='2026-09-22'
            if changes=='minusone':rets['Q0'][0]=-1
            if changes=='bool':rets['Q0'][0]=True
            if changes=='identity':rr[0]['issuer_id']=''
            with self.assertRaises(ValueError):s.validate_inputs(rr,prices,rets,days,'2026-09-21')
        meta={r['security_id']:r for r in rows}
        with self.assertRaises(ValueError):s.risk_checks({'Q0':100,'ALT':100},meta,POLICY)
        self.assertTrue(s.risk_checks({f'Q{i}':100 for i in range(4)},meta,POLICY)['all_passed'])
        self.assertFalse(s.risk_checks(dict(Q0=450.01,Q1=183.33,Q2=183.33,Q3=183.33),meta,POLICY)['all_passed'])
        r=run_case(rows,objective=10,integer=10)
        self.assertFalse(r['point_in_time_verified']);self.assertFalse(r['old_book_plus_new_cash_joint_optimization_complete'])
        self.assertFalse(r['real_adoption_allowed']);self.assertEqual(r['future_one_year_oos'],'NOT_CONSUMED_NOT_MATURE')


if __name__=='__main__':unittest.main()

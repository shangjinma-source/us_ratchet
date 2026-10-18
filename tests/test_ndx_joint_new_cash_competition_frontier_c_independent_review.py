"""Independent Fraction oracle on bounded synthetic domains, never real economics."""
import builtins
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from backtest import ndx_variable_cardinality_new_cash_problem_research as A
from backtest import ndx_joint_new_cash_competition_frontier_research as B

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def raw_case():
    ids=('A1','A2','B','C')
    return dict(evidence_facts={'conditional_inventory':[dict(security_id=s,issuer_id='A' if s.startswith('A') else s,ticker=s,risk_chain=s) for s in ids]},
        prior_book=dict(holdings={'A1':'0.5'},cash='1',currency='USD',as_of='2026-09-30',cash_includes_event=False),
        cash_event=dict(amount='3',currency='USD',decision_date='2026-09-30',execution_date='2026-10-01',available_at='2026-09-30T18:00:00Z'),
        price_context=dict(currency='USD',stage='DECISION_KNOWN_PRICES',decision_at='2026-09-30T20:00:00Z',session_timezone='UTC',basis='SYNTHETIC',prices={s:dict(price=str(p),lot_size=1,available_at='2026-09-30T19:00:00Z',price_date='2026-09-30',basis='SYNTHETIC') for s,p in zip(ids,(2,3,2,1))}),
        policy=dict(risk_parameters=dict(max_single_weight='1',min_single_weight='0',top_weight_cap='1',minimum_effective_n_ratio='0',risk_chain_top1_cap='1'),transaction_cost_bps='2500',minimum_cash_buffer='0',currency='USD'),domain_kind='WHOLE_LOT_QUANTITIES')

def prepare(raw=None, matrix=None):
    raw=raw_case() if raw is None else raw
    ids=sorted(raw['price_context']['prices'])
    covariance=dict(schema='EXPLICIT_SYNTHETIC_RATIONAL_COVARIANCE_V1',security_ids=ids,values=matrix if matrix is not None else [[(4,9,1,1)[i] if i==j else 0 for j in range(4)] for i in range(4)],return_unit='ONE_STEP_DECIMAL_RETURN_SQUARED',available_at='2026-09-30T19:00:00Z',timing_scope='SYNTHETIC_TRAINING_ONLY')
    return B.prepare_synthetic_joint_competition(prepared_problem=A.prepare_synthetic_new_cash_problem(synthetic_case=raw),synthetic_covariance=covariance)

def frontier(rows):
    return {r['rank'] for r in rows if not any(all(a<=b for a,b in zip(o['v'],r['v'])) and any(a<b for a,b in zip(o['v'],r['v'])) for o in rows)}

class IndependentSyntheticJointTests(unittest.TestCase):
    def test_complete_fraction_oracle_fees_issuer_denominators_and_ties(self):
        c=prepare();result=B.run_synthetic_joint_frontier(competition=c,work_budget=100)
        # Independently derive caps from raw cash 1+3, fee factor 5/4.
        expected=[]; compatible={k:0 for k in (1,2,3)};feasible={k:[] for k in (1,2,3)}
        for rank,n in enumerate(product(range(2),range(2),range(2),range(4))):
            q=(F(1,2)+n[0],F(n[1]),F(n[2]),F(n[3]));gross=2*n[0]+3*n[1]+2*n[2]+n[3];fee=F(gross,4)
            cash=4-gross-fee;stock=sum(p*v for p,v in zip((2,3,2,1),q));w=tuple(p*v/stock for p,v in zip((2,3,2,1),q));k=sum(v>0 for v in q)
            category='ISSUER_CONFLICT' if q[1]>0 else 'CASH_REJECTED' if cash<0 else 'FEASIBLE'
            v=(sum(d*x*x for d,x in zip((4,9,1,1),w)),F(gross,5)) if category=='FEASIBLE' else None
            e=dict(rank=rank,q=q,gross=F(gross),fee=fee,cash=cash,stock=stock,w=w,k=k,category=category,v=v);expected.append(e)
            if category!='ISSUER_CONFLICT':compatible[k]+=1
            if v is not None:feasible[k].append(e)
        self.assertEqual(compatible,{1:2,2:8,3:6});self.assertEqual({k:len(v) for k,v in feasible.items()},{1:2,2:5,3:1})
        self.assertEqual(len(result['classified_records']),32)
        for r,e in zip(result['classified_records'],expected):
            self.assertEqual(r['category'],e['category']);self.assertEqual(tuple(F(r['final_quantities'][s]) for s in ('A1','A2','B','C')),e['q'])
            self.assertEqual(r['rank'],e['rank'])
            for key,name in [('actual_buy_notional','gross'),('actual_fee','fee'),('remaining_cash','cash'),('final_stock_value','stock')]:self.assertEqual(F(r[key]),e[name])
            self.assertEqual(None if r['training_objectives'] is None else tuple(map(F,r['training_objectives'])),e['v'])
            self.assertEqual(e['stock']+e['cash'],5-e['fee'])
        for row in result['all_k_frontiers']:
            k=row['holding_count'];self.assertEqual(int(row['issuer_compatible_quantity_box_count']),compatible[k]);self.assertEqual(int(row['feasible_full_domain_count_or_null']),len(feasible[k]));self.assertEqual({r['rank'] for r in row['training_frontier']},frontier(feasible[k]))
        self.assertEqual(sum(len(r['training_frontier']) for r in result['all_k_frontiers']),6)
        self.assertFalse(result['coverage']['training_dominance_used_to_prune_economic_domain']);self.assertEqual(result['continuous']['unsearched_regions'],'UNKNOWN')

    def test_resume_chunks_full_replay_and_coordinated_resign_rejected(self):
        c=prepare();partial=B.run_synthetic_joint_frontier(competition=c,work_budget=7);state=partial['resume_state']
        done=B.run_synthetic_joint_frontier(competition=c,work_budget=100,resume_state=state,expected_resume_sha256=partial['resume_sha256'])
        full=B.run_synthetic_joint_frontier(competition=c,work_budget=100)
        self.assertEqual(done['resume_state'],full['resume_state']);self.assertEqual(done['coverage']['resume_prefix_validation_tuples'],7)
        mutations=[lambda x:x.update(cursor=8),lambda x:x['classified_records'].pop(),lambda x:x['classified_records'][0].update(actual_fee='1'),lambda x:x['per_k']['1'].update(feasible=99),lambda x:x.update(prefix_hash='a'*64),lambda x:x['per_k']['1']['frontier'].clear(),lambda x:x.update(unknown=True)]
        for mutate in mutations:
            bad=deepcopy(state);mutate(bad)
            with self.subTest(bad=bad),self.assertRaises(ValueError):B.run_synthetic_joint_frontier(competition=c,work_budget=1,resume_state=bad,expected_resume_sha256=digest(bad))
        self.assertEqual(state,partial['resume_state'])

    def test_psd_zero_pivot_singular_and_nonfinite_or_false(self):
        good=[[0]*4 for _ in range(4)];good[1][1]=1;good[2][2]=1;good[1][2]=good[2][1]=1
        c=prepare(matrix=good);self.assertEqual(c['synthetic_covariance']['positive_semidefinite_check'],'EXACT_RATIONAL_SCHUR_COMPLEMENTS')
        for value in ('NaN','Infinity',True,0.1):
            bad=deepcopy(good);bad[0][0]=value
            with self.subTest(value=value),self.assertRaises(ValueError):prepare(matrix=bad)
        bad=deepcopy(good);bad[0][1]=bad[1][0]=1
        with self.assertRaises(ValueError):prepare(matrix=bad)
        for budget in (-1,True):
            with self.assertRaises(ValueError):B.run_synthetic_joint_frontier(competition=c,work_budget=budget)

    def test_l1_target_misses_cross_issuer_better_training_actions(self):
        raw=raw_case();raw['evidence_facts']['conditional_inventory']=[r for r in raw['evidence_facts']['conditional_inventory'] if r['security_id']!='A2'];raw['prior_book'].update(holdings={'A1':'1'},cash='0');raw['cash_event']['amount']='4';raw['price_context']['prices'].pop('A2')
        for p in raw['price_context']['prices'].values():p['price']='1'
        raw['policy']['transaction_cost_bps']='0';c=prepare(raw,[[4,0,0],[0,9,0],[0,0,1]])
        records=B.run_synthetic_joint_frontier(competition=c,work_budget=200)['classified_records']
        byweights={tuple(F(r['weights'].get(s,'0')) for s in ('A1','B','C')):r for r in records if r['category']=='FEASIBLE'}
        target=byweights[(F(3,4),F(1,4),F(0))];other=byweights[(F(1,3),F(2,3),F(0))];cross=byweights[(F(1,4),F(1,4),F(1,2))]
        self.assertEqual(tuple(map(F,target['training_objectives'])),(F(45,16),F(3,5)))
        self.assertEqual(tuple(map(F,other['training_objectives'])),(F(40,9),F(2,5)))
        # Root's L1 example uses B variance 1, while its separate four-SID oracle uses B variance 1 too.
        # Check true economic dominance with the intended diag(4,1,1), not diag(4,9,1).
        c=prepare(raw,[[4,0,0],[0,1,0],[0,0,1]]);rows=B.run_synthetic_joint_frontier(competition=c,work_budget=200)['classified_records']
        lookup={tuple(F(r['weights'].get(s,'0')) for s in ('A1','B','C')):r for r in rows if r['category']=='FEASIBLE'}
        self.assertEqual(tuple(map(F,lookup[(F(3,4),F(1,4),F(0))]['training_objectives'])),(F(37,16),F(3,5)))
        self.assertEqual(tuple(map(F,lookup[(F(1,3),F(2,3),F(0))]['training_objectives'])),(F(8,9),F(2,5)))
        self.assertEqual(F(lookup[(F(1,4),F(1,4),F(1,2))]['training_objectives'][0]),F(9,16))

    def test_negative_budget_all_cash_and_zero_io_detached_authority(self):
        raw=raw_case();raw['policy']['minimum_cash_buffer']='5';c=prepare(raw);r=B.run_synthetic_joint_frontier(competition=c,work_budget=0)
        self.assertEqual(r['coverage']['raw_quantity_box_count'],'0');self.assertEqual(r['classified_records'],[]);self.assertTrue(r['coverage']['necessary_negative_cash_domain_empty'])
        raw=raw_case();raw['prior_book']['holdings']={};c=prepare(raw)
        ZoneInfo('UTC')  # runtime timezone library explicitly outside source-IO claim
        with patch.object(Path,'read_bytes',side_effect=AssertionError('source IO')),patch.object(builtins,'open',side_effect=AssertionError('source IO')):
            r=B.run_synthetic_joint_frontier(competition=c,work_budget=0)
        self.assertEqual(r['all_cash_control']['category'],'ALL_CASH_CONTROL');self.assertIsNone(r['all_cash_control']['training_objectives']);self.assertIsNone(r['all_cash_control']['effective_n']);self.assertTrue(all(v is False for v in r['authority'].values()))
        r['resume_state']['classified_records'].append({'bad':True});self.assertEqual(B.run_synthetic_joint_frontier(competition=c,work_budget=0)['resume_state']['classified_records'],[])

    def test_effective_n_acceptance_uses_original_exact_tolerance(self):
        raw=raw_case();raw['prior_book'].update(holdings={'A1':'0.7500000001','B':'0.2499999999'},cash='1');raw['cash_event']['amount']='0'
        for p in raw['price_context']['prices'].values():p['price']='1'
        raw['evidence_facts']['conditional_exclusions']={s:'SYNTHETIC_FREEZE_ALL' for s in raw['price_context']['prices']};raw['policy']['risk_parameters']['minimum_effective_n_ratio']='0.8'
        c=prepare(raw);r=B.run_synthetic_joint_frontier(competition=c,work_budget=1)['classified_records'][0]
        square=F('0.7500000001')**2+F('0.2499999999')**2
        self.assertGreater(square,F(5,8));self.assertGreaterEqual(1/square+F(1,10**9),F(8,5));self.assertEqual(r['category'],'FEASIBLE')
        raw['prior_book']['holdings']={'A1':'0.750000001','B':'0.249999999'}
        r=B.run_synthetic_joint_frontier(competition=prepare(raw),work_budget=1)['classified_records'][0]
        self.assertEqual(r['category'],'RISK_REJECTED');self.assertFalse(r['risk_checks']['MINIMUM_EFFECTIVE_N'])

if __name__=='__main__':unittest.main()

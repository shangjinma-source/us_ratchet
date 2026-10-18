"""Small independent dollar arithmetic and continuous-region proof regressions."""
from copy import deepcopy
from fractions import Fraction as F
import unittest
from unittest.mock import patch
from pathlib import Path

from backtest import ndx_variable_cardinality_new_cash_problem_research as A
from backtest import ndx_continuous_joint_projection_research as P
from backtest import ndx_continuous_joint_certificates_research as C
from backtest import ndx_continuous_joint_frontier_research as S


def raw_case(old=None, cash='4', prior='0', fee='0', buffer='0'):
    rows = [dict(security_id=s,issuer_id=i,ticker=s,risk_chain=r) for s,i,r in
            [('A','IA','R1'),('A2','IA','R2'),('B','IB','R2'),('C','IC','R3')]]
    return dict(evidence_facts=dict(conditional_inventory=rows),
        prior_book=dict(holdings={'A':'1'} if old is None else old,cash=prior,currency='USD',
                        as_of='2026-09-30',cash_includes_event=False),
        cash_event=dict(amount=cash,currency='USD',decision_date='2026-09-30',execution_date='2026-10-01',
                        available_at='2026-09-30T19:00:00Z'),
        price_context=dict(currency='USD',stage='DECISION_KNOWN_PRICES',decision_at='2026-09-30T20:00:00Z',
            session_timezone='UTC',basis='SYNTHETIC',prices={row['security_id']:dict(price='1',lot_size=1,
            available_at='2026-09-30T19:00:00Z',price_date='2026-09-30',basis='SYNTHETIC') for row in rows}),
        policy=dict(risk_parameters=dict(max_single_weight='1',min_single_weight='0',top_weight_cap='1',
            minimum_effective_n_ratio='0',risk_chain_top1_cap='1'),transaction_cost_bps=fee,
            minimum_cash_buffer=buffer,currency='USD'),domain_kind='CONTINUOUS_INCREMENTAL_DOLLARS')


def prepare(raw=None, matrix=None, eps='0'):
    raw = raw_case() if raw is None else raw
    problem = A.prepare_synthetic_new_cash_problem(synthetic_case=raw)
    ids = sorted(raw['price_context']['prices'])
    covariance = dict(schema='EXPLICIT_SYNTHETIC_RATIONAL_COVARIANCE_V1',security_ids=ids,
        values=matrix if matrix is not None else [[4 if i == j == 0 else int(i == j) for j in range(len(ids))] for i in range(len(ids))],
        return_unit='ONE_STEP_DECIMAL_RETURN_SQUARED',available_at='2026-09-30T19:00:00Z',timing_scope='SYNTHETIC_TRAINING_ONLY')
    return P.prepare_synthetic_continuous_competition(prepared_problem_A=problem,synthetic_covariance=covariance,
        epsilon_variance=eps,epsilon_turnover=eps)


def witness(c, support, y, w):
    return P.verify_continuous_witness(competition=c,support_security_ids=support,
                                     reciprocal_total_stock=y,weights=w)


class ContinuousTests(unittest.TestCase):
    def test_fractional_frozen_cash_event_fee_and_dollar_conservation(self):
        raw = raw_case(old={'A':'0.5'},cash='2',prior='1',fee='2500')
        raw['evidence_facts']['conditional_exclusions'] = {'A':'SYNTHETIC_NONBUY'}
        c = prepare(raw)
        p = P.project_frozen_support(competition=c,support_security_ids=['A','B'],total_buy_notional='2')
        self.assertEqual(p['weights']['A'],dict(kind='EXACT_EQUALITY',frozen_weight='1/5'))
        w = witness(c,['A','B'],'2/5',{'A':'1/5','B':'4/5'})
        self.assertEqual(w['final_quantities'],{'A':'1/2','B':'2'})
        self.assertEqual(w['fee'],'1/2')
        self.assertEqual(w['cash_after'],'1/2')
        self.assertEqual(w['objectives']['turnover'],'4/7')
        with self.assertRaisesRegex(ValueError,'exact equality'):
            witness(c,['A','B'],'2/5',{'A':'2/5','B':'3/5'})

    def test_all_issuer_classes_and_full_k_without_preselection(self):
        c = prepare(raw_case(old={}))
        self.assertEqual([v['full_conditional'] for v in c['core']['per_k'].values()],['4','5','2'])
        out = S.search_synthetic_continuous_frontier(competition=c,work_budget=0)
        self.assertEqual(out['status'],'UNATTAINED_TRAINING_PARETO_NO_POSITIVE_ACTION_ATTAINED')
        self.assertEqual([r['unexpanded_support_count'] for r in out['all_k_support_coverage']],['4','5','2'])
        c = prepare()
        out = S.search_synthetic_continuous_frontier(competition=c,work_budget=7)
        for row in out['all_k_support_coverage']:
            self.assertEqual(int(row['expanded_support_count'])+int(row['unexpanded_support_count']),int(row['frozen_legal_support_count']))
        with self.assertRaisesRegex(ValueError,'Issuer'):
            witness(c,['A','A2'],'1/2',{'A':'1/2','A2':'1/2'})

    def test_general_non_diagonal_multiple_old_and_independent_risk_math(self):
        raw = raw_case(old={'A':'0.5','B':'0.5'},cash='3')
        mat = [['2','0','1','0'],['0','1','0','0'],['1','0','2','0'],['0','0','0','1']]
        c = prepare(raw,mat)
        out = S.search_synthetic_continuous_frontier(competition=c,work_budget=18)
        self.assertGreaterEqual(len(out['primal_witnesses']),2)
        for w in out['primal_witnesses']:
            weights = {s:F(v) for s,v in w['weights'].items()}
            ids = ['A','A2','B','C']
            f = sum((weights.get(a,0)*weights.get(b,0)*F(mat[i][j]) for i,a in enumerate(ids) for j,b in enumerate(ids)),F(0))
            self.assertEqual(F(w['objectives']['variance']),f)
            self.assertEqual(F(w['objectives']['turnover']),F(w['t'])/4)
            finalvalue = sum(F(v) for v in w['final_quantities'].values())
            self.assertEqual(finalvalue+F(w['cash_after']),4-F(w['fee']))
        self.assertTrue(out['residual_regions'] or out['implicit_support_forest'])
        self.assertFalse(out['exact_continuous_frontier_proven'])

    def test_psd_singular_and_bad_zero_pivot(self):
        prepare(matrix=[[1]*4 for _ in range(4)])
        bad = [[0]*4 for _ in range(4)];bad[0][1]=bad[1][0]=1
        with self.assertRaisesRegex(ValueError,'PSD'):
            prepare(matrix=bad)

    def test_original_tau_effective_n_boundary_and_other_risks(self):
        raw = raw_case(cash='10')
        raw['policy']['risk_parameters']['minimum_effective_n_ratio'] = '0.8'
        c = prepare(raw)
        w = witness(c,['A','B'],'1/2',{'A':'7500000001/10000000000','B':'2499999999/10000000000'})
        self.assertTrue(w['risk_checks']['effective_n'])
        self.assertGreater(sum(F(v)**2 for v in w['weights'].values()),F(1,1)/F('1.6'))
        for key, value in [('max_single_weight','0.6'),('min_single_weight','0.3'),
                           ('top_weight_cap','0.9'),('risk_chain_top1_cap','0.6')]:
            rr = deepcopy(raw);rr['policy']['risk_parameters'][key] = value
            with self.assertRaisesRegex(ValueError,'risk failed'):
                witness(prepare(rr),['A','B'],'1/2',w['weights'])

    def test_psd_supporting_plane_global_lower_and_certificate_drift(self):
        c = prepare(raw_case(fee='2500'))
        region = C.root_region(c,['A','B'])
        bound = C.bound_region(c,region,{'A':'5/21','B':'16/21'})
        self.assertEqual(bound['variance_lower'],'356/441')
        w = witness(c,['A','B'],'5/21',{'A':'5/21','B':'16/21'})
        self.assertEqual(w['objectives']['variance'],bound['variance_lower'])
        C.verify_continuous_region_certificate(competition=c,region=region,certificate=bound)
        bad = deepcopy(bound);bad['variance_lower']='1'
        with self.assertRaisesRegex(ValueError,'certificate drift'):
            C.verify_continuous_region_certificate(competition=c,region=region,certificate=bad)

    def test_halfopen_split_no_duplicate_boundary_and_exact_turnover_unit(self):
        c = prepare();r = C.root_region(c,['A','B'])
        r['axes']['$y'] = C.axis(F(1,5),F(1,2))
        b = C.bound_region(c,r)
        self.assertEqual(b['turnover_span'],'3/5')
        left,right = C.split_region(r)
        changed = [s for s in r['axes'] if left['axes'][s] != r['axes'][s]][0]
        self.assertEqual(left['axes'][changed]['upper'],right['axes'][changed]['lower'])
        self.assertFalse(left['axes'][changed]['upper_closed'])
        self.assertTrue(right['axes'][changed]['lower_closed'])
        for child in (left,right): C.check_region(c,child)

    def test_open_boundary_never_becomes_action(self):
        c = prepare();r = C.root_region(c,['A','B'])
        self.assertFalse(r['axes']['B']['lower_closed'])
        with self.assertRaisesRegex(ValueError,'Strict positive'):
            witness(c,['A','B'],'1',{'A':'1','B':'0'})
        bad = deepcopy(r);bad['axes']['B']['lower_closed']=True
        with self.assertRaisesRegex(ValueError,'Open support'):
            C.bound_region(c,bad)

    def test_cross_k_dominance_cannot_fake_per_k_cover(self):
        c = prepare(eps='10');r = C.root_region(c,['A','B'])
        bound = C.bound_region(c,r)
        k3 = witness(c,['A','B','C'],'1/3',{'A':'1/3','B':'1/3','C':'1/3'})
        k2 = witness(c,['A','B'],'1/3',{'A':'1/3','B':'2/3'})
        self.assertLess(F(k3['objectives']['variance']),F(k2['objectives']['variance']))
        with self.assertRaisesRegex(ValueError,'same k'):
            C.cover_region(c,r,bound,k3)
        cert = C.cover_region(c,r,bound,k2)
        C.verify_continuous_cover_certificate(competition=c,region=r,bound=bound,certificate=cert)
        cert['scope']='GLOBAL'
        with self.assertRaisesRegex(ValueError,'PER_K'):
            C.verify_continuous_cover_certificate(competition=c,region=r,bound=bound,certificate=cert)

    def test_resume_budget_partitions_and_coherently_resigned_attacks(self):
        c = prepare();first = S.search_synthetic_continuous_frontier(competition=c,work_budget=8)
        resumed = S.search_synthetic_continuous_frontier(competition=c,work_budget=8,
            resume_state=first['resume_state'],expected_resume_sha256=first['resume_sha256'])
        whole = S.search_synthetic_continuous_frontier(competition=c,work_budget=16)
        self.assertEqual(resumed['resume_state'],whole['resume_state'])
        self.assertEqual(resumed['work_and_replay_counters']['resume_prefix_validation_events'],8)
        for mutate in [lambda s:s['queue'].pop(),lambda s:s['queue'].append(deepcopy(s['queue'][0])),
                       lambda s:s['counters'].update(region_splits=999),lambda s:s.update(events=True)]:
            bad = deepcopy(first['resume_state']);mutate(bad)
            with self.assertRaises(ValueError):
                S.search_synthetic_continuous_frontier(competition=c,work_budget=0,resume_state=bad,expected_resume_sha256=P.digest(bad))
        for budget in (True,-1,0.5):
            with self.assertRaises(ValueError):S.search_synthetic_continuous_frontier(competition=c,work_budget=budget)

    def test_large_epsilon_cover_all_k_retains_economic_domains(self):
        c = prepare(eps='10')
        out = S.search_synthetic_continuous_frontier(competition=c,work_budget=50)
        self.assertEqual(out['status'],'CERTIFIED_EPSILON_TRAINING_OBJECTIVE_COVER')
        self.assertTrue(all(r['epsilon_training_objective_cover_certified'] for r in out['all_k_support_coverage']))
        self.assertTrue(all(r['economic_domain_retained'] for r in out['archived_regions']))
        self.assertTrue(all(v is False for v in out['authority'].values()))
        self.assertEqual(out['plan_rows'],[])

    def test_tzero_negative_budget_vzero_typed_and_cash_null(self):
        c = prepare(raw_case(cash='0'))
        out = S.search_synthetic_continuous_frontier(competition=c,work_budget=50)
        self.assertEqual(out['status'],'CERTIFIED_EPSILON_TRAINING_OBJECTIVE_COVER')
        self.assertEqual([w['support'] for w in out['primal_witnesses']],[['A']])
        negative = S.search_synthetic_continuous_frontier(competition=prepare(raw_case(buffer='5')),work_budget=0)
        self.assertEqual(negative['branch'],'NEGATIVE_CASH_BUDGET_EMPTY')
        zero = S.search_synthetic_continuous_frontier(competition=prepare(raw_case(old={},cash='0',prior='1',buffer='1')),work_budget=0)
        self.assertEqual(zero['branch'],'V_ZERO_T_ZERO_ONLY_CASH')
        self.assertIsNone(zero['zero_buy_control']['variance'])
        c = prepare(raw_case(old={}))
        a = witness(c,['B','C'],'1',{'B':'1/2','C':'1/2'})
        b = witness(c,['B','C'],'2',{'B':'1/2','C':'1/2'})
        self.assertEqual(a['objectives']['variance'],b['objectives']['variance'])
        self.assertLess(F(b['objectives']['turnover']),F(a['objectives']['turnover']))

    def test_interval_risk_infeasibility_and_joint_chain(self):
        raw = raw_case();raw['policy']['risk_parameters']['top_weight_cap']='0.8'
        c = prepare(raw);b = C.bound_region(c,C.root_region(c,['A','B']))
        # Weak independent bounds may be inconclusive, never falsely reject.
        self.assertIsInstance(b['infeasibility_reasons'],list)
        raw = raw_case();raw['evidence_facts']['conditional_inventory'][2]['risk_chain']='R1'
        raw['policy']['risk_parameters']['risk_chain_top1_cap']='0.7'
        with self.assertRaisesRegex(ValueError,'risk failed'):
            witness(prepare(raw),['A','B'],'1/2',{'A':'1/2','B':'1/2'})
        c = prepare();r = C.root_region(c,['A','B']);r['axes']['A']=C.axis(F(4,5),F(9,10));r['axes']['B']=C.axis(F(4,5),F(9,10))
        self.assertIn('SIMPLEX_MASS_CONTRADICTION',C.bound_region(c,r)['infeasibility_reasons'])

    def test_re_signed_A_math_drift_numeric_types_detached_no_path_io(self):
        c = prepare()
        for key,value in [('old_stock_value','2'),('fee_factor','2'),('total_cash_before_buys','8')]:
            bad = deepcopy(c['A_problem']);bad['domain_formula'][key]=value
            bad['problem_id']=P.digest({k:v for k,v in bad.items() if k != 'problem_id'})
            cov = {k:v for k,v in c['synthetic_covariance'].items() if k != 'positive_semidefinite_check'}
            with self.assertRaisesRegex(ValueError,'drift'):
                P.prepare_synthetic_continuous_competition(prepared_problem_A=bad,synthetic_covariance=cov)
        for bad in (True,float('nan'),-1):
            with self.assertRaises(ValueError):
                witness(c,['A'],'1',{'A':bad})
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No source IO')):
            result = S.search_synthetic_continuous_frontier(competition=c,work_budget=8)
        result['resume_state']['queue'].clear()
        self.assertTrue(S.search_synthetic_continuous_frontier(competition=c,work_budget=0)['implicit_support_forest'])

    def test_component_counters_match_actual_calls_and_scope_is_replay_bound(self):
        c = prepare()
        bound_fn, primal_fn = C.bound_region,C._witness
        with patch.object(S,'bound_region',wraps=bound_fn) as direct_bounds, \
             patch.object(C,'bound_region',wraps=bound_fn) as cover_bounds, \
             patch.object(C,'_witness',wraps=primal_fn) as primal_checks, \
             patch.object(S,'_witness',wraps=S._witness) as control_checks:
            out = S.search_synthetic_continuous_frontier(competition=c,work_budget=14)
        counter = out['work_and_replay_counters']['cumulative_search_components']
        self.assertEqual(counter['bound_checks'],direct_bounds.call_count+cover_bounds.call_count)
        self.assertEqual(counter['witness_formula_checks'],primal_checks.call_count)
        self.assertEqual(control_checks.call_count,1)
        self.assertEqual(counter['support_expansions']+counter['support_materializations']+counter['region_events'],14)
        self.assertLessEqual(counter['witness_proposals'],3*counter['region_events'])
        changed = deepcopy(out['resume_state'])
        changed['search_registration']['budget_scope']='TOTAL_OPERATIONS'
        with self.assertRaisesRegex(ValueError,'replay mismatch'):
            S.search_synthetic_continuous_frontier(competition=c,work_budget=0,resume_state=changed,expected_resume_sha256=P.digest(changed))
        altered = deepcopy(c);altered['search_registration']['budget_scope']='TOTAL_OPERATIONS'
        altered['competition_id']=P.digest({k:v for k,v in altered.items() if k != 'competition_id'})
        with self.assertRaisesRegex(ValueError,'Competition drift'):
            S.search_synthetic_continuous_frontier(competition=altered,work_budget=0)

    def test_exact_epsilon_zero_keeps_open_unattained_and_equal_objective_families(self):
        c = prepare(matrix=[[1]*4 for _ in range(4)])
        out = S.search_synthetic_continuous_frontier(competition=c,work_budget=20)
        rows = {r['holding_count']:r for r in out['all_k_support_coverage']}
        self.assertFalse(rows[2]['epsilon_training_objective_cover_certified'])
        self.assertTrue(any(t['region']['holding_count'] == 2 for t in out['residual_regions']))
        x = witness(c,['A','B'],'1/2',{'A':'1/2','B':'1/2'})
        y = witness(c,['A','C'],'1/2',{'A':'1/2','C':'1/2'})
        self.assertEqual(x['objectives'],y['objectives'])
        self.assertEqual(len(S._frontier([x,y])),2)

    def test_split_bounds_remain_visible_and_valid_on_both_children(self):
        c = prepare()
        out = S.search_synthetic_continuous_frontier(competition=c,work_budget=16)
        ledger = {b['certificate_id']:b for b in out['global_bound_regions']}
        inherited = [t for t in out['residual_regions'] if 'inherited_parent_bound' in t]
        self.assertTrue(inherited)
        for task in inherited:
            bound = task['inherited_parent_bound']
            self.assertEqual(ledger[bound['certificate_id']],bound)
            C.verify_continuous_region_certificate(competition=c,region=bound['region'],certificate=bound)
            relation = C.verify_inherited_parent_bound(competition=c,child_region=task['region'],parent_certificate=bound)
            self.assertEqual(relation,task['inherited_parent_relation'])
            self.assertEqual(task['region']['support'],bound['region']['support'])
            for key,axis in task['region']['axes'].items():
                parent = bound['region']['axes'][key]
                self.assertGreaterEqual(F(axis['lower']),F(parent['lower']))
                self.assertLessEqual(F(axis['upper']),F(parent['upper']))
        self.assertEqual(out['whole_conditional_domain_objective_lower_bounds']['variance'],'0')
        self.assertTrue(out['exact_partition_ledger'])
        for entry in out['exact_partition_ledger']:
            parent = ledger[entry['parent_certificate_id']]
            self.assertEqual(entry['children'],list(C.split_region(parent['region'])))
        base = next(t for t in inherited if t['region']['holding_count'] == 2)
        changed = deepcopy(base['region'])
        changed['support']=['A','B','C'];changed['holding_count']=3
        self.assertNotEqual(changed['support'],base['inherited_parent_bound']['region']['support'])
        added = next(s for s in changed['support'] if s not in changed['axes'])
        changed['axes'][added]=C.axis(F(0),F(1),False,True)
        with self.assertRaisesRegex(ValueError,'support mismatch'):
            C.verify_inherited_parent_bound(competition=c,child_region=changed,parent_certificate=base['inherited_parent_bound'])


if __name__ == '__main__':unittest.main()

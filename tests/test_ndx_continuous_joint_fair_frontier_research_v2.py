"""Bounded synthetic scheduling tests, no old test-suite or real fit runs."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import json
import unittest
from unittest.mock import patch
from pathlib import Path
from backtest import ndx_variable_cardinality_new_cash_problem_research as A
from backtest import ndx_continuous_joint_projection_research as P
from backtest import ndx_continuous_joint_certificates_research as C
from backtest import ndx_continuous_joint_frontier_research as V1
from backtest import ndx_continuous_joint_fair_frontier_research_v2 as V2


def fixture(n=3, classes=1, covariance_ones=False, epsilon='0', old='1', prior='0', fee='0', cash=None, buffer='0'):
    rows = [dict(security_id='OLD',issuer_id='IOLD',ticker='OLD',risk_chain='ROLD')]
    for i in range(n):
        for j in range(classes):
            sid = f'S{i:02d}_{j}'
            rows.append(dict(security_id=sid,issuer_id=f'I{i:02d}',ticker=sid,risk_chain='R'+sid))
    raw = dict(evidence_facts=dict(conditional_inventory=rows),
        prior_book=dict(holdings=old if type(old) is dict else {'OLD':old},cash=prior,currency='USD',as_of='2026-09-30',cash_includes_event=False),
        cash_event=dict(amount=str(max(n,1)) if cash is None else cash,currency='USD',decision_date='2026-09-30',execution_date='2026-10-01',available_at='2026-09-30T19:00:00Z'),
        price_context=dict(currency='USD',stage='DECISION_KNOWN_PRICES',decision_at='2026-09-30T20:00:00Z',session_timezone='UTC',basis='SYNTHETIC',
            prices={r['security_id']:dict(price='1',lot_size=1,available_at='2026-09-30T19:00:00Z',price_date='2026-09-30',basis='SYNTHETIC') for r in rows}),
        policy=dict(risk_parameters=dict(max_single_weight='1',min_single_weight='0',top_weight_cap='1',minimum_effective_n_ratio='0',risk_chain_top1_cap='1'),
            transaction_cost_bps=fee,minimum_cash_buffer=buffer,currency='USD'),domain_kind='CONTINUOUS_INCREMENTAL_DOLLARS')
    problem = A.prepare_synthetic_new_cash_problem(synthetic_case=raw)
    ids = sorted(raw['price_context']['prices'])
    covariance = dict(schema='EXPLICIT_SYNTHETIC_RATIONAL_COVARIANCE_V1',security_ids=ids,
        values=[[1 if covariance_ones else int(i==j) for j in range(len(ids))] for i in range(len(ids))],
        return_unit='ONE_STEP_DECIMAL_RETURN_SQUARED',available_at='2026-09-30T19:00:00Z',timing_scope='SYNTHETIC_TRAINING_ONLY')
    base = P.prepare_synthetic_continuous_competition(prepared_problem_A=problem,synthetic_covariance=covariance,
        epsilon_variance=epsilon,epsilon_turnover=epsilon)
    return base,V2.prepare_synthetic_fair_continuous_competition(mathematical_competition=base)


def run(c,budget,**kwargs):
    return V2.search_synthetic_fair_continuous_frontier(competition=c,work_budget=budget,**kwargs)


class FairSchedulerTests(unittest.TestCase):
    def test_actual_nine_issuer_v1_fifo_delay_vs_v2_first_leaf_and_bound(self):
        base,c = fixture(9)
        fifo = V1.search_synthetic_continuous_frontier(competition=base,work_budget=512)
        count = fifo['work_and_replay_counters']['cumulative_search_components']
        self.assertEqual((count['support_expansions'],count['support_materializations'],count['bound_checks']),(511,1,0))
        self.assertEqual(fifo['primal_witnesses'],[])
        self.assertIsNotNone(fifo['zero_buy_control'])
        ten = run(c,10)
        self.assertEqual(ten['observations']['first_leaf_event'],10)
        self.assertIsNone(ten['observations']['first_bound_event'])
        self.assertEqual(len(ten['implicit_support_forest']),9)
        eleven = run(c,1,resume_state=ten['resume_state'],expected_resume_sha256=ten['resume_sha256'])
        self.assertEqual(eleven['observations']['first_bound_event'],11)
        self.assertEqual(eleven['observations']['first_search_witness_event'],11)
        self.assertTrue(eleven['primal_witnesses'])
        w = next(w for w in eleven['primal_witnesses'] if F(w['t']) == 9)
        self.assertEqual(w['holding_count'],10)
        self.assertTrue(all(F(v)==F(1,10) for v in w['weights'].values()))
        self.assertEqual(F(w['objectives']['variance']),F(1,10))
        self.assertEqual(F(w['objectives']['turnover']),F(9,10))
        self.assertEqual(F(w['cash_after']),0)
        self.assertEqual(sum(F(v) for v in w['final_quantities'].values()),10)
        self.assertTrue(all(w['risk_checks'].values()))

    def test_multiclass_all_supports_exact_oracle_and_canonical_depth_first_order(self):
        _,c = fixture(2,classes=2,epsilon='10')
        out = run(c,150)
        groups = [['S00_0','S00_1'],['S01_0','S01_1']]
        expected = {tuple(sorted(['OLD']+[s for s in choices if s]))
                    for choices in product(*([None]+g for g in groups))}
        actual = [tuple(s) for s in out['resume_state']['expanded_supports']]
        self.assertEqual(set(actual),expected)
        self.assertEqual(len(actual),len(set(actual)))
        self.assertEqual(actual[0],('OLD','S00_0','S01_0'))
        self.assertEqual(out['status'],'CERTIFIED_EPSILON_TRAINING_OBJECTIVE_COVER')
        self.assertTrue(out['zero_coefficient_proofs'])
        for row in out['all_k_support_coverage']:
            self.assertEqual(int(row['expanded_support_count']),sum(len(s)==row['holding_count'] for s in expected))
            self.assertEqual(row['unexpanded_support_count'],'0')
        partial = run(c,7)
        for row in partial['all_k_support_coverage']:
            self.assertEqual(int(row['expanded_support_count'])+int(row['unexpanded_support_count']),int(row['frozen_legal_support_count']))

    def test_region_residual_cannot_starve_support_k_and_fifo_aging(self):
        _,c = fixture(4,covariance_ones=True)
        out = run(c,40)
        trace = out['resume_state']['event_trace']
        support = [t for t in trace if t['lane']=='SUPPORT' and t['warmup_complete_before']]
        self.assertEqual([t['target_k'] for t in support[:16]],[1,2,3,4]*4)
        self.assertTrue(out['residual_regions'])
        after = [t['lane'] for t in trace if t['event']>5]
        self.assertEqual(after,['REGION' if i%2==0 else 'SUPPORT' for i in range(len(after))])
        region = [t for t in trace if t['lane']=='REGION']
        self.assertEqual([t['enqueue_serial'] for t in region],list(range(len(region))))
        for t in region:
            self.assertEqual(t['region_wait_turns'],t['task']['older_refinable_tasks_at_enqueue'])
        for t in out['residual_regions']:
            self.assertLessEqual(t['current_age_region_turns'],t['older_refinable_tasks_at_enqueue'])
        self.assertTrue(out['observations']['warmup_complete'])

    def test_json_resume_exact_prefix_and_rehashed_state_attacks(self):
        _,c = fixture(3,classes=2)
        first = run(c,11)
        resumed = run(c,7,resume_state=json.loads(json.dumps(first['resume_state'])),expected_resume_sha256=first['resume_sha256'])
        self.assertEqual(resumed['resume_state'],run(c,18)['resume_state'])
        attacks = [lambda s:s.update(warmup_complete=False),lambda s:s.update(warmup_target_k=1),
            lambda s:s.update(preferred_lane='SUPPORT' if s['preferred_lane']=='REGION' else 'REGION'),
            lambda s:s.update(support_k_cursor=999),lambda s:s['region_fifo'][0].update(enqueue_serial=999),
            lambda s:s['region_fifo'][0].update(enqueued_after_region_turn=-1),
            lambda s:s['support_stacks_by_k']['2'].reverse(),lambda s:s['support_stacks_by_k']['2'].pop(),
            lambda s:s['support_stacks_by_k']['2'].append(deepcopy(s['support_stacks_by_k']['2'][0])),
            lambda s:s['search_registration'].update(budget_scope='TOTAL_OPERATIONS'),
            lambda s:s['counters'].update(bound_checks=999)]
        for mutate in attacks:
            bad = deepcopy(first['resume_state']);mutate(bad)
            self.assertNotEqual(bad,first['resume_state'])
            with self.assertRaises(ValueError):run(c,0,resume_state=bad,expected_resume_sha256=P.digest(bad))

    def test_v1_checkpoint_cannot_migrate_even_with_new_schema_and_rehash(self):
        base,c = fixture(1)
        old = V1.search_synthetic_continuous_frontier(competition=base,work_budget=2)['resume_state']
        with self.assertRaisesRegex(ValueError,'V1 migration forbidden'):run(c,0,resume_state=old,expected_resume_sha256=P.digest(old))
        changed = deepcopy(old)
        changed.update(schema=V2.CHECKPOINT,competition_id=c['competition_id'],search_registration=deepcopy(V2.REGISTRATION))
        with self.assertRaisesRegex(ValueError,'replay mismatch'):run(c,0,resume_state=changed,expected_resume_sha256=P.digest(changed))
        with self.assertRaisesRegex(ValueError,'V2 competition'):run(base,0)

    def test_actual_component_counts_setup_replay_and_zero_budget(self):
        _,c = fixture(2)
        bound,primal,poly = C.bound_region,C._witness,V2._coefficient_polynomial
        with patch.object(C,'bound_region',wraps=bound) as bounds, \
             patch.object(C,'_witness',wraps=primal) as primals, \
             patch.object(P,'_witness',wraps=P._witness) as controls, \
             patch.object(C,'split_region',wraps=C.split_region) as splits, \
             patch.object(V2,'_coefficient_polynomial',wraps=poly) as polys:
            out = run(c,16)
        work = out['work'];counts=work['cumulative_search_components'];setup=work['setup_components']
        self.assertEqual(bounds.call_count,counts['bound_checks'])
        self.assertEqual(primals.call_count,counts['witness_formula_checks'])
        self.assertEqual(controls.call_count,1)
        self.assertEqual(splits.call_count,counts['region_split_attempts'])
        self.assertEqual(polys.call_count,counts['coefficient_calls']+setup['coefficient_calls'])
        self.assertEqual(sum(len(t.args[0]) for t in polys.call_args_list),counts['coefficient_factor_visits']+setup['coefficient_factor_visits'])
        self.assertEqual(counts['support_expansions']+counts['support_materializations']+counts['region_events'],16)
        frozen = run(c,0,resume_state=out['resume_state'],expected_resume_sha256=out['resume_sha256'])
        self.assertEqual(frozen['work']['replay_component_counts'],counts)
        self.assertEqual(frozen['work']['new_search_events'],0)
        self.assertEqual(frozen['work']['zero_control_audits'],1)
        self.assertEqual(frozen['resume_state'],out['resume_state'])

    def test_math_certificates_parent_regions_and_per_k_scope_remain_bound(self):
        _,c = fixture(2)
        out = run(c,18)
        ledger = {b['certificate_id']:b for b in out['global_bound_regions']}
        for b in ledger.values():V2.verify_fair_region_certificate(competition=c,region=b['region'],certificate=b)
        for task in out['residual_regions']:
            if 'inherited_parent_bound' in task:
                relation = V2.verify_fair_inherited_bound(competition=c,child_region=task['region'],parent_certificate=task['inherited_parent_bound'])
                self.assertEqual(relation,task['inherited_parent_relation'])
        for entry in out['exact_partition_ledger']:
            self.assertEqual(entry['children'],list(C.split_region(ledger[entry['parent_certificate_id']]['region'])))
        _,loose = fixture(2,epsilon='10')
        covered = run(loose,30)
        for a in covered['archived_regions']:
            if 'cover' not in a:continue
            V2.verify_fair_cover_certificate(competition=loose,region=a['region'],bound=a['bound'],certificate=a['cover'])
            bad = deepcopy(a['cover']);bad['scope']='GLOBAL'
            with self.assertRaisesRegex(ValueError,'PER_K'):V2.verify_fair_cover_certificate(competition=loose,region=a['region'],bound=a['bound'],certificate=bad)
        self.assertTrue(all(a['economic_domain_retained'] for a in covered['archived_regions']))

    def test_fractional_dollars_fee_and_explicit_wrapper_no_fake_identity(self):
        base,c = fixture(1,old='0.5',prior='1',fee='2500')
        self.assertNotEqual(c['competition_id'],base['competition_id'])
        self.assertEqual(c['mathematical_competition_id'],base['competition_id'])
        w = V2.verify_fair_witness(competition=c,support_security_ids=['OLD','S00_0'],reciprocal_total_stock='2/3',weights={'OLD':'1/3','S00_0':'2/3'})
        self.assertEqual(w['final_quantities'],{'OLD':'1/2','S00_0':'1'})
        self.assertEqual(w['fee'],'1/4');self.assertEqual(w['cash_after'],'3/4')
        self.assertEqual(w['objectives']['turnover'],'2/5')
        changed = deepcopy(c);changed['core']['cash']='9';changed['competition_id']=P.digest({k:v for k,v in changed.items() if k!='competition_id'})
        with self.assertRaisesRegex(ValueError,'drift'):run(changed,0)
        self.assertTrue(all(v is False for v in run(c,0)['authority'].values()))

    def test_zero_root_coefficients_typed_branches_and_no_source_io(self):
        _,c = fixture(2,old={'OLD':'0.5','S00_0':'0.5'})
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No source IO')):
            out = run(c,12)
        k1 = out['all_k_support_coverage'][0]
        self.assertEqual(k1['frozen_legal_support_count'],'0')
        self.assertEqual(k1['structural_zero_domain_certificate']['reason'],'BELOW_FROZEN_POSITIVE_HOLDING_COUNT')
        _,c = fixture(2,cash='0')
        out = run(c,40)
        self.assertEqual(out['status'],'CERTIFIED_EPSILON_TRAINING_OBJECTIVE_COVER')
        self.assertTrue(all(w['support']==['OLD'] for w in out['primal_witnesses']))
        _,c = fixture(2,buffer='3')
        self.assertEqual(run(c,0)['branch'],'NEGATIVE_CASH_BUDGET_EMPTY')
        _,c = fixture(2,old={})
        out = run(c,0)
        self.assertEqual(out['branch'],'V_ZERO_T_POSITIVE_UNATTAINED_TRAINING_INFIMUM')
        self.assertIsNone(out['zero_buy_control']['variance'])
        self.assertTrue(out['implicit_support_forest'])
        _,c = fixture(2,old={},cash='0',prior='1',buffer='1')
        self.assertEqual(run(c,0)['branch'],'V_ZERO_T_ZERO_ONLY_CASH')
        for bad in (True,-1,0.5):
            with self.assertRaises(ValueError):run(c,bad)

    def test_first_leaf_linear_events_small_dimensions_without_pool_cap(self):
        for n in range(1,6):
            _,c = fixture(n)
            out = run(c,n+2)
            self.assertEqual(out['observations']['first_leaf_event'],n+1)
            self.assertEqual(out['observations']['first_bound_event'],n+2)
            self.assertEqual(out['observations']['first_search_witness_event'],n+2)
            for row in out['all_k_support_coverage']:
                self.assertEqual(int(row['expanded_support_count'])+int(row['unexpanded_support_count']),int(row['frozen_legal_support_count']))


if __name__ == '__main__':unittest.main()

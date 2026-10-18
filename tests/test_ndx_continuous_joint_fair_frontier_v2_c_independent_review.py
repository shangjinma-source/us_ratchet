"""Independent bounded V2 event-domain/USD oracles; never old suite or real fit."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import builtins,json,unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from backtest import ndx_variable_cardinality_new_cash_problem_research as A
from backtest import ndx_continuous_joint_projection_research as P
from backtest import ndx_continuous_joint_certificates_research as C
from backtest import ndx_continuous_joint_fair_frontier_research_v2 as S
from test_ndx_joint_new_cash_competition_frontier_c_independent_review import raw_case

def problem(groups=(1,1),eps='0',ones=False):
    raw=raw_case();ids=['OLD']+[f'N{i}_{j}' for i,n in enumerate(groups) for j in range(n)]
    raw['evidence_facts']['conditional_inventory']=[dict(security_id=s,issuer_id='IOLD' if s=='OLD' else 'I'+s.split('_')[0][1:],ticker=s,risk_chain=s)for s in ids]
    template=deepcopy(raw['price_context']['prices']['C'])
    raw['price_context']['prices']={s:deepcopy(template)for s in ids};raw['price_context']['prices']['OLD']['price']='2'
    raw['prior_book']['holdings']={'OLD':'0.5'};raw['prior_book']['cash']='0';raw['cash_event']['amount']=str(sum(groups));raw['policy']['transaction_cost_bps']='0'
    raw['domain_kind']='CONTINUOUS_INCREMENTAL_DOLLARS'
    ids=sorted(ids);cov=dict(schema='EXPLICIT_SYNTHETIC_RATIONAL_COVARIANCE_V1',security_ids=ids,values=[[1 if ones else int(i==j)for j in range(len(ids))]for i in range(len(ids))],return_unit='ONE_STEP_DECIMAL_RETURN_SQUARED',available_at='2026-09-30T19:00:00Z',timing_scope='SYNTHETIC_TRAINING_ONLY')
    base=P.prepare_synthetic_continuous_competition(prepared_problem_A=A.prepare_synthetic_new_cash_problem(synthetic_case=raw),synthetic_covariance=cov,epsilon_variance=eps,epsilon_turnover=eps)
    return raw,base,S.prepare_synthetic_fair_continuous_competition(mathematical_competition=base)

def run(c,n,**kw):return S.search_synthetic_fair_continuous_frontier(competition=c,work_budget=n,**kw)
def included(region,coordinates):
    return all((F(a['lower'])<coordinates[k]<F(a['upper']))or(coordinates[k]==F(a['lower']) and a['lower_closed'])or(coordinates[k]==F(a['upper']) and a['upper_closed']) for k,a in region['axes'].items())

class FairV2IndependentTests(unittest.TestCase):
    def test_nine_first_leaf_bound_real_USD_fractional_old_and_original_risk(self):
        raw,base,c=problem((1,)*9);ten=run(c,10)
        self.assertEqual((ten['observations']['first_leaf_event'],ten['observations']['first_bound_event']),(10,None))
        self.assertEqual(ten['work']['cumulative_search_components']['support_materializations'],1)
        self.assertEqual(sum(int(r['frozen_legal_support_count'])for r in ten['all_k_support_coverage']),512)
        self.assertEqual(sum(int(r['unexpanded_support_count'])for r in ten['all_k_support_coverage']),511)
        out=run(c,1,resume_state=ten['resume_state'],expected_resume_sha256=ten['resume_sha256'])
        self.assertEqual((out['observations']['first_bound_event'],out['observations']['first_search_witness_event']),(11,11))
        w=next(w for w in out['primal_witnesses'] if F(w['t'])==9)
        quantities={s:F(v)for s,v in w['final_quantities'].items()};self.assertEqual(quantities['OLD'],F(1,2));self.assertTrue(all(q==1 for s,q in quantities.items()if s!='OLD'))
        amounts={s:q*F(raw['price_context']['prices'][s]['price'])for s,q in quantities.items()}
        old=F(1);buy=sum(amounts.values())-old;wealth=old+9;fee=F(0);cash=9-buy-fee
        self.assertEqual((buy,cash,F(w['fee']),F(w['cash_after'])),(F(9),F(0),fee,cash))
        weights={s:v/sum(amounts.values())for s,v in amounts.items()};self.assertEqual({s:F(v)for s,v in w['weights'].items()},weights)
        self.assertEqual(F(w['objectives']['variance']),sum(v*v for v in weights.values()))
        self.assertEqual(F(w['objectives']['turnover']),buy/wealth)
        risk=raw['policy']['risk_parameters'];tau=F(1,10**9);top=sorted(weights.values(),reverse=True)
        self.assertLessEqual(top[0],F(risk['max_single_weight'])+tau);self.assertGreaterEqual(top[-1]+tau,F(risk['min_single_weight']))
        self.assertLessEqual(sum(top[:3]),F(risk['top_weight_cap'])+tau)
        self.assertGreaterEqual(1/sum(v*v for v in weights.values())+tau,F(risk['minimum_effective_n_ratio'])*10)
        self.assertLessEqual(max(weights.values()),F(risk['risk_chain_top1_cap'])+tau)
        self.assertEqual(c['mathematical_competition'],base);self.assertNotEqual(c['competition_id'],base['competition_id'])

    def test_independent_nonuniform_multiclass_every_support_event_domain_partition(self):
        groups=(2,3);_,_,c=problem(groups,eps='10');out=run(c,100)
        choices=[[None]+[f'N{i}_{j}'for j in range(n)]for i,n in enumerate(groups)]
        oracle={tuple(sorted(['OLD']+[x for x in p if x]))for p in product(*choices)}
        stacks={k:[dict(target_k=k,index=0,chosen=[],composition_count=str(sum(len(s)==k for s in oracle)))]for k in range(1,4)}
        expanded=[];first=True;cursor=1
        def domain(t):
            chosen=set(t['chosen']);i=t['index']
            return {s for s in oracle if len(s)==t['target_k'] and {x for x in s if x!='OLD' and int(x[1:x.index('_')])<i}==chosen}
        for event in out['resume_state']['event_trace']:
            if event['lane']!='SUPPORT':continue
            active=sorted(k for k,v in stacks.items()if v)
            k=max(active)if first else next((k for k in active if k>=cursor),active[0]);cursor=k+1
            task=stacks[k].pop();self.assertEqual(event['target_k'],k);self.assertEqual(event['task'],task)
            previous=domain(task);self.assertEqual(int(task['composition_count']),len(previous))
            if task['index']==len(groups):
                self.assertEqual(len(previous),1);expanded.extend(previous);first=False
            else:
                i=task['index'];children=[];sets=[]
                for sid in [f'N{i}_{j}'for j in range(groups[i])]+[None]:
                    t=dict(target_k=k,index=i+1,chosen=task['chosen']+([]if sid is None else[sid]))
                    subset=domain(t)
                    if subset:t['composition_count']=str(len(subset));children.append(t);sets.append(subset)
                self.assertEqual(set().union(*sets),previous)
                self.assertEqual(sum(map(len,sets)),len(previous));stacks[k].extend(reversed(children))
            for kk in stacks:
                pending=[domain(t)for t in stacks[kk]];actual={s for s in expanded if len(s)==kk}
                self.assertEqual(sum(map(len,pending))+len(actual),sum(len(s)==kk for s in oracle))
        self.assertEqual(set(expanded),oracle);self.assertEqual(len(expanded),len(oracle));self.assertEqual([len(s)for s in oracle].count(3),6)
        self.assertEqual(expanded[0],('N0_0','N1_0','OLD'))
        self.assertEqual(out['resume_state']['expanded_supports'],[list(s)for s in expanded])
        self.assertTrue(all(r['unexpanded_support_count']=='0'for r in out['all_k_support_coverage']))

    def test_actual_fair_trace_FIFO_aging_and_halfopen_parent_math(self):
        _,_,c=problem((1,1,1),ones=True);out=run(c,48);trace=out['resume_state']['event_trace'];support=[t for t in trace if t['lane']=='SUPPORT' and t['warmup_complete_before']]
        # Check service against an independently reconstructed active-stack cursor rather than a fixed first16 literal.
        for row in out['all_k_support_coverage']:
            services=[t['event']for t in trace if t['lane']=='SUPPORT' and t['target_k']==row['holding_count']]
            self.assertEqual(row['service']['support_services'],len(services));self.assertEqual(row['service']['last_support_event'],services[-1]if services else None)
        lanes=[t['lane']for t in trace if t['event']>4]
        self.assertEqual(lanes,['REGION'if i%2==0 else'SUPPORT'for i in range(len(lanes))])
        region=[t for t in trace if t['lane']=='REGION'];self.assertEqual([t['enqueue_serial']for t in region],list(range(len(region))))
        for t in region:self.assertEqual(t['region_wait_turns'],t['task']['older_refinable_tasks_at_enqueue'])
        for t in out['residual_regions']:self.assertLessEqual(t['current_age_region_turns'],t['older_refinable_tasks_at_enqueue'])
        bounds={b['certificate_id']:b for b in out['global_bound_regions']}
        self.assertTrue(out['exact_partition_ledger'])
        for entry in out['exact_partition_ledger']:
            parent=bounds[entry['parent_certificate_id']];left,right=entry['children'];axis=next(a for a in parent['region']['axes'] if left['axes'][a]!=parent['region']['axes'][a]);mid=F(left['axes'][axis]['upper'])
            self.assertFalse(left['axes'][axis]['upper_closed']);self.assertTrue(right['axes'][axis]['lower_closed'])
            point={k:(F(a['lower'])+F(a['upper']))/2 for k,a in parent['region']['axes'].items()}
            for value in (F(parent['region']['axes'][axis]['lower']),mid,F(parent['region']['axes'][axis]['upper'])):
                point[axis]=value;self.assertEqual(int(included(left,point))+int(included(right,point)),int(included(parent['region'],point)))
            for child,relation in zip(entry['children'],entry['relations']):
                self.assertEqual(S.verify_fair_inherited_bound(competition=c,child_region=child,parent_certificate=parent),relation)
        bad=deepcopy(out['residual_regions'][0]['region']);bad['support']=bad['support'][:-1]
        task=out['residual_regions'][0]
        if 'inherited_parent_bound'in task:
            with self.assertRaises(ValueError):S.verify_fair_inherited_bound(competition=c,child_region=bad,parent_certificate=task['inherited_parent_bound'])

    def test_actual_components_resume_prefix_and_coordinated_rehash_domain_omission(self):
        _,_,c=problem((2,1));first=run(c,12)
        originals=dict(bound=C.bound_region,formula=C._witness,control=P._witness,split=C.split_region,cover=C.cover_region,polynomial=S._coefficient_polynomial,support=S._support_event,region=S._region_event)
        with patch.object(C,'bound_region',wraps=originals['bound'])as bounds,patch.object(C,'_witness',wraps=originals['formula'])as formulas,patch.object(P,'_witness',wraps=originals['control'])as controls,patch.object(C,'split_region',wraps=originals['split'])as splits,patch.object(C,'cover_region',wraps=originals['cover'])as covers,patch.object(S,'_coefficient_polynomial',wraps=originals['polynomial'])as polys,patch.object(S,'_support_event',wraps=originals['support'])as supports,patch.object(S,'_region_event',wraps=originals['region'])as regions:
            out=run(c,9,resume_state=json.loads(json.dumps(first['resume_state'])),expected_resume_sha256=first['resume_sha256'])
        work=out['work'];counts=work['cumulative_search_components'];setup=work['setup_components']
        self.assertEqual((work['new_search_events'],work['resume_prefix_validation_events'],work['zero_control_audits']),(9,12,1))
        self.assertEqual(bounds.call_count,counts['bound_checks']);self.assertEqual(formulas.call_count,counts['witness_formula_checks']);self.assertEqual(controls.call_count,1)
        self.assertEqual(covers.call_count,counts['coverage_checks']);self.assertEqual(splits.call_count,counts['region_split_attempts'])
        self.assertEqual(supports.call_count,counts['support_expansions']+counts['support_materializations']);self.assertEqual(regions.call_count,counts['region_events'])
        self.assertEqual(polys.call_count,setup['coefficient_calls']+counts['coefficient_calls'])
        self.assertEqual(sum(len(call.args[0])for call in polys.call_args_list),setup['coefficient_factor_visits']+counts['coefficient_factor_visits'])
        self.assertEqual(work['replay_component_counts'],first['work']['cumulative_search_components'])
        self.assertEqual(out['resume_state'],run(c,21)['resume_state'])
        base=out['resume_state'];changes=[lambda s:s['support_stacks_by_k']['2'].clear(),lambda s:s['region_fifo'].pop(),lambda s:s.update(warmup_complete=False),lambda s:s.update(support_k_cursor=1 if s['support_k_cursor']!=1 else 99),lambda s:s['partition_ledger'].clear(),lambda s:s['region_fifo'][0].update(enqueue_serial=999),lambda s:s['counters'].update(coefficient_calls=999)]
        for change in changes:
            bad=deepcopy(base);change(bad);self.assertNotEqual(bad,base)
            with self.assertRaises(ValueError):run(c,0,resume_state=bad,expected_resume_sha256=P.digest(bad))

    def test_explicit_V2_registration_V1_rejection_no_IO_strict_authority_and_perk(self):
        _,base,c=problem((1,1),eps='10');out=run(c,25)
        for archive in out['archived_regions']:
            if 'cover'not in archive:continue
            cover=archive['cover'];S.verify_fair_cover_certificate(competition=c,region=archive['region'],bound=archive['bound'],certificate=cover)
            bad=deepcopy(cover);bad['scope']='GLOBAL'
            with self.assertRaises(ValueError):S.verify_fair_cover_certificate(competition=c,region=archive['region'],bound=archive['bound'],certificate=bad)
        with self.assertRaises(ValueError):run(base,0)
        bad=deepcopy(out['resume_state']);bad['schema']='SYNTHETIC_CONTINUOUS_CHECKPOINT_V1'
        with self.assertRaisesRegex(ValueError,'V1 migration'):run(c,0,resume_state=bad,expected_resume_sha256=P.digest(bad))
        for mutate in (lambda v:v['search_registration'].update(region_order='PRIORITY_BY_BEST_VARIANCE'),lambda v:v['core'].update(T='999'),lambda v:v['authority'].update(execution_authorized=0)):
            bad=deepcopy(c);mutate(bad);bad['competition_id']=P.digest({k:v for k,v in bad.items()if k!='competition_id'})
            with self.assertRaises(ValueError):run(bad,0)
        ZoneInfo('UTC')
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No source IO')),patch.object(builtins,'open',side_effect=AssertionError('No source IO')):empty=run(c,0)
        self.assertTrue(all(v is False for v in empty['authority'].values()));self.assertIsNone(empty['current_account']);self.assertIsNone(empty['current_new_money']);self.assertEqual(empty['plan_rows'],[])

if __name__=='__main__':unittest.main()

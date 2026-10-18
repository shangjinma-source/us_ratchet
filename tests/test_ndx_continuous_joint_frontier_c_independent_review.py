"""Independent rational USD/Gram/partition oracles; only tiny synthetic cases."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import builtins
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from backtest import ndx_variable_cardinality_new_cash_problem_research as A
from backtest import ndx_continuous_joint_projection_research as P
from backtest import ndx_continuous_joint_certificates_research as C
from backtest import ndx_continuous_joint_frontier_research as S
from test_ndx_joint_new_cash_competition_frontier_c_independent_review import raw_case

def prepare(raw=None,matrix=None,eps='0'):
    raw=raw_case() if raw is None else raw
    raw['domain_kind']='CONTINUOUS_INCREMENTAL_DOLLARS'
    ids=sorted(raw['price_context']['prices'])
    matrix=[[d if i==j else 0 for j in range(4)] for i,d in enumerate((4,9,1,1))] if matrix is None else matrix
    cov=dict(schema='EXPLICIT_SYNTHETIC_RATIONAL_COVARIANCE_V1',security_ids=ids,values=matrix,return_unit='ONE_STEP_DECIMAL_RETURN_SQUARED',available_at='2026-09-30T19:00:00Z',timing_scope='SYNTHETIC_TRAINING_ONLY')
    return P.prepare_synthetic_continuous_competition(prepared_problem_A=A.prepare_synthetic_new_cash_problem(synthetic_case=raw),synthetic_covariance=cov,epsilon_variance=eps,epsilon_turnover=eps)

def witness(c,support,y,weights):
    return P.verify_continuous_witness(competition=c,support_security_ids=support,reciprocal_total_stock=y,weights=weights)

def membership(region,values):
    for k,a in region['axes'].items():
        v=values[k];lo,hi=F(a['lower']),F(a['upper'])
        if v<lo or v>hi or v==lo and not a['lower_closed'] or v==hi and not a['upper_closed']:return False
    return True

class ContinuousIndependentTests(unittest.TestCase):
    def test_actual_USD_fractional_frozen_fee_full_cash_and_exact_nonbuy(self):
        raw=raw_case();raw['evidence_facts']['conditional_exclusions']={'A1':'SYNTHETIC_NONBUY'};c=prepare(raw)
        w=witness(c,['A1','B','C'],'5/21',{'A1':'5/21','B':'8/21','C':'8/21'})
        # From raw q=.5,p=2,priorcash1,event3; independent USD amounts.
        inc={'A1':F(0),'B':F(8,5),'C':F(8,5)};t=sum(inc.values());fee=t/4;cash=4-t-fee
        self.assertEqual({s:F(v) for s,v in w['increments'].items()},inc)
        self.assertEqual(w['final_quantities'],{'A1':'1/2','B':'4/5','C':'8/5'})
        self.assertEqual(F(w['fee']),fee);self.assertEqual(F(w['cash_after']),cash)
        self.assertEqual(F(w['objectives']['turnover']),t/5);self.assertEqual(F(w['objectives']['variance']),F(76,147))
        self.assertEqual(F(1)+t+cash,5-fee)
        project=P.project_frozen_support(competition=c,support_security_ids=['A1','B','C'],total_buy_notional='16/5')
        self.assertEqual(project['weights']['A1']['kind'],'EXACT_EQUALITY')
        with self.assertRaisesRegex(ValueError,'exact equality'):witness(c,['A1','B'],'5/21',{'A1':'6/21','B':'15/21'})
        with self.assertRaisesRegex(ValueError,'Issuer'):witness(c,['A1','A2'],'1/2',{'A1':'1/2','A2':'1/2'})

    def test_Gram_PSD_plane_global_proof_and_forged_bounds(self):
        # Independent S=G^T G; PSD proof is sum of exact squares, not sample count.
        G=((2,0,1,0),(0,1,0,1));mat=[[sum(g[i]*g[j] for g in G) for j in range(4)] for i in range(4)]
        c=prepare(matrix=mat);support=['A1','B','C'];r=C.root_region(c,support);u={'A1':F(1,5),'B':F(3,10),'C':F(1,2)}
        bound=C.bound_region(c,r,{s:str(v) for s,v in u.items()});ids=['A1','A2','B','C'];vec=[u.get(s,F(0)) for s in ids]
        su=[sum(F(mat[i][j])*vec[j] for j in range(4)) for i in range(4)];grad={s:2*su[ids.index(s)] for s in support};constant=-sum(vec[i]*su[i] for i in range(4))
        self.assertEqual({s:F(v) for s,v in bound['supporting_plane']['gradient'].items()},grad)
        self.assertEqual(F(bound['supporting_plane']['constant']),constant)
        lower={s:max(F(0),F(5,21) if s=='A1' else F(0)) for s in support};mass=1-sum(lower.values());minimum=dict(lower)
        for s in sorted(support,key=lambda s:(grad[s],s)):
            add=min(mass,1-minimum[s]);minimum[s]+=add;mass-=add
        self.assertEqual(F(bound['variance_lower']),max(F(0),constant+sum(grad[s]*minimum[s] for s in support)))
        for t,share in product((F(1,10),F(1),F(16,5)),(F(1,4),F(1,2),F(3,4))):
            weights={'A1':1/(1+t),'B':t*share/(1+t),'C':t*(1-share)/(1+t)};x=[weights.get(s,F(0)) for s in ids];delta=[x[i]-vec[i] for i in range(4)]
            f=sum(sum(g[i]*x[i] for i in range(4))**2 for g in G);plane=constant+sum(grad[s]*weights[s] for s in support)
            remainder=sum(sum(g[i]*delta[i] for i in range(4))**2 for g in G)
            self.assertEqual(f-plane,remainder);self.assertGreaterEqual(f,F(bound['variance_lower']))
        C.verify_continuous_region_certificate(competition=c,region=r,certificate=bound)
        for name in ('variance_lower','turnover_lower'):
            bad=deepcopy(bound);bad[name]='99';bad['certificate_id']=P.digest({k:v for k,v in bad.items() if k!='certificate_id'})
            with self.assertRaises(ValueError):C.verify_continuous_region_certificate(competition=c,region=r,certificate=bad)

    def test_full_issuer_forest_coefficients_halfopen_partition_and_inherited_bound(self):
        c=prepare();valid=[['A1'],['A1','B'],['A1','C'],['A1','B','C']]
        for budget in (0,1,3,7,12):
            out=S.search_synthetic_continuous_frontier(competition=c,work_budget=budget)
            expanded=out['resume_state']['expanded_supports'];self.assertEqual(len(expanded),len({tuple(x) for x in expanded}));self.assertTrue(all(s in valid for s in expanded))
            for k in (1,2,3):
                true=sum(len(s)==k for s in valid);row=out['all_k_support_coverage'][k-1]
                self.assertEqual(int(row['frozen_legal_support_count']),true)
                self.assertEqual(int(row['expanded_support_count'])+int(row['unexpanded_support_count']),true)
                forest=sum(int(f['per_k_composition_counts'][str(k)]) for f in out['implicit_support_forest'])
                self.assertEqual(forest,int(row['unexpanded_support_count']))
        parent=C.root_region(c,['A1','B']);bound=C.bound_region(c,parent);left,right=C.split_region(parent)
        changed=next(k for k in parent['axes'] if left['axes'][k]!=parent['axes'][k]);m=F(left['axes'][changed]['upper'])
        values={k:(F(a['lower'])+F(a['upper']))/2 for k,a in parent['axes'].items()}
        for value in (F(parent['axes'][changed]['lower']),m,F(parent['axes'][changed]['upper'])):
            values[changed]=value;self.assertEqual(int(membership(left,values))+int(membership(right,values)),int(membership(parent,values)))
        relation=C.verify_inherited_parent_bound(competition=c,child_region=left,parent_certificate=bound)
        self.assertEqual(relation['parent_region_id'],P.digest(parent));self.assertEqual(bound['region'],parent)
        # Left open midpoint cannot be closed by an allegedly inherited grandchild.
        bad=deepcopy(left);bad['axes'][changed]['upper_closed']=True
        leftbound=C.bound_region(c,left)
        with self.assertRaisesRegex(ValueError,'ownership'):C.verify_inherited_parent_bound(competition=c,child_region=bad,parent_certificate=leftbound)

    def test_same_k_cover_scope_real_turnover_and_original_tau(self):
        c=prepare(eps='10');r=C.root_region(c,['A1','B']);bound=C.bound_region(c,r)
        w3=witness(c,['A1','B','C'],'1/2',{'A1':'1/2','B':'1/4','C':'1/4'})
        w2=witness(c,['A1','B'],'1/2',{'A1':'1/2','B':'1/2'})
        with self.assertRaisesRegex(ValueError,'same k'):C.cover_region(c,r,bound,w3)
        cover=C.cover_region(c,r,bound,w2);cover['scope']='GLOBAL'
        with self.assertRaises(ValueError):C.verify_continuous_cover_certificate(competition=c,region=r,bound=bound,certificate=cover)
        b=C.bound_region(c,r);self.assertEqual(F(b['turnover_span']),(1/F(r['axes']['$y']['lower'])-1/F(r['axes']['$y']['upper']))/5)
        raw=raw_case();raw['policy']['risk_parameters']['minimum_effective_n_ratio']='0.8';cc=prepare(raw)
        weights={'A1':'7500000001/10000000000','B':'2499999999/10000000000'}
        w=witness(cc,['A1','B'],'1/2',weights);self.assertTrue(w['risk_checks']['effective_n']);self.assertGreater(sum(F(v)**2 for v in weights.values()),F(5,8))
        for key,value in [('max_single_weight','0.6'),('min_single_weight','0.3'),('top_weight_cap','0.9'),('risk_chain_top1_cap','0.6')]:
            rr=deepcopy(raw);rr['policy']['risk_parameters'][key]=value
            with self.assertRaisesRegex(ValueError,'risk failed'):witness(prepare(rr),['A1','B'],'1/2',weights)
        with self.assertRaisesRegex(ValueError,'Strict'):witness(cc,['A1','B'],'1',{'A1':'1','B':'0'})

    def test_actual_component_calls_resume_and_rehashed_omissions(self):
        c=prepare();first=S.search_synthetic_continuous_frontier(competition=c,work_budget=8)
        calls={'bounds':0,'formulas':0};bound=C.bound_region;formula=P._witness
        def counted_bound(*a,**k):calls['bounds']+=1;return bound(*a,**k)
        def counted_formula(*a,**k):calls['formulas']+=1;return formula(*a,**k)
        with patch.object(S,'bound_region',counted_bound),patch.object(C,'bound_region',counted_bound),patch.object(S,'_witness',counted_formula),patch.object(C,'_witness',counted_formula):
            out=S.search_synthetic_continuous_frontier(competition=c,work_budget=7,resume_state=first['resume_state'],expected_resume_sha256=first['resume_sha256'])
        counters=out['work_and_replay_counters']['cumulative_search_components']
        self.assertEqual(calls['bounds'],counters['bound_checks']);self.assertEqual(calls['formulas'],counters['witness_formula_checks']+1)
        self.assertEqual(out['work_and_replay_counters']['new_search_events'],7);self.assertEqual(out['work_and_replay_counters']['resume_prefix_validation_events'],8)
        full=S.search_synthetic_continuous_frontier(competition=c,work_budget=15);self.assertEqual(out['resume_state'],full['resume_state'])
        mutate=[lambda s:s['queue'].pop(),lambda s:s['queue'].append(deepcopy(s['queue'][0])),lambda s:s.update(events=99),lambda s:s['counters'].update(bound_checks=999),lambda s:s['partition_ledger'].clear()]
        # Use later state with actual partitions for omitted-region replay attack.
        for change in mutate:
            bad=deepcopy(full['resume_state']);change(bad)
            with self.assertRaises(ValueError):S.search_synthetic_continuous_frontier(competition=c,work_budget=0,resume_state=bad,expected_resume_sha256=P.digest(bad))

    def test_V_zero_and_negative_domains_source_IO_and_false_authority(self):
        raw=raw_case();raw['prior_book']['holdings']={};c=prepare(raw)
        out=S.search_synthetic_continuous_frontier(competition=c,work_budget=0)
        self.assertIn('UNATTAINED',out['status']);self.assertIsNone(out['zero_buy_control']['variance']);self.assertEqual([r['unexpanded_support_count'] for r in out['all_k_support_coverage']],['4','5','2'])
        w=witness(c,['B','C'],'1',{'B':'1/2','C':'1/2'});half=witness(c,['B','C'],'2',{'B':'1/2','C':'1/2'})
        self.assertEqual(w['objectives']['variance'],half['objectives']['variance']);self.assertEqual(F(half['objectives']['turnover']),F(w['objectives']['turnover'])/2)
        raw=raw_case();raw['policy']['minimum_cash_buffer']='5';self.assertIn('EMPTY',S.search_synthetic_continuous_frontier(competition=prepare(raw),work_budget=0)['branch'])
        c=prepare();ZoneInfo('UTC')
        with patch.object(Path,'read_bytes',side_effect=AssertionError('source IO')),patch.object(builtins,'open',side_effect=AssertionError('source IO')):out=S.search_synthetic_continuous_frontier(competition=c,work_budget=2)
        self.assertTrue(all(v is False for v in out['authority'].values()));self.assertIsNone(out['current_account']);self.assertEqual(out['plan_rows'],[])
        bad=deepcopy(c);bad['authority']['execution_authorized']=0;bad['competition_id']=P.digest({k:v for k,v in bad.items() if k!='competition_id'})
        with self.assertRaises(ValueError):S.search_synthetic_continuous_frontier(competition=bad,work_budget=0)

    def test_BFS_nine_issuer_prefix_delays_search_witness_but_keeps_control(self):
        raw=raw_case();ids=['A1']+['N'+str(i) for i in range(9)]
        raw['evidence_facts']['conditional_inventory']=[dict(security_id=s,issuer_id=s,ticker=s,risk_chain=s) for s in ids]
        template=raw['price_context']['prices']['C'];raw['price_context']['prices']={s:deepcopy(template) for s in ids};raw['price_context']['prices']['A1']['price']='2'
        c=prepare(raw,[[int(i==j) for j in range(10)] for i in range(10)])
        out=S.search_synthetic_continuous_frontier(competition=c,work_budget=512);counts=out['work_and_replay_counters']['cumulative_search_components']
        self.assertEqual(counts['support_expansions'],511);self.assertEqual(counts['support_materializations'],1);self.assertEqual(counts['bound_checks'],0)
        self.assertEqual(out['primal_witnesses'],[]);self.assertEqual(out['zero_buy_control']['holding_count'],1)
        self.assertEqual(sum(int(r['unexpanded_support_count']) for r in out['all_k_support_coverage']),511)
        self.assertEqual(out['status'],'BUDGET_STOPPED_WITH_FULL_RESIDUAL')

if __name__=='__main__':unittest.main()

import itertools,random,unittest
from copy import deepcopy
from fractions import Fraction as F
from unittest.mock import patch
from backtest import quantity_coupled_joint_loss_iterator as module
from backtest import quantity_joint_anchor_loss as loss
from backtest import quantity_integer_box_certificate_prototype as core
from test_quantity_integer_box_certificate_prototype import oracle
import test_quantity_coupled_joint_loss_iterator as author
from test_quantity_small_joint_loss_enumerator import fixture as source_fixture

def context(b_return,c_return):
    inputs,_,sources=author.synthetic()
    inputs['training_scenarios']=[dict(A='2',B=str(b_return),C=str(c_return))]
    p=core.prepare(**inputs);box={s:[0,2] for s in p['ids']};inc={'A':2}
    proof=loss.build(inputs=inputs,box=box,anchor_quantities={s:'0' for s in p['ids']},incumbent=inc,dual_lambda='2/5')
    parent=dict(remaining_box=box,lower_product=proof['lower_product'])
    report=dict(inherited_closed_rows=[{'closed':1}],inherited_fixing_rows=[{'closed':2}],new_rows=[dict(id='other',upper_product='99')])
    sources['expected_loss_binding_sha256']=proof['binding_sha256']
    return inputs,(report,parent,proof,module.pattern_bound(proof),p,inc),sources

class IndependentCoupledIterator(unittest.TestCase):
    def test_strict_interval_against_integer_inequalities(self):
        rng=random.Random(7102)
        for _ in range(200):
            b=F(rng.randint(1,30),3);spent=F(rng.randint(0,30),4);lam=F(rng.randint(1,8),7);cost=F(rng.randint(1,8),5);gap=lam*cost*F(rng.randint(1,9),10);partial=gap*F(rng.randint(0,9),10)
            r=module.strict_interval(spendable=b,other_spend=spent,loss_budget=gap,other_loss=partial,dual_lambda=lam,unit_cost=cost,lo=0,hi=15)
            expected=[q for q in range(16) if spent+cost*q<=b and partial+lam*(b-spent-cost*q)<gap]
            self.assertEqual(list(range(r['first'],r['last']+1)),expected)

    def test_exact_oracle_and_budget_frontier_preserves_improvers(self):
        for br,cr in itertools.product((F(3,2),F(19,10),F(21,10),F(11,5)),(F(1,2),F(3,2))):
            inputs,ctx,src=context(br,cr)
            loss.verify(ctx[2],expected_binding_sha256=src['expected_loss_binding_sha256'])
            with patch.object(module,'_context',return_value=ctx),patch('scipy.optimize.minimize',side_effect=AssertionError('NO SOLVER')):
                complete=module.build(**src);module.verify(complete,**src)
                expected=max([F(ctx[1]['lower_product'])]+[v for v,q in oracle(inputs,ctx[1]['remaining_box'])])
                self.assertEqual(F(complete['candidate_product']),expected)
                for row in complete['ledger']:
                    for _,q in oracle(inputs,ctx[1]['remaining_box']):
                        deviations=[(q.get(a['sid'],0)-a['preferred'])*a['direction'] for a in complete['axes']]
                        if deviations[:len(row['prefix'])]!=row['prefix']:continue
                        if any(d<0 or d>a['max_deviation'] for d,a in zip(deviations,complete['axes'])):continue
                        exact=loss.inspect_point(ctx[2],q)
                        self.assertLessEqual(F(row['prefix_loss_bound']['total_loss_lower']),F(exact['loss']))
                for node_budget,objective_budget in ((0,10000),(2,10000),(4,10000),(100000,0),(100000,1)):
                    c=module.build(**src,node_budget=node_budget,objective_budget=objective_budget);module.verify(c,**src)
                    self.assertLessEqual(c['visited_nodes'],node_budget);self.assertLessEqual(c['objective_evaluations'],objective_budget)
                    checked={tuple(sorted(p['quantities'].items())) for p in c['points']}
                    for v,q in oracle(inputs,c['original_box']):
                        if v<=F(c['original_lower_product']):continue
                        deviations=[(q.get(a['sid'],0)-a['preferred'])*a['direction'] for a in c['axes']]
                        pending=any(deviations[:len(prefix)]==prefix for prefix in c['unsearched_frontier'])
                        self.assertTrue(tuple(sorted(q.items())) in checked or pending)
                    self.assertFalse(c['global_objective_value_optimal'])

    def test_strict_metadata_frontier_and_budget_tamper(self):
        _,ctx,src=context(F(21,10),F(1,2))
        with patch.object(module,'_context',return_value=ctx):
            c=module.build(**src,node_budget=0)
            for key,value in [('objective_evaluations',False),('domain_complete',1),('unsearched_frontier',[]),('other_domains',[])]:
                bad=deepcopy(c);bad[key]=value
                with self.assertRaises(ValueError):module.verify(bad,**src)
            for args in ({'objective_budget':True},{'objective_budget':10001},{'node_budget':100001}):
                with self.assertRaises(ValueError):module.build(**src,**args)
        real_sources,_,_=source_fixture()
        for field in ('expected_parent_report_sha256','expected_tail_sha256','expected_loss_sha256','expected_loss_binding_sha256'):
            with self.assertRaises(ValueError):module.build(**dict(real_sources,**{field:'0'*64}))

if __name__=='__main__':unittest.main()

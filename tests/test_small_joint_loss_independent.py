import itertools,json,random,unittest
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from unittest.mock import patch
from backtest import quantity_small_joint_loss_enumerator as module
from backtest import quantity_saved_anchor_tail_tightening as tail
from backtest import quantity_joint_anchor_loss as loss
from test_quantity_saved_anchor_tail_tightening import setup
from test_quantity_integer_box_certificate_prototype import fixture,oracle

def sources(args,lam):
    ts,_=setup(args);t=tail.build(**ts);tr=json.dumps(t).encode();anchor=json.loads(ts['fixing_sources']['anchor_raw'])
    l=loss.build(inputs=args,box=t['remaining_box'],anchor_quantities=anchor['repaired_quantities'],incumbent=ts['fixing_sources']['incumbent'],dual_lambda=lam);lr=json.dumps(l).encode()
    report=dict(lower_product=t['lower_product'],integer_selected_unchanged=ts['fixing_sources']['incumbent'],new_rows=[dict(id='target',certificate_sha256=sha256(tr).hexdigest()),dict(id='OTHER',certificate_sha256='a'*64)],inherited_closed_rows=[{'keep':1}],inherited_fixing_rows=[{'keep':2}]);rr=json.dumps(report).encode()
    return dict(parent_report_raw=rr,expected_parent_report_sha256=sha256(rr).hexdigest(),target_id='target',tail_raw=tr,expected_tail_sha256=sha256(tr).hexdigest(),tail_sources=ts,loss_raw=lr,expected_loss_sha256=sha256(lr).hexdigest(),expected_loss_binding_sha256=l['binding_sha256']),t,l

class IndependentSmallEnumeration(unittest.TestCase):
    def test_random_oracle_and_necessary_count(self):
        rng=random.Random(818)
        for i in range(16):
            args=fixture();args['fee_bps']=rng.choice(['0','25','3000']);args['minimum_cash_buffer']=rng.choice(['0','1'])
            args['training_scenarios']=[{s:str(F(rng.randint(3,19),10)) for s in 'ABC'} for _ in range(2)]
            src,t,l=sources(args,rng.choice(['0','1/100','1']))
            with patch('scipy.optimize.minimize',side_effect=AssertionError('NO SOLVER')):
                c=module.build(**src);module.verify(c,**src)
            self.assertTrue(c['domain_complete']);self.assertFalse(c['global_objective_value_optimal'])
            points=oracle(args,t['remaining_box']);lower=F(t['lower_product'])
            self.assertEqual(F(c['candidate_product']),max([lower]+[v for v,q in points]))
            saved={tuple(sorted(p['quantities'].items())) for p in c['points']}
            self.assertEqual(len(saved),len(c['points']))
            for value,q in points:
                if value>lower:self.assertIn(tuple(sorted(q.items())),saved)
            # Count all integer points with necessary coordinate loss, including infeasible.
            b=t['remaining_box'];count=0
            for values in itertools.product(*(range(b[s][0],b[s][1]+1) for s in 'ABC')):
                q=dict(zip('ABC',values))
                coordinate_loss=sum((F(l['reduced_coefficients'][s])*(l['preferred_endpoints'][s]-q[s]) for s in 'ABC'),F(0))
                count+=coordinate_loss<F(l['strict_loss_budget'])
            self.assertEqual(len(c['points']),count)
            self.assertLessEqual(count,c['necessary_count_evidence']['count_upper'])
            self.assertEqual(c['other_domains'][0]['id'],'OTHER')

    def test_budget_and_external_source_attacks(self):
        src,t,l=sources(fixture(),'0')
        for node_budget,point_budget in ((0,10000),(1,10000),(200000,0),(200000,1)):
            c=module.build(**src,node_budget=node_budget,point_budget=point_budget);module.verify(c,**src)
            self.assertLessEqual(c['checked_points'],point_budget)
            self.assertLessEqual(c['visited_nodes'],node_budget)
            if not c['domain_complete']:self.assertTrue(c['unsearched_frontier'])
        c=module.build(**src)
        for key,value in [('domain_complete',1),('global_objective_value_optimal',True),('other_domains',[]),('points',[]),('candidate_product','999')]:
            bad=deepcopy(c);bad[key]=value
            if module.canonical(bad)==module.canonical(c):continue
            with self.assertRaises(ValueError):module.verify(bad,**src)
        for field in ('expected_parent_report_sha256','expected_tail_sha256','expected_loss_sha256','expected_loss_binding_sha256'):
            with self.assertRaises(ValueError):module.build(**dict(src,**{field:'0'*64}))

if __name__=='__main__':unittest.main()

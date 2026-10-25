from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json,unittest
from unittest.mock import patch
from backtest import quantity_small_joint_loss_enumerator as m
from backtest import quantity_saved_anchor_tail_tightening as tail
from backtest import quantity_joint_anchor_loss as loss
from test_quantity_saved_anchor_tail_tightening import setup
from test_quantity_integer_box_certificate_prototype import oracle

def raw(v):return json.dumps(v).encode()
def fixture():
 ts,src=setup();t=tail.build(**ts);tr=raw(t);a=json.loads(ts['fixing_sources']['anchor_raw'])
 l=loss.build(inputs=a['binding']['inputs'],box=t['remaining_box'],anchor_quantities=a['repaired_quantities'],incumbent=ts['fixing_sources']['incumbent'],dual_lambda='0');lr=raw(l)
 report=dict(lower_product=t['lower_product'],integer_selected_unchanged=ts['fixing_sources']['incumbent'],new_rows=[dict(id='target',certificate_sha256=sha256(tr).hexdigest()),dict(id='first-unresolved',certificate_sha256='f'*64)],inherited_closed_rows=[{'closed':'unchanged'}],inherited_fixing_rows=[{'slabs':'unchanged'}]);rr=raw(report)
 return dict(parent_report_raw=rr,expected_parent_report_sha256=sha256(rr).hexdigest(),target_id='target',tail_raw=tr,expected_tail_sha256=sha256(tr).hexdigest(),tail_sources=ts,loss_raw=lr,expected_loss_sha256=sha256(lr).hexdigest(),expected_loss_binding_sha256=l['binding_sha256']),a['binding']['inputs'],t
class EnumeratorTests(unittest.TestCase):
 def test_complete_exact_oracle_and_preserved_other_domain(self):
  s,inputs,t=fixture()
  with patch('scipy.optimize.minimize',side_effect=AssertionError('NO SOLVER')):c=m.build(**s);m.verify(c,**s)
  expected=max([F(t['lower_product'])]+[v for v,q in oracle(inputs,t['remaining_box'])])
  self.assertEqual(F(c['candidate_product']),expected);self.assertTrue(c['domain_complete']);self.assertFalse(c['global_objective_value_optimal'])
  self.assertEqual(c['other_domains'][0]['id'],'first-unresolved');self.assertLessEqual(c['checked_points'],c['necessary_count_evidence']['count_upper'])
  self.assertEqual(len({tuple(sorted(p['quantities'].items())) for p in c['points']}),len(c['points']))
 def test_budgets_and_tampering(self):
  s,_,_=fixture();c=m.build(**s,node_budget=0)
  self.assertFalse(c['domain_complete']);self.assertTrue(c['unsearched_frontier']);m.verify(c,**s)
  for key,value in [('global_objective_value_optimal',True),('visited_nodes',False),('other_domains',[]),('unsearched_frontier',[])]:
   bad=deepcopy(c);bad[key]=value
   with self.assertRaises(ValueError):m.verify(bad,**s)
  with self.assertRaises(ValueError):m.build(**s,point_budget=True)
  with self.assertRaises(ValueError):m.build(**dict(s,expected_loss_sha256='0'*64))
 def test_large_necessary_domain_rejected(self):
  s,_,_=fixture()
  with patch.object(m,'MAX_POINTS',0):
   with self.assertRaisesRegex(ValueError,'DOMAIN_TOO_LARGE'):m.build(**s,point_budget=0)
if __name__=='__main__':unittest.main()

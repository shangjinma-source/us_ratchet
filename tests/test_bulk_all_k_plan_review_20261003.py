import unittest,math
from fractions import Fraction as F
from unittest.mock import patch
from test_bulk_all_k_plan_20261003 import args,module

def rat(d):return F(int(d['numerator']),int(d['denominator']))
class LazyPlanIndependentReview(unittest.TestCase):
 def test_each_cardinality_certificate_against_independent_rational_inequality(self):
  with patch.object(module.contracts,'prepare_issuer_shards',side_effect=AssertionError('eager')),patch.object(module.indexing.IssuerCombinationIndex,'unrank',side_effect=AssertionError('unrank')):
   p=module.prepare_lazy_plan(**args())
  planned=excluded=shards=0
  for k,card in enumerate(p['cardinalities'],1):
   count=(math.comb(75,k) if k<=75 else 0)+2*math.comb(75,k-1)
   self.assertEqual(card['combination_count'],count)
   padding=F(k+1,10**12);eps=F(1,10**9)
   comparisons=[('MAX_SINGLE_CAPACITY_BELOW_MINIMUM_SIMPLEX_MASS',k*(F(45,100)+eps)+padding,'<',1-eps-padding),('MIN_SINGLE_REQUIRED_MASS_ABOVE_MAXIMUM_SIMPLEX_MASS',k*(F(5,100)-eps)-padding,'>',1+eps+padding),('TRUE_TOP3_UNIVERSAL_LOWER_BOUND_ABOVE_ACCEPTED_CAP',F(min(3,k),k)*(1-eps-padding),'>',F(8,10)+eps+padding)]
   expected=[r for r in comparisons if (r[1]<r[3] if r[2]=='<' else r[1]>r[3])]
   self.assertEqual(len(card['necessary_bound_certificates']),len(expected))
   for cert,(reason,left,op,right) in zip(card['necessary_bound_certificates'],expected):
    self.assertEqual((cert['reason'],rat(cert['left']),cert['comparison'],rat(cert['right']),rat(cert['strict_gap'])),(reason,left,op,right,abs(left-right)))
   self.assertEqual(card['first_global_shard_ordinal'],shards);self.assertEqual(card['first_global_planned_combination_ordinal'],planned)
   if expected:excluded+=count;self.assertEqual(card['planned_combination_count'],0)
   else:planned+=count;shards+=(count+999)//1000
  self.assertEqual((planned,3*planned,shards),(2074219882745370890,6222659648236112670,2074219882745379))
  self.assertEqual(p['all_k_combination_count'],planned+excluded);self.assertEqual(p['completed_canonical_task_count'],0)
  self.assertFalse(p['risk_feasibility_proven']);self.assertNotIn('shards',p)
 def test_last_slice_and_boolean_and_excluded_cardinality(self):
  p=module.prepare_lazy_plan(**args());c=p['cardinalities'][19];n=c['planned_shard_count']
  last=module.get_shard_slice(p,k=20,shard_start=n-1,shard_stop=n)[0]
  self.assertEqual(last['stop'],c['combination_count']);self.assertEqual(last['remaining_canonical_task_count'],3*(last['stop']-last['start']))
  self.assertEqual(module.get_shard_slice(p,k=76,shard_start=0,shard_stop=0),[])
  for k,a,b in [(76,0,1),(20,0,1001),(20,True,2),(False,0,1),(20,0.0,1)]:
   with self.assertRaises(ValueError):module.get_shard_slice(p,k=k,shard_start=a,shard_stop=b)
 def test_source_conflict_guard(self):
  path=next(iter(module.LOADED))
  with self.assertRaises(ValueError):module.guard({path:'0'*64})
if __name__=='__main__':unittest.main()

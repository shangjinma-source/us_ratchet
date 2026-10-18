from fractions import Fraction as F
from decimal import localcontext,Inexact
import unittest
from backtest import ndx_two_positive_integer_budget_domain_research as m

class Tests(unittest.TestCase):
 def test_small_domains_independent_full_bruteforce(self):
  for a in (F(1,3),F(1),F(5,2)):
   for b in (F(2,7),F(2),F(9,4)):
    for budget in (F(-1),F(0),F(1),F(7,2),F(9)):
     expected=[(x,y)for x in range(1,40)for y in range(1,40)if a*x+b*y<=budget]
     args=dict(a=a,b=b,budget=budget)
     self.assertEqual(m.count_points(**args),len(expected))
     for i,pair in enumerate(expected):
      self.assertEqual(m.rank_point(**args,q1=pair[0],q2=pair[1]),i)
      self.assertEqual(m.unrank_point(**args,rank=i),pair)
     for q in range(31):self.assertEqual(m.prefix_count(**args,max_q1=q),sum(x<=q for x,y in expected))
     rows=[]
     for start in range(0,len(expected)+1,7):rows.extend((r['q1'],r['q2'])for r in m.page_points(**args,start=start,limit=7)['rows'])
     self.assertEqual(rows,expected)
 def test_huge_closed_form_and_nonuniform_roundtrip(self):
  n=10**100;args=dict(a=1,b=1,budget=n);total=n*(n-1)//2
  self.assertEqual(m.count_points(**args),total)
  self.assertEqual(m.unrank_point(**args,rank=0),(1,1));self.assertEqual(m.unrank_point(**args,rank=total-1),(n-1,1))
  page=m.page_points(**args,start=total-3,limit=7);self.assertEqual([(r['q1'],r['q2'])for r in page['rows']],[(n-2,1),(n-2,2),(n-1,1)]);self.assertEqual(page['total_count'],total);self.assertFalse(page['has_more'])
  args=dict(a=F(1001,1000),b=F(37,29),budget=10**70)
  total=m.count_points(**args)
  for rank in (0,1,10**30,total//2,total-1):
   x,y=m.unrank_point(**args,rank=rank);self.assertLessEqual(args['a']*x+args['b']*y,args['budget']);self.assertEqual(m.rank_point(**args,q1=x,q2=y),rank)
 def test_fractional_fee_exact_boundary_and_hostile_decimal_context(self):
  args=dict(a='10.01',b='20.02',budget='30.03')
  with localcontext()as ctx:
   ctx.prec=2;ctx.traps[Inexact]=True
   self.assertEqual(m.count_points(**args),1);self.assertEqual(m.unrank_point(**args,rank=0),(1,1))
   self.assertEqual(m.count_points(**dict(args,budget='30.029999')),0)
  self.assertEqual(m.count_points(a=F(1,3),b=F(2,7),budget=F(13,21)),1)
  empty=m.page_points(a=1,b=2,budget=0,start=0,limit=1);self.assertTrue(empty['empty_domain']);self.assertEqual(empty['rows'],[])
 def test_invalid_inputs_and_engineering_limits_do_not_shrink_domain(self):
  for v in (True,False,1.0,' 1','1 ','1.0','01','+1','1e3','-0','NaN','1/3',''):
   with self.subTest(v=v),self.assertRaises(ValueError):m.count_points(a=v,b=1,budget=4)
  for a,b in ((0,1),(-1,1),(1,0)):
   with self.assertRaises(ValueError):m.count_points(a=a,b=b,budget=3)
  for fn,extra in ((m.rank_point,dict(q1=True,q2=1)),(m.rank_point,dict(q1=1,q2=0)),(m.unrank_point,dict(rank=False)),(m.unrank_point,dict(rank=3)),(m.page_points,dict(start=4,limit=1)),(m.page_points,dict(start=0,limit=True)),(m.page_points,dict(start=0,limit=10001))):
   with self.assertRaises(ValueError):fn(a=1,b=1,budget=3,**extra)
  self.assertEqual(m.count_points(a=1,b=1,budget=3),3)
if __name__=='__main__':unittest.main()

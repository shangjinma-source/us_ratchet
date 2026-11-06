import unittest
from docs.candidates.profitability_roa_boundary_alias_20261106 import migrate
class BoundaryTests(unittest.TestCase):
 def test_preserves_values_and_pending(self):
  prior={'research:security:adbe':2100.,'research:security:odfl':1900.};p={'research:security:odfl'};n,q=migrate(prior,p,'2023-12-29',{})
  self.assertEqual(sum(n.values()),4000.);self.assertEqual(q,{'security:0000878927:679580100'});self.assertEqual(prior['research:security:odfl'],1900.)
 def test_wrong_date_or_unknown(self):
  with self.assertRaises(ValueError):migrate({},set(),'2023-12-28',{})
  with self.assertRaises(ValueError):migrate({'unbound':1},set(),'2023-12-29',{})
if __name__=='__main__':unittest.main()

"""Independent synthetic remaining64 contract review."""
from copy import deepcopy
from collections import Counter
import unittest
import test_ndx_remaining_standard_cash_inputs_20261002 as f
m=f.m
class Review(unittest.TestCase):
 def test_old_absent_target_remains_with_gaps_and_only_target_buyable(self):
  docs,refs=f.fixture();row=docs['inventory']['rows'][1];del row['lane_target']['targets']['s0'];row['gaps']=[{'security_id':'s0','reason':'SAVED_IDENTITY_UNCERTIFIED'}]
  before=deepcopy(docs);r=m.assemble(docs,refs);self.assertEqual(docs,before)
  out=r['rows'][0];self.assertEqual(out['holdings']['s0'],2);self.assertIn('s0',out['securities']);self.assertIn('s0',out['execution_prices'])
  self.assertNotIn('s0',out['allowed_buy_security_ids']);self.assertNotIn('s0',out['target_weights']);self.assertEqual(out['gaps'],row['gaps'])
  self.assertEqual(Counter(x['branch_role'] for x in r['rows']),{'MAIN_LANE':40,'MIGRATION_CONTROL':12,'CASH_RETENTION_CONTROL':12})
  for x in r['rows']:
   for flag in m.FLAGS:self.assertIs(x[flag],False)
   if x['zero_buy_only']:self.assertEqual(x['target_weights'],{});self.assertEqual(x['allowed_buy_security_ids'],[]);self.assertFalse(x['target_l1_applicable'])
 def test_cash_control_target_permission_and_duplicate_amount_rejected(self):
  for attack in ('cash_target','boolshares','pointer','authority','duplicate'):
   docs,refs=f.fixture()
   if attack=='cash_target':docs['inventory']['rows'][30]['lane_target']['targets']={'s0':{'ticker':'T0','issuer_id':'i0','target_weight':1.0}}
   elif attack=='boolshares':docs['inventory']['rows'][1]['baseline']['shares']['s0']=True
   elif attack=='pointer':docs['scenarios']['rows'][2]['parent_row_reference']['json_pointer']='/rows/01'
   elif attack=='authority':docs['inventory']['rows'][1]['securities'][0]['identity_interval_certified']=True
   else:docs['scenarios']['rows'][3]=deepcopy(docs['scenarios']['rows'][2])
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs,refs)
 def test_second_saved_coordinate_and_empty_risk_not_ignored(self):
  for attack in ('coordinate','risk','missingmark'):
   docs,refs=f.fixture();sec=docs['inventory']['rows'][1]['securities'][0]
   if attack=='coordinate':sec['saved_coordinates'].append({'value':{'ticker':'OTHER','issuer_id':'wrong'}})
   elif attack=='risk':sec['risk_observations']=[]
   else:sec['execution_open_observations']=[]
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs,refs)
if __name__=='__main__':unittest.main()

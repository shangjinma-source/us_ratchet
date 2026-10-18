from copy import deepcopy
from decimal import Decimal
import unittest
from test_ndx_multidecision_path_comparison_research import m,fixture


class Review(unittest.TestCase):
 def test_all16_missing_candidate_retains_controls_modes_and_domain(self):
  a=fixture()
  for row in a['candidate_prepared']['rows']:
   for track in row['tracks']:
    track['status']='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT';track['blocking_reasons']=['NO_AUDITED_TARGET'];track['engine_binding']['keyword_arguments']['schedule']=[]
  for slot in a['candidate_slots']:
   slot.update(outcome='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT',result=None,result_reference=None,audit_evidence=None,reason='NO_AUDITED_TARGET')
  before=deepcopy(a);result=m.compare_multidecision_paths(**a)
  self.assertEqual(a,before);self.assertEqual(len(result['rows']),16)
  self.assertEqual(result['counts'],dict(candidate_metrics=0,control_metrics=16,missing_candidate=16))
  self.assertTrue(all(r['candidate']['metrics'] is None and r['control']['metrics'] is not None for r in result['rows']))
  self.assertEqual(set(result['nav_modes_preserved']['modes']),set(m.MODES))
  self.assertFalse(result['formal_comparison_passed'])

 def test_same_terminal_path_keeps_intermediate_drawdown_and_absolute_distance(self):
  a=fixture()
  for role in ('candidate_slots','control_slots'):
   saved=a[role][8]['result']
   for row in saved['daily'][1:]:row['normalized_twr']=2.
   saved['summary']['chained_twr']=1.
  a['candidate_slots'][8]['result']['daily'][1]['normalized_twr']=.5
  result=m.compare_multidecision_paths(**a)['rows'][8]
  self.assertEqual(result['candidate']['metrics']['maximum_drawdown'],dict(numerator='1',denominator='2'))
  delta=result['distances']['candidate_minus_control_absolute_distance']
  self.assertEqual(Decimal(delta['annualized_return']),0);self.assertEqual(delta['maximum_drawdown'],'1/2')
  self.assertIs(result['cohort_statistics_computed'],False)

 def test_no_self_signed_scope_or_duplicate_capital_identity(self):
  for attack in ('audit0','audittrue','initialbool','annualbool','flowidentity','auditref'):
   a=fixture()
   if attack.startswith('audit') and attack!='auditref':a['candidate_slots'][8]['audit_evidence']['inspection']['source_bytes_authenticated']=0 if attack=='audit0' else True
   elif attack=='initialbool':a['candidate_slots'][8]['result']['daily'][0]['normalized_twr']=True
   elif attack=='annualbool':a['nav_metrics']['modes'][m.MODES[1]]['metrics']['annualization']['sessions_per_year']=True
   elif attack=='auditref':a['candidate_slots'][8]['audit_evidence']['result_reference']=dict(a['candidate_slots'][8]['result_reference'],sha256='b'*64)
   else:
    day=a['candidate_prepared']['rows'][4]['tracks'][0]['engine_binding']['keyword_arguments']['closes']['index'][1]
    f=dict(session=day,amount_usd=100.,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='same-receipt',sha256='a'*64))
    for role in ('candidate_prepared','control_prepared'):a[role]['rows'][4]['tracks'][0]['engine_binding']['keyword_arguments']['external_flows']=[f,dict(f,amount_usd=101.)]
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.compare_multidecision_paths(**a)


if __name__=='__main__':unittest.main()

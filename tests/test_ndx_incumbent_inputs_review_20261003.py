from copy import deepcopy
import unittest
from backtest import ndx_multidecision_incumbent_inputs_research as m
from test_ndx_multidecision_incumbent_inputs_research import fixture

def resign(a):
 c=a['candidate_evidence']['document']['inputs'];c['content_sha256']=m.digest({k:v for k,v in c.items() if k!='content_sha256'})

class Review(unittest.TestCase):
 def test_envelope_authority_and_specific_published_roles(self):
  mutations=[lambda a:a['candidate_evidence']['publication'].update(schema='FOREIGN'),lambda a:a['candidate_evidence']['document'].update(execution_authorized=0),lambda a:a['candidate_evidence']['readback'].update(scope='FOREIGN'),lambda a:a['original_eight_evidence']['publication'].update(point_in_time_verified=True),lambda a:a['original_eight_evidence']['readback'].update(original_provenance_count=True)]
  for change in mutations:
   a=fixture();change(a)
   with self.subTest(change=change),self.assertRaises((ValueError,KeyError)):m.prepare_incumbent_account_inputs(**a)
 def test_resigned_duplicate_clock_or_false_coordinate_mapping_rejected(self):
  for kind in ('clock','mapping'):
   a=fixture();ci=a['candidate_evidence']['document']['inputs']
   if kind=='clock':ci['execution_clock_from_saved_calendar']=[deepcopy(ci['execution_clock_from_saved_calendar'][0]) for _ in range(6)]
   else:ci['rows'][0]['coordinate_indexes']=[0]*6
   resign(a)
   with self.subTest(kind=kind),self.assertRaises(ValueError):m.prepare_incumbent_account_inputs(**a)
 def test_missing_quote_retains_all_slots_and_controls_do_not_alias(self):
  a=fixture();ch=a['original_eight_evidence']['document']['rows'][4]['channel'];row=ch['quote_rows'][-2];row['nominal_open_exact']=None;ch['quote_rows_sha256']=m.digest(ch['quote_rows'])
  result=m.prepare_incumbent_account_inputs(**a)
  self.assertEqual(len(result['rows']),8);self.assertEqual(sum(len(r['tracks']) for r in result['rows']),16)
  for r in result['rows']:
   for t in r['tracks']:
    self.assertEqual(t['status'],'BLOCKED_ORIGINAL_CONTROL_INPUT');matrix=t['engine_binding']['keyword_arguments']['opens'];self.assertEqual(len(matrix['columns']),8);self.assertIsNone(matrix['data'][-2][4]);self.assertEqual(len(t['engine_binding']['keyword_arguments']['schedule']),6)
  one=result['rows'][0]['tracks'][0];other=result['rows'][1]['tracks'][0]
  one['engine_binding']['keyword_arguments']['schedule'][0]['targets']['CONTROL:TSM']['target_weight']=99
  self.assertEqual(other['engine_binding']['keyword_arguments']['schedule'][0]['targets']['CONTROL:TSM']['target_weight'],.125)

if __name__=='__main__':unittest.main()

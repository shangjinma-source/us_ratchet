from copy import deepcopy
from fractions import Fraction
import unittest
from backtest import ndx_multidecision_target_scoring_inputs_research as m
from test_ndx_multidecision_target_scoring_inputs_research import fixture,resign
class Review(unittest.TestCase):
 def test_saved_alignment_relations_not_just_rehashed_conversion(self):
  def missing(a):a['rows'][0]['conversions'][m.MODES[0]].update(status='MISSING_ALIGNMENT_INPUT',reason='MISSING_NAV',nav_usd_exact=None)
  attacks=[lambda a:a['rows'][0]['conversions'][m.MODES[0]].update(nav_usd_exact='999'),lambda a:a['rows'][0]['conversions'][m.MODES[0]].update(nav_date='!'),lambda a:a['rows'][0]['conversions'][m.MODES[0]].update(nav_original_row_index=False),lambda a:a['rows'][0]['nav_observation']['original_row'].update(nav_cny_decimal='999'),missing]
  for f in attacks:
   a=fixture();f(a['alignment']);resign(a['alignment'])
   with self.subTest(attack=f):
    with self.assertRaises(ValueError):m.prepare_target_scoring_inputs(**a)
 def test_all_windows_independent_calendar_and_missing_edges(self):
  args=fixture('2026-03-31');before=deepcopy(args);r=m.prepare_target_scoring_inputs(**args);self.assertEqual(args,before);cal=args['reference_calendar']
  self.assertEqual(len(r['modes']),2)
  for mode in r['modes']:
   for decision in mode['decisions']:
    end=cal.index(decision['cutoff']);first=end-504;self.assertEqual(decision['required_price_dates'],cal[first:end+1]);self.assertEqual(len(decision['windows']),13)
    for n,w in enumerate(decision['windows']):self.assertEqual(w['training_freeze_close'],cal[first+21*n+126]);self.assertEqual(w['evaluation_last_return_end'],cal[first+21*n+252])
  j=r['session_dates'].index('2026-03-31');self.assertIsNone(r['modes'][0]['return_slots'][j-1]['return_exact']);self.assertIsNone(r['modes'][0]['return_slots'][j]['return_exact']);self.assertIsNotNone(r['modes'][1]['return_slots'][j]['return_exact'])
  self.assertFalse(r['source_bytes_authenticated']);self.assertFalse(r['mode_selected_using_results']);self.assertFalse(r['score_computed'])
if __name__=='__main__':unittest.main()

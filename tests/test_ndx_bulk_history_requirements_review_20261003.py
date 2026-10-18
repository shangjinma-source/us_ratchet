from copy import deepcopy
import unittest
from test_ndx_bulk_history_requirements_research import module as m,args

class IndependentHistoryRequirementsReview(unittest.TestCase):
 def test_all_thirteen_windows_match_pair_index_oracle(self):
  a=args();calendar=a['reference_calendar']['dates'];v=m.prepare_history_requirements(**a);long=v['scenarios'][1];dates=calendar[-505:]
  self.assertEqual(len(long['windows']),13)
  for n,w in enumerate(long['windows']):
   start=21*n
   expected_train=[{'previous_session':dates[i],'session':dates[i+1]} for i in range(start,start+126)]
   expected_eval=[{'previous_session':dates[i],'session':dates[i+1]} for i in range(start+126,start+252)]
   self.assertEqual(w['training_return_predecessors'],expected_train);self.assertEqual(w['evaluation_return_predecessors'],expected_eval)
   self.assertEqual(w['required_price_dates'],dates[start:start+253]);self.assertEqual(w['evaluation_initial_close_date'],dates[start+126]);self.assertEqual(w['training_freeze_close_date'],dates[start+126])
  self.assertEqual(long['windows'][-1]['required_price_dates'],calendar[-253:]);self.assertFalse(long['desired_505_is_hard_admission_threshold'])
 def test_floor_at_training_freeze_does_not_block_next_evaluation_return(self):
  a=args();days=a['reference_calendar']['dates'][-253:];item=a['ticker_observations']['T1'];item['event_policy_bridge']['regular_floor']=days[126]
  row=m.prepare_history_requirements(**a)['scenarios'][0]['security_rows'][1]['requirements'][0]
  self.assertEqual(row['forbidden_pre_partition_price_dates'],days[:126]);self.assertEqual(len(row['training_return_pairs_crossing_or_before_partition']),126);self.assertEqual(row['evaluation_return_pairs_crossing_or_before_partition'],[])
  self.assertFalse(row['partition_scope_complete']);self.assertTrue(row['saved_close_metadata_complete'])
 def test_missing_pair_endpoints_no_compaction_and_full_actions_preserved(self):
  a=args();days=a['reference_calendar']['dates'][-253:];item=a['ticker_observations']['T1'];removed={days[2],days[3]};item['observation_rows']=[r for r in item['observation_rows'] if r['session'] not in removed]
  item['event_policy_bridge']['events']=[{'kind':'DIVIDEND','date':days[0],'amount':'0.25'},{'kind':'SPLIT','date':days[-1],'numerator':10,'denominator':1}]
  item['extra_original']['publication_date']=None;before=deepcopy(a);v=m.prepare_history_requirements(**a);self.assertEqual(a,before);self.assertEqual(v['ticker_observations_preserved'],a['ticker_observations'])
  w=v['scenarios'][0]['windows'][0];r=v['scenarios'][0]['security_rows'][1]['requirements'][0]
  self.assertEqual(w['required_price_dates'],days);self.assertEqual(r['missing_price_dates'],sorted(removed));self.assertEqual(r['training_return_pairs_with_missing_close'],[p for p in w['training_return_predecessors'] if {p['session'],p['previous_session']} & removed]);self.assertEqual(len(r['training_return_pairs_with_missing_close']),3)
  self.assertEqual(v['security_denominator'],77);self.assertEqual(v['issuer_denominator'],76);self.assertTrue(all(v[k] is False for k in m.FLAGS))
 def test_reference_cannot_be_filtered_or_identity_backdated(self):
  for attack in ('filter','identity','unknownfield','duplicate'):
   a=args()
   if attack=='filter':a['reference_calendar']['dates'].pop(-5)
   elif attack=='identity':a['ticker_observations']['T1']['identity_assumed_window']={'first':'2024-01-01','last':'2026-09-21'}
   elif attack=='unknownfield':a['ticker_observations']['T1']['observation_rows'][0]['missing_fields']=[True]
   else:a['ticker_observations']['T1']['observation_rows'].insert(1,deepcopy(a['ticker_observations']['T1']['observation_rows'][0]))
   with self.assertRaises(ValueError):m.prepare_history_requirements(**a)
if __name__=='__main__':unittest.main()

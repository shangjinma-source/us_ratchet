"""Independent bounded adapter tests; no live data, sealing or fitting."""
from copy import deepcopy
from itertools import combinations
from unittest.mock import patch
import unittest
from test_ndx_persisted_fresh_snapshot_executor_research import fixture,m


class Tests(unittest.TestCase):
 def test_boolean_prices_cannot_become_training_one(self):
  for role,field in (('adjusted_prices','Close'),('nominal_prices','Volume'),('target_nav','Close')):
   a=fixture();x=a['execution_input'];p=x[role] if role=='target_nav' else x[role]['T00']
   p['rows'][0][field]=True;p['projection_sha256']=m.digest(p['rows'])
   with self.subTest(role=role),self.assertRaises(ValueError):m.execute_fresh_input_snapshot(**a)

 def test_calendar_registration_and_deadline_fail_before_compute(self):
  for mode in ('invalid_date','mixed_reader','deadline','registration','missing_role'):
   a=fixture();x=a['execution_input']
   if mode=='invalid_date':x['calendar']['document']['evidence']['known_typed_rows_preserved'][0]['session']='2026-00-01'
   elif mode=='mixed_reader':x['calendar']['readback']['reader_sha256']='b'*64
   elif mode=='deadline':a['execution_started_at_utc']='2026-10-05T13:30:00+00:00'
   elif mode=='registration':a['registration']['operation']='FIT_AND_SEAL'
   else:del x['evidence_sidecars']['official_receipt']
   with self.subTest(mode=mode),patch.object(m,'fixed_computation',side_effect=AssertionError('Should reject before compute')),self.assertRaises(ValueError):m.execute_fresh_input_snapshot(**a)

 def test_real_compute_full_ndx_domain_preserves_conditional_input(self):
  a=fixture('later');original=deepcopy(a)
  a['execution_input']['evidence_sidecars']['risk_evidence']['original_evidence']={'historical_available_at':None,'conditional_only':True}
  result=m.execute_fresh_input_snapshot(**a)
  rows=result['snapshot']['eligible_securities']['rows']
  oracle=[sum(len({r['issuer_id'] for r in combo})==k for combo in combinations(rows,k)) for k in range(1,4)]
  self.assertEqual(oracle,[4,5,2])
  self.assertEqual([r['theoretical_security_combinations'] for r in result['snapshot']['job_plan']['rows']],oracle)
  self.assertEqual(result['planned_evaluation_tracks'],['continuous','whole_lot'])
  self.assertFalse(result['industry_filter_applied'])
  self.assertTrue(any(r['risk_chain']=='oil_gas' for r in rows))
  self.assertEqual(result['original_control_ticker_order_preserved'],original['execution_input']['frozen_original8_tickers'])
  self.assertEqual(result['evidence_sidecars_preserved']['risk_evidence']['original_evidence']['historical_available_at'],None)
  self.assertTrue(all(result[k]is False for k in m.FLAGS))
  self.assertEqual(result['snapshot']['execution_date'],None)
  self.assertEqual(a['execution_input']['adjusted_prices'],original['execution_input']['adjusted_prices'])

 def test_row_membership_evidence_is_in_closure_and_conflicts_rejected(self):
  a=fixture();p=a['execution_input']['eligible_membership'];extra={'path':str(m.ROOT/'tmp/independent-extra-membership-proof'),'sha256':'c'*64}
  p['rows'][0]['membership_evidence_reference']=extra;p['projection_sha256']=m.digest(p['rows'])
  out=m.execute_fresh_input_snapshot(**a)
  self.assertEqual(out['source_hash_claims'][extra['path']],extra['sha256'])
  self.assertFalse(out['source_bytes_authenticated']);self.assertFalse(out['complete_universe_verified'])
  p['rows'][1]['membership_evidence_reference']=dict(extra,sha256='d'*64);p['projection_sha256']=m.digest(p['rows'])
  with patch.object(m,'fixed_computation',side_effect=AssertionError('Conflicting proof before computation')),self.assertRaises(ValueError):m.execute_fresh_input_snapshot(**a)


if __name__=='__main__':unittest.main()

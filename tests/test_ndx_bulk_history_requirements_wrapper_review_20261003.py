from copy import deepcopy
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_bulk_history_requirements_20261003 import m,core,fixture

class IndependentHistoryWrapperReview(unittest.TestCase):
 def test_incomplete_reference_day_not_filtered_full_events_and_sidecars_preserved(self):
  d,r=fixture();obs=d['readback']['rows'][0]['observation'];day=obs['rows'][-2]['new_york_date'];obs['rows'][-2]['missing_fields']=['close','volume']
  obs['raw_returned_events']['capitalGains']={'extra':{'date':'original','amount':'0.75'}}
  before=deepcopy(d);a,e=m.project_inputs(d,r);self.assertEqual(d,before)
  self.assertIn(day,a['reference_calendar']['dates']);self.assertEqual(a['ticker_observations']['AAPL']['observation_rows'][-1]['missing_fields'],['close','volume'])
  self.assertEqual(a['ticker_observations']['AAPL']['returned_events'],obs['raw_returned_events']);self.assertEqual(e['complete_panel_sidecars'],{k:d['panel'][k] for k in m.SIDECARS})
  self.assertEqual(a['ticker_observations']['AAPL']['excluded_after_cutoff_or_receipt_day'][0]['session'],'2026-09-22');self.assertEqual(len(a['ticker_observations']),77)
 def test_crosssource_hash_split_and_receipt_exclusion_conflicts(self):
  d,r=fixture()
  for attack in ('rawhash','split','receipt','sameissuer-otherSID'):
   bad=deepcopy(d)
   if attack=='rawhash':bad['readback']['source_hashes'][bad['bridge']['rows'][0]['new_raw_reference']['path']]='f'*64
   elif attack=='split':bad['bridge']['rows'][0]['new_returned_splits']={'unexpected':{'numerator':2}}
   elif attack=='receipt':bad['readback']['rows'][0]['observation']['rows'][-1]['excluded_receipt_day_or_later']=True
   else:bad['panel']['panel']['observed_provenance_and_missing'][0]['coordinate_assumption']['security_id']='S1'
   with self.assertRaises(ValueError):m.project_inputs(bad,r)
 def test_rehashed_authority_upgrade_rejected_no_early_identity_extension(self):
  d,r=fixture();a,e=m.project_inputs(d,r);v=core.prepare_history_requirements(**a)
  v['identity_interval_verified']=True;v['content_sha256']=m.sha(m.encoded({k:x for k,x in v.items() if k!='content_sha256'}))
  with self.assertRaises(ValueError):m.validate_result(v,a)
  self.assertEqual(a['ticker_observations']['T1']['identity_assumed_window'],{'first':'2026-03-20','last':'2026-09-21'})
 def test_loaded_source_guard_and_existing_failure_never_restarted(self):
  with tempfile.TemporaryDirectory() as t:
   source=Path(t)/'new.py';source.write_bytes(b'original')
   with patch.object(m,'SOURCE',source),patch.object(m,'LOADED_SHA',m.sha(b'original')):
    source.write_bytes(b'changed')
    with self.assertRaises(ValueError):m.guard({})
   folder=Path(t)/'out';folder.mkdir();(folder/'failure.json').write_text('{}')
   with patch.object(m,'OUTPUT',folder),patch.object(m,'load_inputs') as load:
    with self.assertRaises(ValueError):m.run()
    load.assert_not_called()
if __name__=='__main__':unittest.main()

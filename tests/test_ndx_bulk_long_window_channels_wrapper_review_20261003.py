"""Synthetic source-bound wrapper review; no actual77 reconstruction."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('long_wrapper_fixture',ROOT/'tests/test_ndx_bulk_long_window_channels_20261003.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f);m=f.m

class Review(unittest.TestCase):
 def test_prior_fitting_overlap_full126_exact_and_not_holdout(self):
  docs,refs,raws=f.fixture();requests=m.prepare(docs,refs)
  out=m.assemble(requests,raws,b'TZ',types.SimpleNamespace(reconstruct_long_channel=f.blocked),docs,refs)
  ev=out['evaluation_prior_fit_overlap_evidence'];self.assertEqual(ev['evaluation_dates'],requests[0]['calendar253'][127:]);self.assertEqual(ev['saved_batch_reference'],refs['prior_fit_batch']);self.assertEqual(ev['prior_fit_task_count'],1632)
  self.assertIs(out['untouched_holdout'],False);self.assertIs(out['future_independent_oos'],False);self.assertIs(out['evaluation_interval_previously_used_for_fitting'],True)
  for mutation in (lambda d:d['panel']['panel']['returns']['index'].reverse(),lambda d:d['panel']['panel']['returns']['index'].__setitem__(-1,d['panel']['panel']['returns']['index'][-1].replace('T00:00:00','T12:00:00')),lambda d:d['prior_fit_batch'].update(status='STOPPED_WITH_EVIDENCE'),lambda d:d['prior_fit_batch'].update(new_readback_count=True)):
   bad=deepcopy(docs);mutation(bad)
   with self.assertRaises(ValueError):m.prepare(bad,refs)

 def test_original_101_sidecars_and_unselected_metadata_binding(self):
  docs,refs,raws=f.fixture()
  for mutate in (lambda d:d['history']['requirements']['observed_provenance_and_missing'].pop(),lambda d:d['history']['projection_evidence']['complete_panel_sidecars'][m.SIDECARS[-1]].append({'new':True}),lambda d:d['history']['requirements']['ticker_observations_preserved']['AAPL']['receipt_reference'].update(sha256='0'*64),lambda d:d['history']['requirements'].update(original_identity_assumed_window={'first':'2025-09-18','last':'2026-09-21'})):
   bad=deepcopy(docs);mutate(bad)
   with self.assertRaises(ValueError):m.prepare(bad,refs)
  req=m.prepare(docs,refs);call=Mock(side_effect=f.blocked);changed=deepcopy(raws);changed[req[0]['coordinate']['ticker']]['receipt_bytes']+=b' '
  with self.assertRaises(ValueError):m.assemble(req,changed,b'TZ',types.SimpleNamespace(reconstruct_long_channel=call),docs,refs)
  call.assert_not_called()

 def test_permission_source_conflict_failure_evidence_and_retry_gate(self):
  docs,refs,raws=f.fixture();req=m.prepare(docs,refs)
  def forged(**kw):
   out=f.blocked(**kw);out['legal_training_input_admitted']=True;return out
  with self.assertRaises(ValueError):m.assemble(req,raws,b'TZ',types.SimpleNamespace(reconstruct_long_channel=forged),docs,refs)
  with self.assertRaises(ValueError):m.merge({'same':'a'*64},'same','b'*64)
  with tempfile.TemporaryDirectory() as td:
   output=Path(td)/'attempt'
   with patch.object(m,'OUTPUT',output),patch.object(m,'load_inputs',return_value=({}, {}, {}, [], {}, b'', None)) as load,patch.object(m,'assemble',side_effect=ValueError('new bad raw')):
    with self.assertRaises(ValueError):m.run()
    self.assertEqual({p.name for p in output.iterdir()},{'started.json','failure.json'})
    with self.assertRaises(ValueError):m.run()
    self.assertEqual(load.call_count,1)

if __name__=='__main__':unittest.main()

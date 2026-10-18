"""Independent bounded original8 reuse/one-call tests; no saved raw used."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('original8_fixture',ROOT/'tests/test_ndx_original_eight_long_window_channels_20261003.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f);m=f.m

class Review(unittest.TestCase):
 def test_seven_full_rows_unchanged_only_tsm_new_no_fivefold_conversion(self):
  docs,refs,raw,receipt=f.fixture();old=deepcopy(docs);prepared=m.prepare(docs,refs);calls=[]
  def call(**kw):calls.append(deepcopy(kw));return f.fake_core(**kw)
  out=m.assemble(prepared,raw,receipt,b'TZ',types.SimpleNamespace(reconstruct_long_channel=call),docs,refs)
  self.assertEqual(len(calls),1);self.assertEqual(calls[0]['receipt']['ticker'],'TSM');self.assertEqual(calls[0]['raw_bytes'],raw);self.assertEqual(calls[0]['bridge_row']['event_policy_bridge'],{'events':[],'regular_floor':None})
  for row in out['rows']:
   t=row['original_control_security']['ticker']
   if t!='TSM':self.assertEqual(row['complete_parent_row'],next(r for r in docs['channels']['rows'] if r['coordinate']['ticker']==t));self.assertEqual(row['channel'],row['complete_parent_row']['channel'])
  self.assertEqual(docs,old);self.assertEqual(out['rows'][4]['original_control_security']['security_id'],'security:incumbent_overlay:TSM');self.assertFalse(out['holdings_or_quotes_converted']);self.assertFalse(out['untouched_holdout'])
  self.assertNotIn('OLD_NOT_SPLICED',out['rows'][4]['channel']['returned_events']['dividends'])
  out['rows'][0]['channel']['quote_rows'][0]['nominal_close']='changed';self.assertEqual(docs,old)

 def test_link_hashes_class_roles_basis_and_original_weights_attack(self):
  mutations=(lambda d:d['channels_audit']['per_channel'][0].update(quote_rows_sha256='f'*64),lambda d:d['requirements']['requirements']['original_control_preserved']['securities'][0].update(target_weight=.9),lambda d:d['requirements']['requirements']['stock_metadata_preserved']['TSM']['complete_identity_sidecar'].update(ordinary_shares_per_ads=True),lambda d:d['requirements']['requirements']['stock_metadata_preserved']['TSM']['complete_identity_sidecar'].update(security_class='Ordinary Shares'),lambda d:d['old_tsm_basis']['reconstruction'].update(quote_field_basis='ADJCLOSE_TOTAL_RETURN'),lambda d:d['old_tsm_basis'].update(zero_returned_splits_proves_no_actions=True))
  for mutate in mutations:
   docs,refs,_,_=f.fixture();mutate(docs)
   with self.assertRaises(ValueError):m.prepare(docs,refs)

 def test_tsm_fail_keeps_seven_no_retry_and_source_guard(self):
  docs,refs,raw,receipt=f.fixture();prepared=m.prepare(docs,refs);call=Mock(side_effect=ValueError('TSM new decode failure'))
  with self.assertRaises(ValueError):m.assemble(prepared,raw,receipt,b'TZ',types.SimpleNamespace(reconstruct_long_channel=call),docs,refs)
  self.assertEqual(call.call_count,1);self.assertIsNone(prepared['rows'][4]['channel'])
  with tempfile.TemporaryDirectory() as td:
   src=Path(td)/'source';src.write_bytes(b'changed')
   with patch.object(m,'SOURCE',src),patch.object(m,'LOADED_SHA',m.sha(b'original')):
    with self.assertRaises(ValueError):m.guard({})
   out=Path(td)/'attempt';out.mkdir();(out/'failure.json').write_text('{}')
   with patch.object(m,'OUTPUT',out),patch.object(m,'load_inputs') as load:
    with self.assertRaises(ValueError):m.run()
    load.assert_not_called()

if __name__=='__main__':unittest.main()

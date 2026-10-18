import copy,unittest,tempfile
from decimal import localcontext,Inexact
from pathlib import Path
from unittest.mock import patch
from test_ndx_bulk_conditional_panel_20261003 import fixture,channel,m
class BulkPanelIndependentReview(unittest.TestCase):
 def test_context_numeric_reuse_and_calendar_attack(self):
  d=fixture();c=channel('TEST',d['channels']['calendar']);c['price_rows'][-1]['nominal_close']=100.12345678901234
  with localcontext() as context:
   context.prec=2;context.traps[Inexact]=True
   values,reason=m.saved_channel_projection(c,c['calendar'])
  self.assertIsNone(reason);self.assertEqual(values[0],[r['price_return'] for r in c['price_returns']]);self.assertEqual(values[1],[r['nominal_close'] for r in c['price_rows']])
  c['price_returns'][0]['previous_session']=c['calendar'][1]
  with self.assertRaises(ValueError):m.saved_channel_projection(c,c['calendar'])
 def test_full_old_frames_evidence_and_blocked_identity(self):
  d=fixture();original=copy.deepcopy(d);c=d['channels']['rows'][24];c['channel_input']['liquidity']['numerical_threshold_passed']=False
  for role in ('wiring','parent_wiring'):d[role]['rows'][24]['channel_row_sha256']=m.sha(m.encode(c))
  with patch.object(m.core,'channel_values',side_effect=AssertionError('no old numeric')):out=m.assemble(d)
  before=m.codec.typed_decode(original['parent_panel']['panel']);after=m.codec.typed_decode(out['panel'])
  for name in m.FRAMES:
   left=before[name]
   right=after[name].set_index('security_id',drop=False).loc[left.security_id].reset_index(drop=True) if name=='universe' else after[name].loc[:,left.columns]
   self.assertEqual(m.canonical(m.frame_payload(left)),m.canonical(m.frame_payload(right)))
  for key in m.SIDECARS:self.assertEqual(out[key],original['parent_panel'][key])
  increment=out['bulk_incremental_evidence_and_projection'][0]
  self.assertEqual(increment['original_gap'],before['observed_provenance_and_missing'][24]);self.assertIsNotNone(increment['new_gap']['coordinate_assumption']);self.assertFalse(increment['new_gap']['included_in_conditional_panel'])
  self.assertNotIn('N0',after['returns'].columns);self.assertNotIn('CRWD',after['returns'].columns)
  self.assertTrue(all(out[k] is False for k in m.FALSE))
 def test_versioned_mapping_resigned_risk_and_receipt_attack(self):
  d=fixture();d['wiring_publication']['wiring_reference']={'path':'wrong','sha256':'a'*64}
  with self.assertRaises(ValueError):m.assemble(d)
  out=m.assemble(fixture());p=m.codec.typed_decode(out['panel']);p['universe'].loc[p['universe']['security_id']=='sid:N0','risk_chain']='';p['panel_content_sha256']=m.core.panel_digest(p)
  with self.assertRaises(ValueError):m.selected_mapping_bulk(p,['sid:N0'])
  p['schema']='LATEST_CONDITIONAL_TYPED_PANEL_V6';p['panel_content_sha256']=m.core.panel_digest(p)
  with self.assertRaises(ValueError):m.selected_mapping_bulk(p,['sid:O0'])
if __name__=='__main__':unittest.main()

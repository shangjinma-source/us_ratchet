from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import tempfile,unittest
from scripts import ndx_original_eight_tsm_scoring_history_20261003 as m
from test_ndx_original_eight_tsm_scoring_history_20261003 import fixture
class Review(unittest.TestCase):
 def test_preserved_control_bridge_and_false_type_attacks(self):
  docs,refs=fixture();a=m.prepare(docs,refs)
  self.assertEqual(a['original_control_contract']['securities'],docs['control']['definition']['securities']);self.assertEqual(a['bridge_row'],docs['original_channels']['rows'][4]['conditional_event_policy_bridge'])
  for mutate in (lambda d:d['original_audit'].update(reader_sha256='0'*64),lambda d:d['original_channels'].update(point_in_time_verified=0),lambda d:d['requirements']['requirements']['stock_metadata_preserved']['TSM'].update(control_only_overlay=1),lambda d:d['original_channels']['rows'][4]['conditional_event_policy_bridge'].update(new_decoded_sha256='0'*64)):
   bad=deepcopy(docs);mutate(bad)
   with self.assertRaises(ValueError):m.prepare(bad,refs)
 def test_published_channel_drift_is_failed_namespace(self):
  docs,refs=fixture();args=m.prepare(docs,refs)
  ch=dict(schema='ORIGINAL_EIGHT_TSM_SCORING_HISTORY_CHANNEL_V1',role=m.ROLE,ticker='TSM',bridge_row_preserved=args['bridge_row'],decisions=[dict(windows=[{}]*13)]*6,**{k:args[k]for k in ('raw_reference','receipt_reference','original_control_contract','window_contract')},**dict.fromkeys(('fit_performed','score_computed','source_bytes_authenticated','ndx_candidate_admitted','holdings_or_ads_converted','point_in_time_verified'),False))
  with tempfile.TemporaryDirectory() as tmp:
   original=m.save
   def save(p,v,failure=False):
    out=original(p,v,failure)
    if p.name=='publication.json':(p.parent/'channel.json').write_bytes(b'drift')
    return out
   with patch.object(m,'OUTPUT',Path(tmp)/'out'),patch.object(m,'load_inputs',return_value=(docs,refs,{},args,SimpleNamespace(materialize_tsm_control_history=lambda **kw:ch))),patch.object(m,'space'),patch.object(m,'guard'),patch.object(m,'save',side_effect=save):
    with self.assertRaisesRegex(ValueError,'Output drift'):m.run(execute=True)
    self.assertTrue((m.OUTPUT/'failure.json').exists())
    with self.assertRaisesRegex(ValueError,'Immutable'):m.run(execute=True)
if __name__=='__main__':unittest.main()

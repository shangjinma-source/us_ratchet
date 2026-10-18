from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
import tempfile,unittest
from backtest import ndx_tsm_scoring_history_inspection_research as c
from scripts import ndx_tsm_scoring_history_independent_readback_20261003 as r
from test_ndx_tsm_scoring_history_inspection_research import fixture,producer
from test_ndx_tsm_scoring_history_independent_readback_20261003 import fixture as evidence
class Review(unittest.TestCase):
 def test_independent_values_and_resigned_control_claim(self):
  a=fixture();d=producer.materialize_tsm_control_history(**a)
  for q in d['quote_rows']:self.assertEqual(Fraction(q['nominal_close_exact']),Fraction(81,8)*(10 if q['session']<'2026-06-12'else 1))
  self.assertEqual(c.inspect_tsm_control_history(saved_channel=d,**a)['window_count'],78)
  for mutate in (lambda x:x.update(ndx_candidate_admitted=0),lambda x:x['original_control_contract']['securities'].reverse(),lambda x:x['quote_rows'][0].update(split_factor_exact='1')):
   bad=deepcopy(d);mutate(bad);bad['quote_rows_sha256']=c.digest(bad['quote_rows']);bad['content_sha256']=c.digest({k:v for k,v in bad.items()if k!='content_sha256'})
   with self.assertRaises(ValueError):c.inspect_tsm_control_history(saved_channel=bad,**a)
 def test_independent_metadata_source_and_identity_roles(self):
  a=evidence();r.inspect_evidence(*a)
  for mutate in (lambda x:x[1].update(source_hashes={}),lambda x:x[2].update(planned_raw_decode_count=1.0),lambda x:x[0]['complete_tsm_metadata']['complete_identity_sidecar'].update(ordinary_shares_per_ads=True),lambda x:x[3]['original_audit'].update(reader_sha256='0'*64)):
   bad=deepcopy(a);mutate(bad)
   with self.assertRaises(ValueError):r.inspect_evidence(*bad)
 def test_parent_namespace_extra_rejected_at_guard(self):
  with tempfile.TemporaryDirectory() as tmp:
   parent=Path(tmp)
   for name in ('started.json','channel.json','publication.json'):(parent/name).write_bytes(b'{}')
   with patch.object(r,'PARENT',parent):
    r.guard({});(parent/'unexpected').write_bytes(b'')
    with self.assertRaises(ValueError):r.guard({})
if __name__=='__main__':unittest.main()

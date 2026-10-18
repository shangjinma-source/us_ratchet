from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch
from scripts import ndx_official_public_membership_capture_20261003 as m

class Tests(unittest.TestCase):
 def test_preexecution_gate_and_createonly_public_bytes(self):
  with TemporaryDirectory() as t,patch.object(m,'OUTPUT',Path(t)/'new'),patch.object(m,'fetch',return_value=(b'<html>Data unavailable</html>',{'http_status':200})) as f:
   with self.assertRaises(ValueError):m.run()
   f.assert_not_called();self.assertFalse(m.OUTPUT.exists())
   r=m.run(execute=True);d=json.loads(Path(r['path']).read_bytes());self.assertEqual(f.call_count,2)
   self.assertEqual(d['status'],'PUBLIC_ACCESS_EVIDENCE_ONLY_NO_MEMBER_LIST')
   self.assertTrue(all(d[k]is False for k in m.FLAGS))
   with self.assertRaisesRegex(ValueError,'no retry'):m.run(execute=True)
 def test_http_denial_and_transport_error_retained_no_membership(self):
  with TemporaryDirectory() as t,patch.object(m,'OUTPUT',Path(t)/'new'),patch.object(m,'fetch',side_effect=[(b'Login required',{'http_status':403}),TimeoutError('bounded')]):
   m.run(execute=True)
   a=json.loads((m.OUTPUT/'companies.receipt.json').read_bytes());b=json.loads((m.OUTPUT/'giw_weighting.receipt.json').read_bytes())
   self.assertEqual(a['transport_metadata']['http_status'],403);self.assertFalse(a['membership_complete'])
   self.assertEqual(b['error']['type'],'TimeoutError');self.assertIsNone(b['response_reference'])
 def test_rawfirst_resource_and_publication_drift_failed_no_retry(self):
  with TemporaryDirectory() as t,patch.object(m,'OUTPUT',Path(t)/'new'),patch.object(m,'LIMIT',2),patch.object(m,'fetch',return_value=(b'abc',{'http_status':200})):
   m.run(execute=True);r=json.loads((m.OUTPUT/'companies.receipt.json').read_bytes());self.assertFalse(r['body_complete']);self.assertEqual((m.OUTPUT/'companies.response.bin').read_bytes(),b'abc')
  original=m.save
  with TemporaryDirectory() as t,patch.object(m,'OUTPUT',Path(t)/'new'),patch.object(m,'fetch',return_value=(b'ok',{'http_status':200})):
   def corrupt(p,o):
    r=original(p,o)
    if p.name=='manifest.json':(m.OUTPUT/'companies.response.bin').write_bytes(b'changed')
    return r
   with patch.object(m,'save',side_effect=corrupt),self.assertRaisesRegex(ValueError,'drift'):m.run(execute=True)
   self.assertEqual(json.loads((m.OUTPUT/'failure.json').read_bytes())['status'],'FAILED_NO_RETRY')
   self.assertTrue((m.OUTPUT/'manifest.json').exists())

if __name__=='__main__':unittest.main()

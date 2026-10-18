import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_official_change_notices_capture_20261003 as m
class Response(io.BytesIO):
 code=200;headers={'Date':'untrusted server date','Content-Type':'text/html'}
 def geturl(self):return m.PAGES[0][1]
class Opener:
 def __init__(self,response):self.response=response
 def open(self,request,timeout):return self.response
class Tests(unittest.TestCase):
 def test_fixed_two_raw_opaque_no_authority_and_no_retry(self):
  with tempfile.TemporaryDirectory()as tmp,patch.object(m,'OUTPUT',Path(tmp)/'out'),patch.object(m,'build_opener',side_effect=lambda *a:Opener(Response(b'\xffnon-html'))):
   r=m.run(execute=True);d=json.loads(Path(r['path']).read_bytes())
   self.assertEqual(d['successful_http200_response_count'],2);self.assertEqual(len(list(m.OUTPUT.iterdir())),6)
   self.assertTrue(all(d[k]is False for k in m.FLAGS))
   self.assertEqual((m.OUTPUT/'october_future_mrna_wbd.response.bin').read_bytes(),b'\xffnon-html')
   with self.assertRaises(ValueError):m.run(execute=True)
 def test_pending_no_io_and_redirect_disabled(self):
  with patch.object(Path,'read_bytes',side_effect=AssertionError('No IO')),patch.object(m,'build_opener',side_effect=AssertionError('No network')):
   with self.assertRaises(ValueError):m.run()
  self.assertIsNone(m.NoRedirect().redirect_request(None,None,302,'',{},'https://other.example'))
 def test_partial_and_oversize_preserve_bytes_without_complete_claim(self):
  class Broken(Response):
   def read(self,size):
    if self.tell():raise OSError('read interrupted')
    return super().read(3)
  for response,limit in [(Broken(b'abcdef'),100),(Response(b'abcdef'),4)]:
   with self.subTest(limit=limit),tempfile.TemporaryDirectory()as tmp,patch.object(m,'OUTPUT',Path(tmp)),patch.object(m,'LIMIT',limit),patch.object(m,'build_opener',return_value=Opener(response)):
    raw,rr,ok=m.capture(*m.PAGES[0]);d=json.loads(Path(rr['path']).read_bytes())
    self.assertFalse(ok);self.assertFalse(d['body_complete']);self.assertIsNotNone(d['error']);self.assertGreater(raw['byte_count'],0)
 def test_interrupt_and_final_drift_keep_failure(self):
  class Interrupted(Response):
   def read(self,size):
    if self.tell():raise KeyboardInterrupt('original interrupt')
    return super().read(3)
  for mode in ('interrupt','drift'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as tmp,patch.object(m,'OUTPUT',Path(tmp)/'out'),patch.object(m,'build_opener',side_effect=lambda *a:Opener(Interrupted(b'abcdef')if mode=='interrupt'else Response(b'abcdef'))):
    original=m.save
    def save(name,value):
     r=original(name,value)
     if name=='manifest.json':(m.OUTPUT/'june_quarterly_changes.response.bin').write_bytes(b'drift')
     return r
    with patch.object(m,'save',save),self.assertRaises((KeyboardInterrupt,ValueError)):m.run(execute=True)
    self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertTrue((m.OUTPUT/'june_quarterly_changes.response.bin').exists())
    with self.assertRaises(ValueError):m.run(execute=True)
 def test_close_failure_retains_body_and_receipt(self):
  class BrokenClose(Response):
   def close(self):
    was_closed=self.closed;super().close()
    if not was_closed:raise OSError('close failed')
  with tempfile.TemporaryDirectory()as tmp,patch.object(m,'OUTPUT',Path(tmp)),patch.object(m,'build_opener',return_value=Opener(BrokenClose(b'complete body'))):
   raw,rr,ok=m.capture(*m.PAGES[0]);d=json.loads(Path(rr['path']).read_bytes())
   self.assertFalse(ok);self.assertFalse(d['body_complete']);self.assertEqual(d['error']['stage'],'RESPONSE_CLOSE')
   self.assertEqual(Path(raw['path']).read_bytes(),b'complete body')
   self.assertEqual(m.DECISION_RELATION['october_future_mrna_wbd']['relation'],'AFTER_DECISION_DO_NOT_APPLY_EARLY')
if __name__=='__main__':unittest.main()

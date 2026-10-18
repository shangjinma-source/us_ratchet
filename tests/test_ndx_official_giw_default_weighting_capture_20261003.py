import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from scripts import ndx_official_giw_default_weighting_capture_20261003 as m
HTML='<a id="symbol">NDX</a><option value="SOD">Start of Day</option>$("#tradeDate").attr("disabled", "true")'+''.join(u.split('nasdaqomx.com')[1]for _,u in m.PAGES)
JS='function GetFreeColumns "Name" "Symbol" new Date() datepicker("setDate", today) $("#timeOfDay").val("SOD") url: "/Index/WeightingData" type: "POST" tradeDate: tradeDate.toISONonUtcString() timeOfDay: $("#timeOfDay").val()'
SITE='Date.prototype.toISONonUtcString = function getFullYear() getMonth() + 1 getDate() getHours() getMinutes() getSeconds() getMilliseconds()'
CLOCK=dict(local_iso='2026-10-03T14:00:00+08:00',timezone_name='synthetic UTC+08',utc_offset_seconds=28800,local_date='2026-10-03',basis='WINDOWS_LOCAL_DATETIME_ASTIMEZONE_NOT_MEMBER_EFFECTIVE_DATE')
class Response(io.BytesIO):
 code=200;headers={}
 def geturl(self):return 'https://indexes.nasdaqomx.com/synthetic'
class Tests(unittest.TestCase):
 def context(self,stack,root,responses):
  h=root/'original.html';h.write_bytes(HTML.encode());requests=[]
  class Opener:
   def open(self,request,timeout):requests.append(request);return responses.pop(0)
  for name,value in [('OUTPUT',root/'out'),('HTML',h),('HTML_SHA',m.sha(h.read_bytes())),('local_clock',lambda:dict(CLOCK)),('build_opener',lambda *a:Opener())]:stack.enter_context(patch.object(m,name,value))
  return requests
 def test_default_local_day_exact_post_body_no_history_export(self):
  with tempfile.TemporaryDirectory()as t,ExitStack()as st:
   reqs=self.context(st,Path(t),[Response(JS.encode()),Response(SITE.encode()),Response(b'opaque login page')]);ref=m.run(execute=True)
   self.assertEqual([r.method for r in reqs],['GET','GET','POST'])
   self.assertEqual(reqs[-1].data,b'id=NDX&tradeDate=2026-10-03T00%3A00%3A00.000&timeOfDay=SOD')
   saved=json.loads((m.OUTPUT/'default_weighting.request.json').read_bytes());self.assertIsNone(saved['member_effective_date']);self.assertFalse(saved['export_requested'])
   doc=json.loads(Path(ref['path']).read_bytes());self.assertTrue(all(doc[k]is False for k in m.FLAGS));self.assertEqual(doc['successful_http200_response_count'],3)
   with self.assertRaises(ValueError):m.run(execute=True)
 def test_js_non200_or_wrong_semantics_never_post(self):
  for wrong in ('status','semantics'):
   with self.subTest(wrong=wrong),tempfile.TemporaryDirectory()as t,ExitStack()as st:
    r=Response(JS.encode()if wrong=='status'else b'changed code')
    if wrong=='status':r.code=403
    reqs=self.context(st,Path(t),[r,Response(SITE.encode())])
    with self.assertRaises(ValueError):m.run(execute=True)
    self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertTrue(all(r.method=='GET'for r in reqs));self.assertFalse((m.OUTPUT/'default_weighting.request.json').exists())
 def test_post_partial_and_interrupt_durable(self):
  for interrupt in (False,True):
   class Broken(Response):
    def read(self,n):
     if self.tell():raise KeyboardInterrupt('stop')if interrupt else OSError('partial')
     return super().read(3)
   with self.subTest(interrupt=interrupt),tempfile.TemporaryDirectory()as t,ExitStack()as st:
    self.context(st,Path(t),[Response(JS.encode()),Response(SITE.encode()),Broken(b'abcdef')])
    if interrupt:
     with self.assertRaises(KeyboardInterrupt):m.run(execute=True)
    else:m.run(execute=True)
    self.assertEqual((m.OUTPUT/'default_weighting.response.bin').read_bytes(),b'abc')
    receipt=json.loads((m.OUTPUT/'default_weighting.receipt.json').read_bytes());self.assertFalse(receipt['body_complete']);self.assertEqual(receipt['request']['body_sha256'],m.sha(receipt['request']['body_ascii'].encode()))
 def test_gate_before_io_and_source_drift_after_save(self):
  with patch.object(Path,'read_bytes',side_effect=AssertionError('no IO')):
   with self.assertRaises(ValueError):m.run()
  with tempfile.TemporaryDirectory()as t,ExitStack()as st:
   self.context(st,Path(t),[Response(JS.encode()),Response(SITE.encode()),Response(b'{}')]);original=m.save
   def save(name,value):
    r=original(name,value)
    if name=='manifest.json':m.HTML.write_bytes(b'changed')
    return r
   with patch.object(m,'save',save),self.assertRaises(ValueError):m.run(execute=True)
   self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertTrue((m.OUTPUT/'manifest.json').exists())
if __name__=='__main__':unittest.main()

import copy,json,unittest
from scripts import ndx_official_giw_empty_response_diagnostic_20261003 as m
from test_ndx_official_giw_default_weighting_capture_20261003 import JS,SITE,HTML,CLOCK
from urllib.parse import urlencode
def encoded(v):return json.dumps(v).encode()
def fixture():
 form=dict(id='NDX',tradeDate='2026-10-03T00:00:00.000',timeOfDay='SOD');body=urlencode(form)
 q=dict(method='POST',url=m.URLS['default_weighting'],body_ascii=body,body_sha256=m.digest(body.encode()),form=form,clock=CLOCK,member_effective_date=None,historical_date_control_disabled=True,requested_time_of_day='SOD',**dict.fromkeys(('historical_date_override','eod_requested','export_requested','proforma_requested','js_executed'),False))
 raws={'weighting_js.response.bin':JS.encode(),'site_js.response.bin':SITE.encode(),'default_weighting.response.bin':encoded(dict(sEcho=1,iTotalRecords=0,iTotalDisplayRecords=0,aaData=[])),'default_weighting.request.json':encoded(q)};outputs=[]
 for name,url in m.URLS.items():
  b=raws[name+'.response.bin'];ref=dict(path='/synthetic/'+name+'.response.bin',sha256=m.digest(b),byte_count=len(b));outputs.append(ref)
  r=dict(schema='OFFICIAL_GIW_DEFAULT_WEIGHTING_RECEIPT_V1',name=name,body_complete=True,error=None,transport_metadata=dict(http_status=200,response_url=url),request=q if name=='default_weighting'else dict(method='GET',url=url,body_ascii=None),response_reference=ref,started_at_utc='2026-10-03T05:00:00+00:00',completed_at_utc='2026-10-03T05:00:01+00:00',**dict.fromkeys(m.FALSE_FLAGS,False))
  raws[name+'.receipt.json']=encoded(r)
 raws['manifest.json']=encoded(dict(schema='OFFICIAL_GIW_DEFAULT_WEIGHTING_CAPTURE_V1',status='DEFAULT_PUBLIC_RESPONSES_SAVED_NOT_INTERPRETED',successful_http200_response_count=3,outputs=outputs,**dict.fromkeys(m.FALSE_FLAGS,False)))
 return raws,HTML.encode()
class Tests(unittest.TestCase):
 def test_empty_not_universe_or_reason(self):
  r,h=fixture();d=m.inspect(r,h);self.assertEqual(d['status'],'EMPTY_PUBLIC_RESPONSE_NOT_EMPTY_UNIVERSE');self.assertFalse(d['universe_empty']);self.assertIsNone(d['member_effective_date']);self.assertEqual(d['empty_response_reason'],'UNKNOWN_NOT_INFERRED_FROM_WEEKEND_OR_ACCESS_POLICY')
 def test_response_counts_types_duplicates_and_rows_rejected(self):
  for obj in [dict(sEcho=1,iTotalRecords=False,iTotalDisplayRecords=0,aaData=[]),dict(sEcho=1,iTotalRecords=0,iTotalDisplayRecords=0.0,aaData=[]),dict(sEcho=1,iTotalRecords=0,iTotalDisplayRecords=0,aaData=[{}])]:
   r,h=fixture();r['default_weighting.response.bin']=encoded(obj)
   with self.assertRaises(ValueError):m.inspect(r,h)
  with self.assertRaises(ValueError):m.parse(b'{"iTotalRecords":0,"iTotalRecords":0}')
 def test_request_js_receipt_identity_and_authority(self):
  for kind in ('date','rawpath','js','authority','body'):
   with self.subTest(kind=kind):
    r,h=fixture()
    if kind=='js':r['weighting_js.response.bin']=b'no default code'
    else:
     name='default_weighting.receipt.json';v=json.loads(r[name])
     if kind=='date':v['request']['form']['tradeDate']='2026-10-02T00:00:00.000'
     elif kind=='rawpath':v['response_reference']['path']='/other/default_weighting.response.bin'
     elif kind=='authority':v['point_in_time_verified']=0
     else:v['request']['body_ascii']='changed'
     r[name]=encoded(v)
    with self.assertRaises(ValueError):m.inspect(r,h)
if __name__=='__main__':unittest.main()

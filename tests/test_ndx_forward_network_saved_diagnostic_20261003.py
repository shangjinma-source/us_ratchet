import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_sina_saved_day_response_research import fixture
from backtest import ndx_sina_saved_day_response_v2_research as core
spec=importlib.util.spec_from_file_location('savedv2',Path(__file__).resolve().parents[1]/'scripts/ndx_forward_network_saved_diagnostic_20261003.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def inputs():
    raw={};refs={}
    for t in ('QQQ','SPY'):
        b,c,_=fixture(t);raw['raw_'+t]=core.EXACT_BANNER+b;raw['baseline_'+t]=c
    for r in ('old_core','old_producer'):raw[r]=b'synthetic'
    for r,b in raw.items():refs[r]={'path':r,'sha256':m.sha(b)}
    start=dict(schema='FORWARD_NETWORK_DAY_RECEIPT_STARTED_V1',target_session='2026-10-02',tickers=['QQQ','SPY'],started_at_utc='2026-10-02T21:00:00+00:00',source_hashes={refs[r]['path']:refs[r]['sha256'] for r in m.OTHER},baseline_references={t:refs['baseline_'+t] for t in ('QQQ','SPY')},**dict.fromkeys(m.PARENT_FALSE,False))
    fail=dict(schema='FORWARD_NETWORK_DAY_RECEIPT_FAILURE_V1',type='ValueError',message='Unsupported JSONP envelope; retain raw and block',retry_allowed=False,failed_at_utc='2026-10-02T21:05:00+00:00',**dict.fromkeys(m.PARENT_FALSE,False))
    raw['started']=m.encode(start);raw['failure']=m.encode(fail)
    for i,t in enumerate(('QQQ','SPY')):
        url='https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_='+t+'_day/US_MinKService.getDailyK?symbol='+t
        receipt=dict(raw_reference=refs['raw_'+t],ticker=t,saved_byte_count=len(raw['raw_'+t]),network_attempt_count=1,http_status=200,response_complete=True,transport_error=None,retry_allowed=False,redirects_allowed=False,request_url=url,final_url=url,started_at_utc=f'2026-10-02T21:0{i+1}:00+00:00',completed_at_utc=f'2026-10-02T21:0{i+1}:30+00:00')
        raw['receipt_'+t]=m.encode(receipt)
    for r,b in raw.items():refs[r]={'path':r,'sha256':m.sha(b)}
    return raw,refs

class Tests(unittest.TestCase):
    def test_exact_banner_offsets_original_hash(self):
        b,c,_=fixture();raw=core.EXACT_BANNER+b
        result=core.inspect_response(raw_bytes=raw,ticker='QQQ',baseline_csv_bytes=c)
        self.assertEqual(result['raw_sha256'],m.sha(raw));self.assertEqual(result['parsing_bytes_sha256'],m.sha(b));self.assertEqual(result['parsing_byte_offset'],len(core.EXACT_BANNER));self.assertFalse(result['fresh_observation'])
        for prefix in (core.EXACT_BANNER.replace(b'sina',b'evil'),b'/* arbitrary */\n',core.EXACT_BANNER*2):
            with self.assertRaises(ValueError):core.inspect_response(raw_bytes=prefix+b,ticker='QQQ',baseline_csv_bytes=c)
    def test_parent_roles_and_raw_tampering(self):
        raw,refs=inputs();m.validate(raw,refs)
        receipt=json.loads(raw['receipt_QQQ']);receipt['raw_reference']['sha256']='f'*64;raw['receipt_QQQ']=m.encode(receipt)
        with self.assertRaises(ValueError):m.validate(raw,refs)
    def test_offline_mock_publish_failure_and_noexecute(self):
        with patch.object(m,'load',side_effect=AssertionError('not invoked')):self.assertEqual(m.run()['status'],'NOT_EXECUTED')
        for drift in (False,True):
            with tempfile.TemporaryDirectory() as folder:
                out=Path(folder)/'new';raw,refs=inputs()
                with patch.object(m,'OUTPUT',out),patch.object(m,'load',return_value=(raw,refs,{},core)),patch.object(m,'guard',side_effect=ValueError('drift') if drift else None):
                    if drift:
                        with self.assertRaises(ValueError):m.run(execute=True)
                        self.assertTrue((out/'failure.json').exists())
                    else:
                        result=m.run(execute=True);self.assertEqual(m.sha(Path(result['path']).read_bytes()),result['sha256']);self.assertEqual(len(list(out.iterdir())),3)
                    with self.assertRaises(ValueError):m.run(execute=True)
if __name__=='__main__':unittest.main()

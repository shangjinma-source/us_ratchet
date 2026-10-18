import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_sina_saved_day_response_research import fixture

spec=importlib.util.spec_from_file_location('receipt',Path(__file__).resolve().parents[1]/'scripts/ndx_forward_network_day_receipt_20261003.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
    def test_noexecute_and_namespace_no_retry(self):
        with patch.object(m,'load',side_effect=AssertionError('no load')):
            self.assertEqual(m.run()['status'],'NOT_EXECUTED')
            with self.assertRaises(ValueError):m.run(execute=1)
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'OUTPUT',Path(folder)):
            with patch.object(m,'load',side_effect=AssertionError('no load')),self.assertRaises(ValueError):m.run(execute=True)
    def test_raw_and_receipt_before_parser_error(self):
        from backtest import ndx_sina_saved_day_response_research as core
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'new'
            def receive(t,p):
                m.write(p,b'bad JSONP')
                return dict(raw_reference={'path':str(p),'sha256':m.sha(b'bad JSONP')},transport_error=None,response_complete=True,http_status=200,final_url='url',request_url='url',response_headers={})
            with patch.object(m,'OUTPUT',output),patch.object(m,'load',return_value=({}, {t:fixture(t)[1] for t in ('QQQ','SPY')}, {},core)),patch.object(m,'receive',side_effect=receive):
                with self.assertRaises(ValueError):m.run(execute=True)
                self.assertTrue((output/'SPY.response.bin').exists());self.assertTrue((output/'SPY.receipt.json').exists());self.assertTrue((output/'QQQ.response.bin').exists());self.assertTrue((output/'QQQ.receipt.json').exists());self.assertTrue((output/'failure.json').exists())
                with self.assertRaises(ValueError):m.run(execute=True)
    def test_mock_success_complete_exact_bytes_no_csv(self):
        from backtest import ndx_sina_saved_day_response_research as core
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'new'
            def receive(t,p):
                b=fixture(t)[0];rr=m.write(p,b)
                return dict(raw_reference=rr,transport_error=None,response_complete=True,http_status=200,final_url='url',request_url='url',response_headers={})
            with patch.object(m,'OUTPUT',output),patch.object(m,'load',return_value=({}, {t:fixture(t)[1] for t in ('QQQ','SPY')}, {},core)),patch.object(m,'receive',side_effect=receive):
                result=m.run(execute=True);self.assertEqual(len(list(output.iterdir())),7)
                saved=json.loads((output/'diagnostic.json').read_text());self.assertFalse(saved['observable_csv_derived']);self.assertEqual(m.sha(Path(result['path']).read_bytes()),result['sha256'])
    def test_receive_late_eof_and_close_failure_preserve_raw(self):
        from unittest.mock import Mock
        for close_bad in (False,True):
            with tempfile.TemporaryDirectory() as folder:
                response=Mock();response.code=200;response.headers={};response.geturl.return_value='url'
                response.read.side_effect=[b'raw',b'']
                if close_bad:response.close.side_effect=OSError('close failed')
                opener=Mock();opener.open.return_value=response
                times=[0,0,1,1,2] if close_bad else [0,0,1,1,100]
                with patch.object(m,'build_opener',return_value=opener),patch.object(m.time,'monotonic',side_effect=times):
                    result=m.receive('QQQ',Path(folder)/'raw')
                self.assertEqual((Path(folder)/'raw').read_bytes(),b'raw')
                self.assertIsNotNone(result['transport_error']);self.assertIsNotNone(result['completed_at_utc'])
                if not close_bad:self.assertFalse(result['response_complete'])
if __name__=='__main__':unittest.main()

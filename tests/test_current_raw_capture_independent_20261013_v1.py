"""New fake-transport cases. No HTTP or author-suite replay."""
from pathlib import Path
import hashlib,importlib.util,io,gzip,json,tempfile,unittest
from unittest.mock import patch
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'scripts/ndx_current_raw_capture_20261013.py'
RAW=SOURCE.read_bytes();PIN='2a72692831c3b09671a8f973c795d71655c8f9a4f2ffe3689e8bdfe06ce263d5'
assert hashlib.sha256(RAW).hexdigest()==PIN
spec=importlib.util.spec_from_file_location('independent_rawtransport',SOURCE);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
CLOCK=datetime(2026,10,13,4,17,tzinfo=timezone.utc)


class FakeResponse(io.BytesIO):
    def __init__(self,raw,url,status=200):super().__init__(raw);self.url=url;self.status=status;self.headers={'Content-Encoding':'gzip'}


def body():
    stamps=[int(datetime(2026,10,12,13,30,tzinfo=timezone.utc).timestamp()),int(datetime(2026,10,13,4,1,tzinfo=timezone.utc).timestamp())]
    return json.dumps({'chart':{'error':None,'result':[{'meta':{'symbol':'TESTZ','currency':'USD','exchangeTimezoneName':'America/New_York','dataGranularity':'1d'},'timestamp':stamps,'indicators':{'quote':[{'open':[17,18],'high':[19,19],'low':[16,17],'close':[18,None],'volume':[1000,None]}]},'events':{'dividends':{'event':{'amount':.2}}}}]}}).encode()


class IndependentCapture(unittest.TestCase):
    def test_gzip_success_rawfirst_durable_order_prior_target_not_certified(self):
        with tempfile.TemporaryDirectory()as temp:
            output=Path(temp)/'capture';saved=[];transport=[];original=s.save;raw=gzip.compress(body())
            def save(path,value):
                if path.name.endswith('receipt.json'):self.assertEqual((output/'TESTZ.response.bin').read_bytes(),raw)
                saved.append(path.name);return original(path,value)
            def opener(request,**kw):
                self.assertEqual(saved,['TESTZ.started.json']);self.assertTrue((output/'TESTZ.started.json').exists());transport.append(request.full_url)
                return FakeResponse(raw,request.full_url)
            with patch.object(s,'OUTPUT',output),patch.object(s,'guard',return_value=['TESTZ']),patch.object(s,'save',side_effect=save):r=s.run(runner_sha=PIN,execute=True,opener=opener,clock=lambda:CLOCK)
            self.assertEqual(len(transport),1);self.assertEqual(saved,['TESTZ.started.json','TESTZ.receipt.json','TESTZ.decoded.json','completion_index_001.json'])
            d=json.loads((output/'TESTZ.decoded.json').read_bytes());self.assertEqual(d['status'],'RAW_TARGET_OHLCV_PRESENT_NOT_CALENDAR_CERTIFIED');self.assertEqual(d['target_date'],'2026-10-12');self.assertEqual(d['excluded_dates'],['2026-10-13'])
            self.assertEqual(d['decoded_sha256'],s.digest(body()));self.assertEqual(d['receipt_new_york_date'],'2026-10-13');self.assertFalse(d['quote_basis_authenticated']);self.assertFalse(d['point_in_time_membership_verified']);self.assertFalse(d['prices_reconstructed'])

    def test_failures_retain_exact_evidence_and_completed_attempt_never_retries(self):
        for kind in ('503','partial','badgzip','bodylimit'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory()as temp:
                output=Path(temp)/'capture';calls=[]
                raw=b'service unavailable'if kind=='503'else b'prefix-retained'if kind=='partial'else b'\x1f\x8bbroken'if kind=='badgzip'else b'x'*65
                def opener(request,**kw):
                    calls.append(request.full_url);response=FakeResponse(raw,request.full_url,503 if kind=='503' else 200);read=response.read;state=[0]
                    if kind=='partial':
                        def interrupted(size):
                            state[0]+=1
                            if state[0]>1:raise TimeoutError('secondchunk stopped')
                            return read(size)
                        response.read=interrupted
                    return response
                with patch.object(s,'OUTPUT',output),patch.object(s,'guard',return_value=['TESTZ']),patch.object(s,'MAX_BYTES',64):
                    r=s.run(runner_sha=PIN,execute=True,opener=opener,clock=lambda:CLOCK)
                    self.assertEqual(r['statuses'],[{'503':'HTTP_FAILED','partial':'TRANSPORT_FAILED','badgzip':'DECODE_FAILED','bodylimit':'BODY_LIMIT_FAILED'}[kind]])
                    self.assertEqual((output/'TESTZ.response.bin').read_bytes(),raw)
                    no_retry=s.run(runner_sha=PIN,execute=True,index_sha=r['last_index_sha256'],opener=opener,clock=lambda:CLOCK)
                    self.assertEqual(no_retry['network_requests'],0);self.assertEqual(len(calls),1)

    def test_orphan_lock_and_clock_boundaries_block_before_opener(self):
        for evidence in ('TESTZ.started.json','.batch.lock'):
            with tempfile.TemporaryDirectory()as temp:
                output=Path(temp);(output/evidence).write_bytes(b'untouched');before=(output/evidence).read_bytes()
                with patch.object(s,'OUTPUT',output),patch.object(s,'guard',return_value=['TESTZ']),patch.object(s,'default_open',side_effect=AssertionError('HTTP forbidden')):
                    with self.assertRaisesRegex(ValueError,'orphan'):s.run(runner_sha=PIN,execute=True,opener=lambda *_a,**_k:self.fail('network'),clock=lambda:CLOCK)
                self.assertEqual((output/evidence).read_bytes(),before)
        for clock in (datetime(2026,10,13,3,59,59,tzinfo=timezone.utc),datetime(2026,10,14,0,0,tzinfo=timezone.utc),datetime(2026,10,13,4,17)):
            with self.assertRaises(ValueError):s.validate_clock(clock)
        s.validate_clock(CLOCK)

    def test_real_fixed_observation_denominator_has_new_member_not_removed_member(self):
        queue=s.guard(PIN);raw=s.OBSERVATION.read_bytes();obs=json.loads(raw)
        self.assertEqual(queue,list(dict.fromkeys(obs['observed_symbols']+['TSM','QQQ','SPY'])))
        self.assertEqual(len(queue),104);self.assertIn('MRNA',queue);self.assertNotIn('WBD',queue)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'41573c3b20f683f1565e969be689d1eac52b4d1b4fb0d29d8c5b9c477e371fbf')
        self.assertFalse(obs['point_in_time_membership_verified']);self.assertFalse(s.FLAGS['legal_training_input_admitted'])


if __name__=='__main__':unittest.main()

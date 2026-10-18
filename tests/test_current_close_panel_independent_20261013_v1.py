"""Fresh adapter fake-domain tests; no actual raw sources, fitting or HTTP."""
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from copy import deepcopy
from types import SimpleNamespace
import hashlib,importlib.util,json,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'data/current_research_close_panel.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='5ebacf528557a869b28b532b79852964b0ed6d1865c553626618284b34c3841d'
spec=importlib.util.spec_from_file_location('independent_closepanel',SOURCE);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


def channels_fixture():
    dates=[(date(2026,10,12)-timedelta(days=378-i)).isoformat()for i in range(379)]+['2026-10-13']
    symbols=['MRNA']+[f'FAK{i}'for i in range(100)];channels={}
    for ticker in symbols+list(s.CONTROLS):
        channels[ticker]=dict(ticker=ticker,dates=list(dates),closes=[100.]*380,control=ticker in s.CONTROLS,raw_sha256='a'*64,decoded_sha256='b'*64,events_sha256='c'*64,splits_payload_sha256='d'*64,dividends_payload_sha256='e'*64,splits_count=0,dividends_count=0)
    return symbols,channels,dates


def raw_channel(ticker,days):
    stamps=[int(datetime.fromisoformat(d).replace(hour=13,minute=30,tzinfo=timezone.utc).timestamp())for d in days]
    return json.dumps({'chart':{'error':None,'result':[{'meta':{'symbol':ticker,'currency':'USD','instrumentType':'ETF'if ticker in ('QQQ','SPY')else 'EQUITY','exchangeTimezoneName':'America/New_York','dataGranularity':'1d'},'timestamp':stamps,'indicators':{'quote':[{'close':[77.]*len(days)}]},'events':{}}]}}).encode()


class IndependentPanel(unittest.TestCase):
    def test_fake104_full379_preserves_missing_null_shortipo_and_control_separation(self):
        symbols,channels,days=channels_fixture()
        channels['MRNA']['dates']=days[340:];channels['MRNA']['closes']=[90.]*40
        channels['FAK0']['dates'].pop(200);channels['FAK0']['closes'].pop(200)
        channels['FAK1']['closes'][210]=None
        panel=s.bind_observed_close_panel(observed_symbols=symbols,channels=channels)
        self.assertEqual(panel['observation_sessions'],379);self.assertEqual(len(panel['stocks']),101);self.assertEqual(len(panel['controls']),3)
        stock={r['ticker']:r for r in panel['stocks']};self.assertEqual(stock['MRNA']['unavailable_prefix_sessions'],340);self.assertEqual(stock['MRNA']['raw_close'][:340],[None]*340)
        self.assertEqual(stock['FAK0']['missing_dates'],[days[200]]);self.assertEqual(stock['FAK1']['null_close_dates'],[days[210]])
        self.assertIsNone(stock['FAK0']['raw_close'][200]);self.assertIsNone(stock['FAK1']['raw_close'][210]);self.assertEqual(stock['FAK1']['excluded_future_dates'],['2026-10-13'])
        self.assertEqual([r['ticker']for r in panel['controls']],['TSM','QQQ','SPY']);self.assertTrue(all(r['role']=='REFERENCE_ONLY_NEVER_TRAIN'for r in panel['controls']));self.assertTrue(set(stock).isdisjoint(s.CONTROLS))
        self.assertFalse(panel['qualified']);self.assertFalse(panel['security_identity_verified']);self.assertTrue(panel['no_sid_created']);self.assertTrue(panel['price_basis'].startswith('CONDITIONAL_'))

    def test_default_zero_reads_and_fakefixed_loader_never_tails253(self):
        with patch.object(s,'_read_fixed',side_effect=AssertionError('Default read forbidden')),patch.object(Path,'read_bytes',side_effect=AssertionError('Default filesystem IO')):
            default=s.load_current_close_panel();self.assertEqual(default['file_reads'],0)
        symbols,_,days=channels_fixture();queue=symbols+list(s.CONTROLS)
        blobs={ticker:raw_channel(ticker,days)for ticker in queue};entries=[dict(ticker=t,raw_sha256=hashlib.sha256(blobs[t]).hexdigest())for t in queue]
        docs={'observation':{'observed_symbols':symbols,'point_in_time_membership_verified':False},'final_index':{'queue':queue,'entries':entries,'completed_attempts':104,'target_date':'2026-10-12'},'independent_readback':{'channels':104,'all_target_fullraw_present':104,'source_unchanged':True,'channel_checks':[dict(ticker=t,raw_sha256=e['raw_sha256'],provider_dates=days)for t,e in zip(queue,entries)]},'inventory':{'rows':[dict(ticker=t)for t in symbols]}}
        lookup={str(p):json.dumps(docs[role]).encode()for role,(p,_)in s.FIXED_REFERENCES.items()};calls=[]
        def take(path,expected):
            calls.append(str(path))
            if str(path)in lookup:return lookup[str(path)]
            ticker=path.name.removesuffix('.response.bin');self.assertIn(ticker,queue);self.assertEqual(expected,hashlib.sha256(blobs[ticker]).hexdigest());return blobs[ticker]
        with patch.object(s,'_read_fixed',side_effect=take):panel=s.load_current_close_panel(execute=True)
        self.assertEqual(len(panel['calendar']),379);self.assertEqual(panel['calendar'],days[:-1]);self.assertEqual(len(calls),112)
        self.assertFalse(panel['publication_performed']);self.assertEqual(panel['actual_http_requests'],0);self.assertFalse(panel['fit_performed']);self.assertFalse(panel['optimization_performed'])

    def test_fixed_read_regular_reparse_hash_and_json_number_guards(self):
        with tempfile.TemporaryDirectory()as td:
            p=Path(td)/'input.json';p.write_bytes(b'{"ok":1}');digest=hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(s._read_fixed(p,digest),b'{"ok":1}')
            with self.assertRaisesRegex(ValueError,'SHA'):s._read_fixed(p,'0'*64)
            with self.assertRaisesRegex(ValueError,'regular'):s._read_fixed(Path(td),digest)
            original=Path.lstat
            def reparse(path,*args,**kw):
                r=original(path,*args,**kw)
                return SimpleNamespace(st_mode=r.st_mode,st_file_attributes=1024)if path==p.parent else r
            with patch.object(Path,'lstat',reparse),patch.object(Path,'open',side_effect=AssertionError('Read through reparse')):
                with self.assertRaisesRegex(ValueError,'reparse'):s._read_fixed(p,digest)
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1e999}'):
            with self.assertRaises(ValueError):s._loads(raw)
        symbols,channels,_=channels_fixture();channels['FAK0']['closes'][100]=True
        with self.assertRaises(ValueError):s.bind_observed_close_panel(observed_symbols=symbols,channels=channels)
        with self.assertRaises(ValueError):s.bind_observed_close_panel(observed_symbols=['QQQ'],channels=channels)


if __name__=='__main__':unittest.main()

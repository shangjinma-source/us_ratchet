"""Synthetic tests only: no real assembler run, network, fit or account."""
import copy
from datetime import datetime, timezone
from decimal import Decimal, localcontext, ROUND_DOWN, Inexact
import hashlib
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'scripts/ndx_return_eight_price_only_20260923.py'
spec=importlib.util.spec_from_file_location('eight_price',SOURCE)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture(ticker='AMAT'):
    calendar=[d for d in json.loads(module.CALENDAR.read_bytes())['calendar'] if '2023-03-31'<=d<='2023-09-01']
    stamp=lambda d:int(datetime.fromisoformat(d+'T14:00:00+00:00').timestamp())
    times=[stamp(d) for d in calendar];factor=10 if ticker=='AVGO' else 1
    events={}
    if factor==10:
        epoch=stamp('2024-07-15');times.append(epoch)
        events={'splits':{str(epoch):{'date':epoch,'numerator':10,'denominator':1,'splitRatio':'10:1'}}}
    data={'meta':dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),
        'timestamp':times,'indicators':{'quote':[{'open':[12.125]*len(times),'close':[13.125]*len(times)}]},'events':events}
    raw=json.dumps({'chart':{'error':None,'result':[data]}}).encode()
    rows=[dict(session=d,ticker=ticker,currency='USD',provider_timestamp=stamp(d),quote_open=12.125,quote_close=13.125,
        nominal_open=12.125*factor,nominal_close=13.125*factor,split_factor=factor,split_factor_numerator=str(factor),
        split_factor_denominator='1',later_split_effective_sessions=['2024-07-15'] if factor==10 else []) for d in calendar]
    return dict(ticker=ticker,raw=raw,raw_sha256=hashlib.sha256(raw).hexdigest(),
        request={'method':'GET','credentials_sent':False,'url':f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1=1640995200&period2=1789754400&interval=1d&events=div,splits'},
        received_at_utc='2026-09-18T18:13:58+00:00',calendar=calendar,rows=rows,basis=module.BASIS)


class PriceTests(unittest.TestCase):
    def test_transport_and_decoded_hashes_are_distinct(self):
        f=fixture();decoded=f['raw'];f['raw']=gzip.compress(decoded)
        f['raw_sha256']=hashlib.sha256(f['raw']).hexdigest()
        result=module.inspect_channel(**f)
        self.assertEqual(result['decoded_sha256'],hashlib.sha256(decoded).hexdigest())
        self.assertEqual(result['raw_sha256'],f['raw_sha256'])
        self.assertNotEqual(result['decoded_sha256'],result['raw_sha256'])

    def test_avgo_applied_once_context_independent(self):
        f=fixture('AVGO')
        expected=module.inspect_channel(**f)
        with localcontext() as ctx:
            ctx.prec=2;ctx.rounding=ROUND_DOWN;ctx.traps[Inexact]=True
            self.assertEqual(module.inspect_channel(**f),expected)
        self.assertEqual(expected['cells_checked'],214)
        self.assertEqual(expected['rows'][0]['open'],'121.250')
        self.assertEqual(expected['window_event_counts'],dict(splits=0,dividends=0))

    def test_bool_duplicate_missing_nonfinite(self):
        for attack in ('bool','duplicate','missing','nan'):
            f=fixture();data=json.loads(f['raw']);chart=data['chart']['result'][0]
            if attack=='bool':chart['indicators']['quote'][0]['open'][0]=True
            if attack=='duplicate':chart['timestamp'][1]=chart['timestamp'][0]
            if attack=='missing':chart['timestamp'].pop()
            if attack=='nan':chart['indicators']['quote'][0]['close'][0]=float('nan')
            f['raw']=json.dumps(data).encode();f['raw_sha256']=hashlib.sha256(f['raw']).hexdigest()
            with self.subTest(attack=attack),self.assertRaises(ValueError):module.inspect_channel(**f)

    def test_dividend_count_never_factor(self):
        f=fixture();data=json.loads(f['raw']);chart=data['chart']['result'][0];epoch=chart['timestamp'][0]
        chart['events']={'dividends':{str(epoch):{'date':epoch,'amount':5}}}
        f['raw']=json.dumps(data).encode();f['raw_sha256']=hashlib.sha256(f['raw']).hexdigest()
        result=module.inspect_channel(**f)
        self.assertEqual(result['window_event_counts']['dividends'],1)
        self.assertEqual(result['rows'][0]['open'],'12.125')

    def test_semantic_replay_rejects_matrix_tamper(self):
        expected={'matrices':{'open':{'2023-03-31':{'AMAT':'12.125'}}},'price_cell_count':1712}
        bad=copy.deepcopy(expected);bad['matrices']['open']['2023-03-31']['AMAT']='1'
        with patch.object(module,'build',return_value=expected):
            self.assertEqual(module.verify(expected),expected)
            with self.assertRaises(ValueError):module.verify(bad)

    def test_source_drift_and_single_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source';path.write_bytes(b'a');sources={str(path):hashlib.sha256(b'a').hexdigest()}
            module.verify_sources(sources);path.write_bytes(b'b')
            with self.assertRaises(ValueError):module.publish(Path(tmp)/'out',{},sources)
            self.assertFalse((Path(tmp)/'out').exists())
            with self.assertRaises(ValueError):module.run(tmp)


if __name__=='__main__':unittest.main()

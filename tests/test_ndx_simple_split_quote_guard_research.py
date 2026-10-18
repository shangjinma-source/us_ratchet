from copy import deepcopy
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backtest import ndx_simple_split_quote_guard_research as guard


def fixture():
    days=['2022-06-03','2022-06-06'];times=[int(datetime.fromisoformat(day+'T13:30:00+00:00').timestamp()) for day in days]
    end=int(datetime.fromisoformat('2022-06-07T00:00:00+00:00').timestamp())
    data=dict(meta=dict(symbol='AMZN',currency='USD',exchangeTimezoneName='America/New_York',instrumentType='EQUITY',dataGranularity='1d'),
        timestamp=times,indicators=dict(quote=[dict(open=[1.,2.],close=[2.,3.])]),
        events=dict(splits={str(times[1]):dict(date=times[1],numerator=20.,denominator=1.,splitRatio='20:1')}))
    params=dict(ticker='AMZN',calendar=days,request=dict(method='GET',credentials_sent=False,
        url=f'https://query1.finance.yahoo.com/v8/finance/chart/AMZN?period1={times[0]-86400}&period2={end}&interval=1d&events=div%2Csplits'),
        received_at_utc='2022-06-07T00:01:00+00:00',quote_field_basis=guard.nominal.BASIS)
    return dict(chart=dict(error=None,result=[data])),params


def execute(directory,payload,params,compressed=False):
    decoded=json.dumps(payload).encode();raw=gzip.compress(decoded,mtime=0) if compressed else decoded
    path=Path(directory)/'response.bin';path.write_bytes(raw)
    return guard.reconstruct_guarded_nominal_quote(raw_path=path,raw_sha256=hashlib.sha256(raw).hexdigest(),
        content_encoding='gzip' if compressed else 'identity',**params)


class SplitGuardTests(unittest.TestCase):
    def test_specific_supported_event_and_gzip_raw_decoded_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            payload,params=fixture();result=execute(directory,payload,params,True)
            self.assertEqual([r['split_factor'] for r in result['reconstruction']['rows']],[20.,1.])
            self.assertEqual(result['returned_event_count'],1)
            self.assertNotEqual(result['raw_decoding_evidence']['raw_sha256'],result['raw_decoding_evidence']['decoded_sha256'])
            self.assertFalse(result['complete_corporate_action_history_verified']);self.assertFalse(result['price_identity_verified'])

    def test_any_unmatched_date_ratio_or_additional_event_rejects_before_old_engine(self):
        for fault in ('ratio','date','extra'):
            with tempfile.TemporaryDirectory() as directory:
                payload,params=fixture();splits=payload['chart']['result'][0]['events']['splits'];key=next(iter(splits));event=splits[key]
                if fault=='ratio':event.update(numerator=2.,splitRatio='2:1')
                else:
                    timestamp=event['date']+86400;changed=dict(event,date=timestamp)
                    if fault=='date':splits.clear()
                    splits[str(timestamp)]=changed
                with patch.object(guard.nominal,'reconstruct_nominal_quote_ticker') as old:
                    with self.assertRaisesRegex(ValueError,'lacks exact supported'):execute(directory,payload,params)
                    old.assert_not_called()

    def test_complex_tickers_block_even_empty_returned_events(self):
        report,_=guard.load_specific_facts()
        for ticker in guard.BLOCKED:
            payload,_=fixture();payload['chart']['result'][0]['meta']['symbol']=ticker;payload['chart']['result'][0]['events']={}
            with self.assertRaisesRegex(ValueError,'Complex corporate action'):
                guard.match_returned_events(decoded=json.dumps(payload).encode(),ticker=ticker,specific_events=report['specific_events'],blocked_tickers=guard.BLOCKED)

    def test_zero_events_does_not_certify_no_action_and_unknown_basis_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            payload,params=fixture();payload['chart']['result'][0]['events']={}
            result=execute(directory,payload,params)
            self.assertTrue(result['no_returned_events_observed']);self.assertFalse(result['absence_of_returned_events_proves_no_corporate_actions'])
            with self.assertRaises(ValueError):execute(directory,payload,dict(params,quote_field_basis='UNKNOWN'))

    def test_raw_sha_checked_before_gzip_and_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'invalid.gz';path.write_bytes(b'invalid gzip')
            with patch.object(guard.gzip,'decompress') as decode:
                with self.assertRaisesRegex(ValueError,'before decoding'):
                    guard.decode_bound_raw(raw_path=path,raw_sha256='0'*64,content_encoding='gzip')
                decode.assert_not_called()
            payload,_=fixture();raw=json.dumps(payload).replace('"symbol": "AMZN"','"symbol":"AMZN","symbol":"AMZN"').encode()
            with self.assertRaisesRegex(ValueError,'Duplicate raw JSON'):
                guard.match_returned_events(decoded=raw,ticker='AMZN',specific_events=[],blocked_tickers=guard.BLOCKED)

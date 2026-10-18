"""Synthetic response tests only; no actual assembly build or publication."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import localcontext
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_legacy_twelve_price_only_20260923 as m


def calendar():
    return json.loads((m.BASE/'return_six_period_benchmarks_20260923_v1/benchmarks.json').read_bytes())['calendar']


def fixture(ticker='QCOM',compressed=False,mutate=None):
    days=calendar();stamps=[int(datetime.fromisoformat(d+'T16:00:00+00:00').timestamp()) for d in days]
    result=dict(meta=dict(symbol=ticker,currency='USD',exchangeTimezoneName='America/New_York',instrumentType='EQUITY',dataGranularity='1d'),
        timestamp=stamps,indicators=dict(quote=[dict(open=[100.125]*107,close=[101.0625]*107)],adjclose=[dict(adjclose=[1]*107)]),
        events=dict(dividends={str(stamps[1]):dict(date=stamps[1],amount=.75)}))
    if mutate:mutate(result)
    decoded=json.dumps(dict(chart=dict(error=None,result=[result]))).encode();raw=gzip.compress(decoded) if compressed else decoded
    sha=hashlib.sha256(raw).hexdigest();started=datetime.fromtimestamp(m.PERIOD2[ticker],timezone.utc).isoformat()
    received=datetime.fromtimestamp(m.PERIOD2[ticker]+1,timezone.utc).isoformat()
    meta=dict(http_status=200,final_url=m.request_url(ticker),started_at_utc=started,received_at_utc=received)
    if ticker=='TEAM':meta.update(response_sha256=sha,response_bytes=len(raw),response_path=m.reference(ticker+'_raw')['path'],transport_success=True,
        request=dict(method='GET',credentials_sent=False,url=m.request_url(ticker)))
    else:meta.update(raw_sha256=sha,raw_bytes=len(raw),raw_path=m.reference(ticker+'_raw')['path'],request_method='GET',credentials_sent=False,
        request_url=m.request_url(ticker),ticker=ticker,attempt_count=1,period2_utc_epoch=m.PERIOD2[ticker],
        completed_training_excludes_dates_on_or_after=datetime.fromisoformat(received).astimezone(m.NY).date().isoformat(),promotion_allowed=False,historical_identity_verified=False)
    bound=deepcopy(m.BOUND);bound[ticker+'_raw']=(bound[ticker+'_raw'][0],sha)
    return raw,meta,days,bound,decoded


class PriceTests(unittest.TestCase):
    def test_gzip_separate_hashes_events_retained_adjclose_unused(self):
        raw,meta,days,bound,decoded=fixture(compressed=True)
        with patch.dict(m.BOUND,bound):channel=m.decode('QCOM',raw,meta,days)
        self.assertNotEqual(channel['transport_sha256'],channel['decoded_sha256'])
        self.assertEqual(channel['decoded_sha256'],hashlib.sha256(decoded).hexdigest())
        self.assertEqual(channel['rows'][0]['open'],'100.125')
        self.assertEqual(channel['window_dividend_events'][0]['amount'],'0.75')
        self.assertEqual(channel['returned_event_counts'],dict(splits=0,dividends=1))
        self.assertFalse(channel['adjusted_close_used']);self.assertFalse(channel['dividends_applied_to_quote'])

    def test_raw_bad_tokens_metadata_calendar_events_reject(self):
        attacks=[lambda r:r['indicators']['quote'][0]['open'].__setitem__(0,True),
            lambda r:r['indicators']['quote'][0]['close'].__setitem__(1,None),
            lambda r:r['timestamp'].__setitem__(1,r['timestamp'][0]),
            lambda r:r['meta'].__setitem__('instrumentType','ETF'),
            lambda r:r['meta'].__setitem__('dataGranularity','1wk'),
            lambda r:r['events'].__setitem__('splits',{'1':{'date':1}}),
            lambda r:r['events'].__setitem__('capitalGains',{})]
        for attack in attacks:
            raw,meta,days,bound,_=fixture(mutate=attack)
            with self.subTest(attack=attack),patch.dict(m.BOUND,bound),self.assertRaises(ValueError):m.decode('QCOM',raw,meta,days)
        raw,meta,days,bound,_=fixture()
        with patch.dict(m.BOUND,bound):
            with self.assertRaises(ValueError):m.decode('QCOM',raw,meta,days[:-1])
            meta['request_url']+='&redirect=true'
            with self.assertRaises(ValueError):m.decode('QCOM',raw,meta,days)
        with self.assertRaises(ValueError):m.loads('{"a":1,"a":2}')
        with self.assertRaises(ValueError):m.loads('{"a":NaN}',decimal=True)

    def test_empty_events_and_old_receipt_no_complete_actions_claim(self):
        raw,meta,days,bound,_=fixture('TEAM',mutate=lambda r:r.pop('events'))
        with patch.dict(m.BOUND,bound),localcontext() as context:
            context.prec=2;channel=m.decode('TEAM',raw,meta,days)
        self.assertFalse(channel['raw_events_field_present'])
        self.assertEqual(channel['rows'][0]['close'],'101.0625')
        self.assertIn('NOT_COMPLETE',channel['event_scope'])

    def test_exact_old_strings_and_complete_2568_cells(self):
        days=calendar();matrices={k:{d:{t:'630.54000854492190' if t=='AVGO' else '100.125' for t in m.OLD} for d in days} for k in ('open','close')}
        channels=[dict(ticker=t,cells_checked=214,rows=[dict(session=d,open=matrices['open'][d][t],close=matrices['close'][d][t]) for d in days]) for t in m.OLD]
        parent=dict(schema='RETURN_EIGHT_107_OBSERVED_SESSION_CONDITIONAL_PRICE_ONLY_V1',calendar=days,matrices=matrices,channels=channels,point_in_time_verified=False,promotion_allowed=False)
        enph=dict(schema='DRAWDOWN_FOUR_SECURITY_107_SESSION_CONDITIONAL_INPUT_V1',calendar=days,price_projection=deepcopy(parent),point_in_time_verified=False,promotion_allowed=False)
        docs=dict(parent=parent,enph=enph,parent_final=dict(raw_reference=m.reference('parent'),price_cell_count=1712,point_in_time_verified=False,promotion_allowed=False),
            benchmark=dict(calendar=days,point_in_time_verified=False,promotion_allowed=False));raws={};bound=deepcopy(m.BOUND)
        for ticker in m.NEW:
            raw,meta,_,partial,_=fixture(ticker);raws[ticker]=raw;docs[ticker+'_meta']=meta;bound[ticker+'_raw']=partial[ticker+'_raw']
        with patch.dict(m.BOUND,bound):value=m.assemble(docs,raws)
        self.assertEqual(value['price_cell_count'],2568)
        self.assertEqual(sum(len(r) for matrix in value['matrices'].values() for r in matrix.values()),2568)
        self.assertEqual(value['matrices']['open'][days[0]]['AVGO'],'630.54000854492190')
        self.assertTrue(all(value[key] is False for key in m.FALSE))
        self.assertNotIn('identity_projection',value)

    def test_tz_source_drift_and_duplicate_namespace_fail_closed(self):
        raw,meta,days,bound,_=fixture()
        with patch.dict(m.BOUND,bound),patch.dict(m.LOADED,{str(m.NY_SOURCE):'0'*64}):
            with self.assertRaises(ValueError):m.decode('QCOM',raw,meta,days)
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'OUTPUT',Path(folder)),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()


if __name__=='__main__':unittest.main()

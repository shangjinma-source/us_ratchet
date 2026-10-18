"""Synthetic saved benchmark metadata and temporary failed publication only."""
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_bulk_long_window_benchmark_requirements_20261003 as m
from backtest import ndx_long_window_benchmark_requirements_research as core

def weekdays(a,b):
    d=date.fromisoformat(a);end=date.fromisoformat(b);out=[]
    while d<=end:
        if d.weekday()<5:out.append(d.isoformat())
        d+=timedelta(days=1)
    return out

def fixture():
    refs={k:dict(path='/synthetic/'+k,sha256='a'*64) for k in m.BOUND}
    a=weekdays('2025-09-18','2026-03-20');b=weekdays('2026-03-23','2026-09-21');days=a[:126]+[a[-1]]+b[:125]+[b[-1]]
    assert len(days)==253 and len(set(days))==253
    securities=[dict(ticker=t,security_id='security:incumbent_overlay:TSM' if t=='TSM' else 'S'+t,issuer_id='I'+t,risk_chain='R'+t,target_weight=.125) for t in m.TICKERS]
    control=dict(definition=dict(securities=securities,starting_capital_usd=25000.,minimum_cash_buffer_usd=100.,transaction_cost_bps=10.),promotion_allowed=False,live_mutation=dict.fromkeys(('broker','config','orders','state','today_advice'),False))
    channels=[];entries=[];sources={};docs={};wiring=[]
    for i,t in enumerate(['AAPL']+m.TICKERS+['X'+str(i) for i in range(93)]):
        rr=refs.get('receipt_'+t,dict(path='/synthetic/receipt_'+t,sha256='a'*64));raw=dict(path='/synthetic/'+t+'.bin',sha256='b'*64);sources[raw['path']]=raw['sha256']
        receipt=dict(ticker=t,http_status=200,request_method='GET',request_url='https://example/chart/'+t,credentials_sent=False,point_in_time_verified=False,promotion_allowed=False,raw_path=raw['path'],raw_sha256=raw['sha256'])
        if t in m.TICKERS:docs['receipt_'+t]=receipt
        entries.append(dict(ticker=t,receipt_path=rr['path'],receipt_sha256=rr['sha256']))
        obs=dict(ticker=t,raw_provider_meta=dict(symbol=t,currency='USD'),decoded_sha256='c'*64,raw_returned_events={'dividends':{'unchanged':1}},quote_price_unit='UNVERIFIED',volume_unit='UNVERIFIED',rows=[dict(new_york_date=d,missing_fields=[],excluded_receipt_day_or_later=False) for d in days])
        channels.append(dict(ticker=t,http_status=200,receipt_sha256=rr['sha256'],receipt_new_york_day='2026-09-23',readback_status='RAW_CHANNEL_READBACK_ONLY',observation=obs))
    for row in securities:
        if row['ticker']!='TSM':wiring.append(dict(ticker=row['ticker'],coordinate=dict(security_id=row['security_id'],issuer_id=row['issuer_id']),original_window=dict(first='2026-03-20',last='2026-09-21')))
    wiring += [dict(ticker='W'+str(i)) for i in range(94)]
    for t in ('TSM','ASML'):
        row=next(r for r in securities if r['ticker']==t);role=t.lower();docs[role]=dict(ticker=t,security_id=row['security_id'],issuer_id=row['issuer_id'],point_in_time_verified=False,promotion_allowed=False,source_hashes={},class_fact='ADS5' if t=='TSM' else 'Ordinary vs New York')
        docs[role+'_publication']=dict(status='PUBLISHED_CONDITIONAL_SID_SIDECAR_ONLY',identity_reference=refs[role],source_hashes={})
    navdays=[d for i,d in enumerate(days) if i%17!=1];navrows=[dict(Date=d,UnitNav='1',Close='1') for d in navdays]
    docs.update(control=control,readback=dict(schema='NEW_CUTOFF_INDEPENDENT_RAW_READBACK_V1',rows=channels,index_path=refs['index']['path'],index_sha256=refs['index']['sha256'],source_hashes=sources),index=dict(entries=entries),wiring=dict(rows=wiring),nav_csv=navrows,nav_manifest=dict(content_sha256=refs['nav_csv']['sha256'],publication_time_known=False,row_count=len(navrows)),nav_snapshot=dict(schema='NEW_CUTOFF_LOCAL_NAV_BYTES_SNAPSHOT_V1',dataset_key='012922',nav_publication_time_verified=False,immutable_copies={'nav.csv':refs['nav_csv'],'original_manifest.json':refs['nav_manifest']}),currency_manifest=dict(source_reference=refs['currency_listing'],nav_dataset_currency_binding_certified=False,fx_rates_supplied=False,point_in_time_verified=False))
    return docs,refs

class Tests(unittest.TestCase):
    def test_full_original8_and_backward_nav_requirements(self):
        docs,refs=fixture();before=deepcopy(docs);args=m.project_inputs(docs,refs);out=core.prepare_benchmark_requirements(**args);m.validate_result(out,args)
        self.assertEqual(docs,before);self.assertEqual(out['stock_date_requirement_count'],2024);self.assertEqual(len(out['nav_date_mappings']),253)
        self.assertEqual(out['original_control_preserved']['securities'],docs['control']['definition']['securities']);self.assertTrue(args['stock_metadata']['TSM']['control_only_overlay']);self.assertFalse(args['stock_metadata']['TSM']['shares_or_prices_converted'])
        self.assertTrue(all(r['nav_date']<=r['session'] for r in out['nav_date_mappings']));self.assertTrue(any(r['lag_calendar_days']>0 for r in out['nav_date_mappings']))

    def test_cross_binding_and_early_authority_rejected(self):
        docs,refs=fixture()
        for mutate in (lambda d:d['receipt_TSM'].update(ticker='NVDA'),lambda d:d['receipt_TSM'].update(raw_sha256='e'*64),lambda d:d['nav_manifest'].update(publication_time_known=True),lambda d:d['tsm'].update(security_id='CONVERTED'),lambda d:d['control']['live_mutation'].update(orders=True)):
            bad=deepcopy(docs);mutate(bad)
            with self.assertRaises(ValueError):m.project_inputs(bad,refs)

    def test_missing_metadata_is_retained_not_filtered(self):
        docs,refs=fixture();obs=next(r for r in docs['readback']['rows'] if r['ticker']=='TSM')['observation'];obs['rows'][100]['missing_fields']=['close'];args=m.project_inputs(docs,refs)
        self.assertEqual(len(args['stock_metadata']['TSM']['observation_rows']),253);self.assertEqual(args['stock_metadata']['TSM']['observation_rows'][100]['missing_fields'],['close'])

    def test_pending_pin_and_failed_publication_no_retry(self):
        with patch.object(m,'CORE_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.load_inputs()
            read.assert_not_called()
        with tempfile.TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)/'new'),patch.object(m,'load_inputs',return_value=({}, {}, {}, None)) as load,patch.object(m,'project_inputs',side_effect=ValueError('metadata conflict')):
            with self.assertRaises(ValueError):m.run()
            self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','failure.json'})
            with self.assertRaises(ValueError):m.run()
            self.assertEqual(load.call_count,1)

if __name__=='__main__':unittest.main()

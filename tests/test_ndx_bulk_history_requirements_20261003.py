"""Synthetic saved metadata; no raw decoding, real projection or fitting."""
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_bulk_history_requirements_20261003 as m
from backtest import ndx_bulk_history_requirements_research as core

def fixture():
    refs={k:dict(path='/synthetic/'+k,sha256='a'*64) for k in m.BOUND}
    days=[];day=date(2026,9,21)
    while len(days)<520:
        if day.weekday()<5:days.append(day.isoformat())
        day-=timedelta(days=1)
    days.reverse();tickers=['AAPL']+['T'+str(i) for i in range(1,101)]
    rows=[dict(security_id='S'+str(i),issuer_id='I'+str(max(0,i-1)),ticker=t,risk_chain='risk'+str(i%3)) for i,t in enumerate(tickers[:77])]
    gaps=[]
    for i,t in enumerate(tickers):
        gaps.append(dict(ticker=t,included_in_conditional_panel=i<77,coordinate_assumption=dict(security_id='S'+str(i),issuer_id='I'+str(max(0,i-1)),assumed_window=dict(first='2026-03-20',last='2026-09-21')),risk_assumption=dict(risk_chain='risk'+str(i%3))))
    flags=dict.fromkeys(('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted','formal_input_ready'),False)
    fields=list(rows[0]);panel=dict(schema='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1',cutoff='2026-09-21',universe=dict(type='dataframe',index_kind='RangeIndex',index=list(range(77)),columns=fields,dtypes=['object']*len(fields),data=[[r[k] for k in fields] for r in rows]),observed_provenance_and_missing=gaps,**flags)
    pdoc=dict(schema='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1',panel=panel,source_hashes={},**flags,**{k:[{'saved':k}] for k in m.SIDECARS})
    scope=dict.fromkeys(('prices_reconstructed','complete_corporate_actions_verified','legal_training_input_admitted','point_in_time_verified','promotion_allowed','volume_unit_verified'),False)
    channels=[];bridges=[];sources={}
    for t in tickers+['TSM']:
        raw=dict(path='/synthetic/'+t+'.bin',sha256='b'*64);receipt=dict(path='/synthetic/'+t+'.receipt',sha256='c'*64);sources[raw['path']]=raw['sha256'];sources[receipt['path']]=receipt['sha256']
        obs=dict(ticker=t,decoded_sha256='d'*64,raw_provider_meta=dict(symbol=t),raw_returned_events={'dividends':{'preserved':1}},quote_price_unit='UNVERIFIED',volume_unit='UNVERIFIED',rows=[dict(new_york_date=d,missing_fields=[],excluded_receipt_day_or_later=False) for d in days]+[dict(new_york_date='2026-09-22',missing_fields=['close','adjclose'],excluded_receipt_day_or_later=False)])
        channels.append(dict(ticker=t,http_status=200,readback_status='RAW_CHANNEL_READBACK_ONLY',receipt_new_york_day='2026-09-23',receipt_sha256='c'*64,observation=obs))
        if t!='TSM':bridges.append(dict(ticker=t,new_raw_reference=raw,new_receipt_reference=receipt,new_decoded_sha256='d'*64,new_returned_splits={},event_policy_bridge=dict(regular_floor=None,events=[]),original_reason=None))
    return dict(panel=pdoc,panel_publication=dict(panel_reference=refs['panel'],status='PUBLISHED_CONDITIONAL_PANEL_ONLY',source_hashes={}),readback=dict(schema='NEW_CUTOFF_INDEPENDENT_RAW_READBACK_V1',attempted_prefix_count=102,queue_count=104,rows=channels,source_hashes=sources,**scope),bridge=dict(candidate_cutoff='2026-09-21',rows=bridges,source_hashes=sources,**scope)),refs

class Tests(unittest.TestCase):
    def test_projection_complete_fields_and_original_windows(self):
        docs,refs=fixture();before=deepcopy(docs);docs['readback']['rows'][0]['observation']['rows'][10]['missing_fields']=['close'];docs['bridge']['rows'][1]['event_policy_bridge']['regular_floor']='2026-06-30'
        args,evidence=m.project_inputs(docs,refs)
        self.assertEqual(len(args['reference_calendar']['dates']),520);self.assertEqual(args['ticker_observations']['AAPL']['observation_rows'][10]['missing_fields'],['close'])
        self.assertEqual(len(args['ticker_observations']['AAPL']['excluded_after_cutoff_or_receipt_day']),1)
        self.assertEqual(args['ticker_observations']['T1']['event_policy_bridge']['regular_floor'],'2026-06-30')
        self.assertEqual(evidence['complete_panel_sidecars'],{k:before['panel'][k] for k in m.SIDECARS})
        self.assertEqual(len(args['observed_provenance_and_missing']),101)
        result=core.prepare_history_requirements(**args);m.validate_result(result,args)
        self.assertEqual([s['constructed_window_count'] for s in result['scenarios']],[1,13]);self.assertEqual(result['scenarios'][1]['windows'][-1]['start_price_index'],252)

    def test_cross_source_and_scope_rejections(self):
        docs,refs=fixture()
        for mutate in (lambda d:d['bridge']['rows'][0].update(new_decoded_sha256='e'*64),lambda d:d['readback']['rows'][0].update(receipt_sha256='e'*64),lambda d:d['panel']['panel']['observed_provenance_and_missing'][0]['coordinate_assumption']['assumed_window'].update(first='2020-01-01'),lambda d:d['readback']['rows'][0]['observation']['raw_provider_meta'].update(symbol='WRONG'),lambda d:d['panel']['panel']['observed_provenance_and_missing'][0].update(included_in_conditional_panel=False)):
            bad=deepcopy(docs);mutate(bad)
            with self.assertRaises(ValueError):m.project_inputs(bad,refs)

    def test_pending_core_precedes_reads(self):
        with patch.object(m,'CORE_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.load_inputs()
            read.assert_not_called()

    def test_failed_projection_has_started_and_no_retry(self):
        with tempfile.TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)/'out'),patch.object(m,'load_inputs',return_value=({}, {}, {}, None)) as load,patch.object(m,'project_inputs',side_effect=ValueError('projection failure')):
            with self.assertRaises(ValueError):m.run()
            self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','failure.json'})
            with self.assertRaises(ValueError):m.run()
            self.assertEqual(load.call_count,1)

    def test_result_cannot_upgrade_identity_or_drop_security(self):
        docs,refs=fixture();args,_=m.project_inputs(docs,refs);result=core.prepare_history_requirements(**args)
        for mutate in (lambda r:r.update(identity_interval_verified=True),lambda r:r['scenarios'][0]['security_rows'].pop(),lambda r:r['ticker_observations_preserved'].pop('AAPL')):
            bad=deepcopy(result);mutate(bad)
            with self.assertRaises(ValueError):m.validate_result(bad,args)

if __name__=='__main__':unittest.main()

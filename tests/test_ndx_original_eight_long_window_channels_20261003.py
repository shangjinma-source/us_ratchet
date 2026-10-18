"""Synthetic seven-channel reuse plus one mocked TSM reconstruction only."""
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from scripts import ndx_original_eight_long_window_channels_20261003 as m

def weekdays(first,last):
    d=date.fromisoformat(first);end=date.fromisoformat(last);out=[]
    while d<=end:
        if d.weekday()<5:out.append(d.isoformat())
        d+=timedelta(days=1)
    return out

def numeric(ticker,days,rawref,receiptreference):
    quotes=[dict(session=d,nominal_open=str(i+10),nominal_close=str(i+11)) for i,d in enumerate(days)]
    returns=[dict(previous_session=a,session=b,dividends_included=False,value=i/10000) for i,(a,b) in enumerate(zip(days,days[1:]))]
    value=dict(schema='BULK_LONG_WINDOW_CONDITIONAL_CHANNEL_V1',ticker=ticker,status='CONDITIONAL_NUMERIC_RESULT',reasons=[],calendar=days,raw_reference=rawref,receipt_reference=receiptreference,quote_rows=quotes,return_rows=returns,training_returns=returns[:126],evaluation_returns=returns[126:],returned_events={'dividends':{'preserved':17}},**dict.fromkeys(m.CHANNEL_FALSE,False))
    for field in ('quote_rows','training_returns','evaluation_returns'):value[field+'_sha256']=m.sha(m.encoded(value[field]))
    return value

def fixture():
    refs={k:dict(path='/synthetic/'+k,sha256='a'*64) for k in m.BOUND}
    a=weekdays('2025-09-18','2026-03-20');b=weekdays('2026-03-23','2026-09-21');days=a[:126]+[a[-1]]+b[:125]+[b[-1]]
    securities=[dict(ticker=t,security_id='security:incumbent_overlay:TSM' if t=='TSM' else 'S'+t,issuer_id='issuer:0001046179' if t=='TSM' else 'I'+t,risk_chain='R'+t,target_weight=.125) for t in m.TICKERS]
    definition=dict(securities=deepcopy(securities),starting_capital_usd=25000.,transaction_cost_bps=10.,minimum_cash_buffer_usd=100.)
    control=dict(securities=deepcopy(securities),complete_original_definition=definition,complete_original_manifest=dict(definition=deepcopy(definition)),new_execution_contract_frozen=False)
    metadata={};rows=[];audits=[];raw=b'SYNTHETIC TSM RAW';receipt=dict(ticker='TSM',raw_path='/synthetic/TSM.bin',raw_sha256=m.sha(raw),http_status=200);receiptbytes=m.encoded(receipt)
    for s in securities:
        t=s['ticker'];rr=dict(path='/synthetic/'+t+'.bin',sha256=m.sha(raw) if t=='TSM' else 'b'*64);rc=dict(path='/synthetic/'+t+'.receipt',sha256=m.sha(receiptbytes) if t=='TSM' else 'c'*64)
        metadata[t]=dict(security_id=s['security_id'],raw_reference=rr,receipt_reference=rc,decoded_sha256='d'*64,shares_or_prices_converted=False,complete_original_control_security=deepcopy(s),returned_events={'dividends':{'preserved':1}},control_only_overlay=t=='TSM')
        if t=='TSM':
            metadata[t].update(original_receipt=receipt,complete_identity_sidecar=dict(ticker=t,security_id=s['security_id'],issuer_id=s['issuer_id'],cusip='874039100',security_class='American Depositary Shares',ordinary_shares_per_ads=5,**dict.fromkeys(('historical_2023_identity_interval_verified','point_in_time_verified','ndx_membership_verified','price_identity_verified','holdings_conversion_performed','promotion_allowed'),False)))
        else:
            value=numeric(t,days,rr,rc);rows.append(dict(coordinate=deepcopy(s),channel=value,original_identity_assumed_window={'first':'2026-03-20','last':'2026-09-21'}));audits.append({key:deepcopy(value[key]) for key in ('ticker','raw_reference','receipt_reference','quote_rows_sha256','training_returns_sha256','evaluation_returns_sha256')})
    for i in range(70):rows.append(dict(coordinate=dict(ticker='X'+str(i))));audits.append(dict(ticker='X'+str(i)))
    false=dict.fromkeys(('fit_performed','account_simulation_performed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized'),False)
    saved=dict(schema='BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1',source_hashes={},rows=rows,calendar253=days,original_provenance_and_missing=[{'ticker':'P'+str(i)} for i in range(101)],preserved_evidence_sidecars={str(i):[{'unchanged':i}] for i in range(7)},evaluation_interval_previously_used_for_fitting=True,future_independent_oos=False,untouched_holdout=False,evaluation_prior_fit_overlap_evidence={'exact_same_126_dates':True,'evaluation_dates':days[127:]},**false)
    req=dict(schema='LONG_WINDOW_BENCHMARK_REQUIREMENTS_V1',reference_calendar={'dates':days},training_return_end_dates=days[1:127],evaluation_return_end_dates=days[127:],original_control_order=deepcopy(m.TICKERS),original_control_preserved=control,stock_metadata_preserved=metadata,original_target_weight_sum_exact='1',nav_metadata_preserved={'publication_time_known':False},fx_metadata_preserved={'bound':False})
    reqdoc=dict(schema='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_DOCUMENT_V1',source_hashes={},requirements=req,**false)
    audit=dict(schema='BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_V1',status='PASS',channels_sha256=refs['channels']['sha256'],publication_sha256=refs['channels_publication']['sha256'],reader_sha256=refs['channels_audit_reader']['sha256'],per_channel=audits,**false)
    old=dict(schema='INCUMBENT_TSM_FIXED_CUTOFF_CONDITIONAL_NOMINAL_QUOTE_V1',ticker='TSM',all_returned_raw_events={'dividends':{'OLD_NOT_SPLICED':1}},reconstruction=dict(quote_field_basis='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS',basis_was_supplied_not_authenticated=True,provider_split_events=[],rows=[{'never_used':True}]),**dict.fromkeys(('zero_returned_splits_proves_no_actions','complete_actions_verified','quote_basis_independently_authenticated','point_in_time_verified','promotion_allowed'),False))
    docs=dict(channels=saved,requirements=reqdoc,channels_audit=audit,old_tsm_basis=old)
    docs['channels_publication']=dict(schema='BULK_LONG_WINDOW_CHANNELS_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_INDEPENDENT_READBACK',channels_reference=refs['channels'],source_hashes={},**false)
    docs['requirements_publication']=dict(schema='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_PUBLICATION_V1',status='PUBLISHED_REQUIREMENTS_ONLY',requirements_reference=refs['requirements'],source_hashes={},**false)
    return docs,refs,raw,receiptbytes

def fake_core(**kw):
    value=numeric('TSM',kw['calendar253'],kw['raw_reference'],kw['receipt_reference']);value.update(bridge_row_preserved=kw['bridge_row'],window_contract=kw['window_contract'],tzif_sha256=m.sha(kw['tzif_bytes']),decoded_sha256=kw['bridge_row']['new_decoded_sha256']);return value

class Tests(unittest.TestCase):
    def test_original8_order_weight_and_exact7_reuse_only_one_tsm_call(self):
        docs,refs,raw,receipt=fixture();before=deepcopy(docs);prepared=m.prepare(docs,refs);seen=[]
        def call(**kw):seen.append(kw['receipt']['ticker']);return fake_core(**kw)
        out=m.assemble(prepared,raw,receipt,b'TZ',types.SimpleNamespace(reconstruct_long_channel=call),docs,refs)
        self.assertEqual(seen,['TSM']);self.assertEqual(out['sealed_channel_reuse_count'],7);self.assertEqual(out['conditional_numeric_channel_count'],8);self.assertEqual(docs,before)
        for row in out['rows']:
            if row['original_control_security']['ticker']!='TSM':self.assertEqual(row['channel'],row['complete_parent_row']['channel'])
        self.assertEqual(out['original_control_preserved'],docs['requirements']['requirements']['original_control_preserved']);self.assertTrue(out['evaluation_interval_previously_used_for_fitting']);self.assertFalse(out['untouched_holdout']);self.assertFalse(out['holdings_or_quotes_converted'])

    def test_source_audit_overlay_and_split_conflicts_rejected(self):
        docs,refs,_,_=fixture()
        mutations=[lambda d:d['channels_audit'].update(channels_sha256='f'*64),lambda d:d['channels']['rows'][0]['coordinate'].update(issuer_id='OTHER'),lambda d:d['requirements']['requirements']['stock_metadata_preserved']['TSM']['complete_identity_sidecar'].update(holdings_conversion_performed=True),lambda d:d['old_tsm_basis']['reconstruction'].update(provider_split_events=[{'new':1}]),lambda d:d['requirements']['requirements']['stock_metadata_preserved']['TSM']['returned_events'].update(splits={'new':1}),lambda d:d['channels'].update(untouched_holdout=True)]
        for change in mutations:
            bad=deepcopy(docs);change(bad)
            with self.assertRaises(ValueError):m.prepare(bad,refs)

    def test_tsm_consumed_bytes_and_output_flags(self):
        docs,refs,raw,receipt=fixture();prepared=m.prepare(docs,refs)
        with patch.object(types.SimpleNamespace(),'reconstruct_long_channel',create=True) as call:
            with self.assertRaises(ValueError):m.assemble(prepared,raw+b'!',receipt,b'TZ',types.SimpleNamespace(reconstruct_long_channel=call),docs,refs)
            call.assert_not_called()
        def bad(**kw):v=fake_core(**kw);v['benchmark_qualified']=True;return v
        with self.assertRaises(ValueError):m.assemble(prepared,raw,receipt,b'TZ',types.SimpleNamespace(reconstruct_long_channel=bad),docs,refs)

    def test_blocked_tsm_retained_with_seven_reused(self):
        docs,refs,raw,receipt=fixture();prepared=m.prepare(docs,refs)
        def blocked(**kw):
            v=fake_core(**kw);v.update(status='BLOCKED_PRICE_INPUT',reasons=['MISSING_QUOTE_FIELDS'],quote_rows=None,return_rows=None,training_returns=None,evaluation_returns=None);return v
        out=m.assemble(prepared,raw,receipt,b'TZ',types.SimpleNamespace(reconstruct_long_channel=blocked),docs,refs)
        self.assertEqual(out['blocked_price_channel_count'],1);self.assertEqual(out['conditional_numeric_channel_count'],7);self.assertEqual(len(out['rows']),8)

    def test_pending_audit_and_failed_attempt_not_retried(self):
        pending=deepcopy(m.BOUND);pending['channels_audit']=(pending['channels_audit'][0],None)
        with patch.object(m,'BOUND',pending),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.load_inputs()
            read.assert_not_called()
        with tempfile.TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)/'attempt'),patch.object(m,'load_inputs',return_value=({}, {}, {}, {}, b'', b'', b'', None)) as load,patch.object(m,'assemble',side_effect=ValueError('TSM decode failure')):
            with self.assertRaises(ValueError):m.run()
            self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','failure.json'})
            with self.assertRaises(ValueError):m.run()
            self.assertEqual(load.call_count,1)

if __name__=='__main__':unittest.main()

"""Synthetic wrapper requests; actual raw reconstruction is never performed here."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from scripts import ndx_bulk_long_window_channels_20261003 as m
from backtest import ndx_bulk_long_window_channels_research as core

def load_fixture(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
hist=load_fixture('test_ndx_bulk_history_requirements_20261003');bench=load_fixture('test_ndx_bulk_long_window_benchmark_requirements_20261003')

def fixture():
    source,_=hist.fixture();b,_=bench.fixture();days=[r['new_york_date'] for r in b['readback']['rows'][0]['observation']['rows']];panel=source['panel'];fields=panel['panel']['universe']['columns'];universe=[dict(zip(fields,row)) for row in panel['panel']['universe']['data']]
    panel['panel']['returns']={'index':[d+'T00:00:00' for d in days[127:]]}
    refs={k:dict(path='/synthetic/'+k,sha256='a'*64) for k in m.BOUND};observations={};rawinputs={}
    for security in universe:
        t=security['ticker'];i=next(i for i,r in enumerate(source['bridge']['rows']) if r['ticker']==t);br=source['bridge']['rows'][i];raw=m.encoded({'synthetic':t});br['new_raw_reference']['sha256']=m.sha(raw)
        receipt=dict(ticker=t,raw_path=br['new_raw_reference']['path'],raw_sha256=m.sha(raw));blob=m.encoded(receipt);br['new_receipt_reference']['sha256']=m.sha(blob);rawinputs[t]=dict(raw_bytes=raw,receipt_bytes=blob)
        observations[t]=dict(complete_bridge_row=deepcopy(br),bridge_reference=dict(refs['bridge'],json_pointer=f'/rows/{i}'),raw_reference=deepcopy(br['new_raw_reference']),receipt_reference=deepcopy(br['new_receipt_reference']),decoded_sha256=br['new_decoded_sha256'],identity_assumed_window=dict(first='2026-03-20',last='2026-09-21'))
    flags=dict.fromkeys(('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted'),False)
    history=dict(schema='BULK_HISTORY_REQUIREMENTS_DOCUMENT_V1',source_hashes={},requirements=dict(schema='BULK_CONDITIONAL_HISTORY_REQUIREMENTS_V1',scenarios=[dict(price_window_length=253,constructed_window_count=1,security_denominator=77,required_reference_price_dates=days)],universe=universe,observed_provenance_and_missing=deepcopy(panel['panel']['observed_provenance_and_missing']),original_identity_assumed_window=dict(first='2026-03-20',last='2026-09-21'),ticker_observations_preserved=observations),projection_evidence=dict(complete_panel_sidecars={k:deepcopy(panel[k]) for k in m.SIDECARS}),**flags)
    docs=dict(prior_fit_batch=dict(status='BUDGETED_QUEUE_FINISHED',new_readback_count=1630,initial_completed_rows=[{},{}]),history=history,history_publication=dict(schema='BULK_HISTORY_REQUIREMENTS_PUBLICATION_V1',status='PUBLISHED_REQUIREMENTS_ONLY',requirements_reference=refs['history'],source_hashes={}),history_audit=dict(status='PASS',requirements_sha256=refs['history']['sha256'],publication_sha256=refs['history_publication']['sha256'],reader_sha256=refs['history_audit_reader']['sha256']),panel=panel,bridge=source['bridge'])
    return docs,refs,rawinputs

def blocked(**kw):
    return dict(schema=core.SCHEMA,ticker=kw['receipt']['ticker'],status='BLOCKED_PRICE_INPUT',reasons=['SYNTHETIC_BLOCKED'],calendar=deepcopy(kw['calendar253']),raw_reference=kw['raw_reference'],receipt_reference=kw['receipt_reference'],bridge_row_preserved=kw['bridge_row'],window_contract=kw['window_contract'],tzif_sha256=m.sha(kw['tzif_bytes']),decoded_sha256=kw['bridge_row']['new_decoded_sha256'],quote_rows=None,return_rows=None,training_returns=None,evaluation_returns=None,**core.FLAGS)

class Tests(unittest.TestCase):
    def test_exact77_calls_all_provenance_and_blocked_rows_retained(self):
        docs,refs,raws=fixture();requests=m.prepare(docs,refs);seen=[]
        def call(**kwargs):seen.append(kwargs['receipt']['ticker']);return blocked(**kwargs)
        out=m.assemble(requests,raws,b'TZ',types.SimpleNamespace(reconstruct_long_channel=call),docs,refs)
        self.assertEqual(len(seen),len(set(seen)));self.assertEqual(len(seen),77);self.assertEqual(out['blocked_price_channel_count'],77);self.assertEqual(out['conditional_numeric_channel_count'],0)
        self.assertEqual(out['original_provenance_and_missing'],docs['panel']['panel']['observed_provenance_and_missing']);self.assertEqual(out['preserved_evidence_sidecars'],{k:docs['panel'][k] for k in m.SIDECARS});self.assertFalse(out['identity_interval_extended']);self.assertTrue(out['evaluation_interval_previously_used_for_fitting']);self.assertFalse(out['untouched_holdout']);self.assertFalse(out['future_independent_oos'])

    def test_parent_policy_sidecar_coordinate_mutations_fail(self):
        docs,refs,_=fixture()
        for mutation in (lambda d:d['panel']['panel']['returns']['index'].__setitem__(0,'2026-03-24T00:00:00'),lambda d:d['history']['requirements']['universe'][0].update(ticker='OTHER'),lambda d:d['history']['requirements']['ticker_observations_preserved']['AAPL']['complete_bridge_row']['event_policy_bridge'].update(regular_floor='2020-01-01'),lambda d:d['panel']['bulk_incremental_evidence_and_projection'].append({'injected':True}),lambda d:d['history_publication'].update(status='FAILED')):
            bad=deepcopy(docs);mutation(bad)
            with self.assertRaises(ValueError):m.prepare(bad,refs)

    def test_consumed_raw_sha_and_result_permission_are_guarded(self):
        docs,refs,raws=fixture();requests=m.prepare(docs,refs);bad=deepcopy(raws);bad['AAPL']['raw_bytes']+=b' '
        with patch.object(core,'reconstruct_long_channel') as call:
            with self.assertRaises(ValueError):m.assemble(requests,bad,b'TZ',core,docs,refs)
            call.assert_not_called()
        def upgrade(**kwargs):value=blocked(**kwargs);value['promotion_allowed']=True;return value
        with self.assertRaises(ValueError):m.assemble(requests,raws,b'TZ',types.SimpleNamespace(reconstruct_long_channel=upgrade),docs,refs)

    def test_started_precedes_arithmetic_failure_no_retry(self):
        with tempfile.TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)/'attempt'),patch.object(m,'load_inputs',return_value=({}, {}, {}, [], {}, b'', None)) as load,patch.object(m,'assemble',side_effect=ValueError('decode failed')):
            with self.assertRaises(ValueError):m.run()
            self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','failure.json'})
            with self.assertRaises(ValueError):m.run()
            self.assertEqual(load.call_count,1)

    def test_pending_pin_fails_before_source_reads(self):
        with patch.object(m,'CORE_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.load_inputs()
            read.assert_not_called()

if __name__=='__main__':unittest.main()

from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
from scripts import ndx_dated_per_task_continuous_20261003 as core
from backtest import ndx_dated_account_input_research as inputs_core
from backtest import ndx_dated_continuous_weight_diagnostic_research as numeric
from test_ndx_dated_account_input_research import fixture,REF


def fixtures():
    a=fixture()
    for c in list(a['candidate_channels_by_security'].values())+list(a['incumbent_channels_by_security'].values()):
        for row in c['quote_rows']:
            price=Fraction(100)
            for p in c['event_policies']:
                if row['session']>=p['session']:price/=p['numerator']
            row['nominal_open_exact']=row['nominal_close_exact']=str(price)
    inp=inputs_core.assemble_dated_account_inputs(**a);tid=a['task']['numerical_task_id']
    refs={r:dict(path=r+'.json',sha256='a'*64) for r in ('inputs','publication','readback')}
    false=dict(account_executed=False,fit_performed=False,point_in_time_verified=False,promotion_allowed=False)
    docs=dict(inputs=dict(schema='DATED_ACCOUNT_INPUT_DOCUMENT_V1',inputs=inp,source_hashes={},task_reference=dict(path=str(core.PREPARATION),sha256=core.PREPARATION_SHA,json_pointer='/materialized/combinations/0/tasks/0'),original_provenance_and_missing=[{}]*101,preserved_evidence_sidecars={str(i):{} for i in range(7)},**false),publication=dict(schema='DATED_ACCOUNT_INPUT_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED',inputs_reference=refs['inputs'],source_hashes={},**false),readback=dict(schema='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=core.INPUT_READER_SHA,source_hashes={str(core.INPUT_READER):core.INPUT_READER_SHA},inputs_reference=refs['inputs'],publication_reference=refs['publication'],**false))
    control={'tracks':{'incumbent':dict(calendar=inp['calendar'],source_references_preserved={'complete_original_track_preserved':deepcopy(inp['incumbent'])})}}
    return tid,docs,refs,control

class Tests(unittest.TestCase):
    def test_candidate_once_split_accounting_control_never_called(self):
        tid,docs,refs,control=fixtures();spy=Mock(wraps=numeric.diagnose_continuous_weights)
        result=core.assemble(tid,docs,refs,control,SimpleNamespace(diagnose_continuous_weights=spy))
        spy.assert_called_once();self.assertEqual(result['candidate_core_call_count'],1);self.assertEqual(result['control_core_call_count'],0)
        self.assertEqual(result['immutable_control_reference']['json_pointer'],'/tracks/incumbent')
        v=numeric.number(result['candidate']['path'][-1]['normalized_value']);self.assertEqual(v,Fraction(999,1000))
        self.assertEqual(len(result['candidate']['split_events_preserved']),2)
        self.assertNotIn('tracks',result);self.assertFalse(result['integer_execution_or_rejection_inferred'])

    def test_zero_target_retained_without_integer_success_inference(self):
        tid,docs,refs,control=fixtures();inp=docs['inputs']['inputs'];sids=inp['candidate']['original_security_order']
        for sid,w in zip(sids,[0.,1.]):
            inp['candidate']['schedule'][0]['targets'][sid]['target_weight']=w
            inp['original_fit_result']['targets'][sid]['target_weight']=w
        result=core.assemble(tid,docs,refs,control,numeric)
        self.assertEqual([p['target_weight'] for p in result['candidate']['positions_preserved']],[0.,1.])
        self.assertEqual(numeric.number(result['candidate']['path'][-1]['security_rows'][0]['fractional_quantity']),0)
        self.assertFalse(result['integer_account_status_consumed'])

    def test_original_control_change_rejected_before_candidate_call(self):
        tid,docs,refs,control=fixtures();docs['inputs']['inputs']['incumbent']['matrices']['close']['data'][0][0]+=1
        spy=Mock()
        with self.assertRaises(ValueError):core.assemble(tid,docs,refs,control,SimpleNamespace(diagnose_continuous_weights=spy))
        spy.assert_not_called()

    def test_old_first_task_and_existing_namespace_early_block(self):
        with patch.object(core,'load_common') as load:
            with self.assertRaises(ValueError):core.run(core.OLD_TASK,REF,REF,execute=True)
            with self.assertRaises(ValueError):core.run('a'*64,REF,REF,execute=1)
            load.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp,patch.object(core,'OUTPUT',Path(tmp)):
            (Path(tmp)/('a'*64)).mkdir()
            with self.assertRaises(ValueError):core.check_task('a'*64)

    def test_actual_immutable_control_metadata_only(self):
        docs={}
        for role in ('control','control_publication','control_readback'):
            r=core.BOUND[role];blob=Path(r['path']).read_bytes();self.assertEqual(core.sha(blob),r['sha256']);docs[role]=core.loads(blob)
        core.validate_control(docs)
        docs['control']['original_task_preserved']['numerical_task_id']='f'*64
        with self.assertRaises(ValueError):core.validate_control(docs)

    def test_receipt_drift_keeps_failure_and_no_retry(self):
        tid,docs,refs,control=fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'inputs'/tid;folder.mkdir(parents=True)
            inref=core.save(folder/'inputs.json',docs['inputs']);pub=deepcopy(docs['publication']);pub['inputs_reference']=inref
            pubref=core.save(folder/'publication.json',pub);audit=deepcopy(docs['readback']);audit.update(inputs_reference=inref,publication_reference=pubref);aref=core.save(folder/'independent_readback.json',audit);core.save(folder/'started.json',{})
            common=dict(immutable_control_reference=deepcopy(core.BOUND['control']));core._CACHE[id(common)]=(common,{'control':control},{},numeric);out=root/'out';count=[0]
            def guard(s):
                count[0]+=1
                if count[0]==5:raise ValueError('receipt source drift')
            with patch.object(core,'INPUT_ROOT',root/'inputs'),patch.object(core,'OUTPUT',out),patch.object(core,'guard',side_effect=guard):
                with self.assertRaises(ValueError):core.run(tid,inref,aref,execute=True,common=common)
                self.assertTrue((out/tid/'publication.json').exists());self.assertTrue((out/tid/'failure.json').exists())
                with self.assertRaises(ValueError):core.run(tid,inref,aref,execute=True,common=common)
            core._CACHE.pop(id(common))

if __name__=='__main__':unittest.main()

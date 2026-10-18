from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
from scripts import ndx_dated_per_task_continuous_20261003 as core
from test_ndx_dated_per_task_continuous_20261003 import fixtures,numeric


class Tests(unittest.TestCase):
    def test_source_pins_bytes_and_conflicts(self):
        for r in list(core.BOUND.values())+[dict(path=str(p),sha256=h) for p,h in ((core.CORE,core.CORE_SHA),(core.SEMANTICS,core.SEMANTICS_SHA),(core.INPUT_READER,core.INPUT_READER_SHA),(core.PREPARATION,core.PREPARATION_SHA))]:
            self.assertEqual(core.sha(Path(r['path']).read_bytes()),r['sha256'])
        with self.assertRaises(ValueError):core.guard({str(core.CORE):'a'*64})

    def test_control_and_input_changes_stop_before_numeric(self):
        original=fixtures()
        for change in (
            lambda d:d['readback'].__setitem__('publication_reference',dict(path='elsewhere',sha256='b'*64)),
            lambda d:d['inputs']['inputs']['incumbent']['schedule'][0]['targets'][next(iter(d['inputs']['inputs']['incumbent']['schedule'][0]['targets']))].__setitem__('target_weight',.2),
            lambda d:d['inputs']['inputs'].__setitem__('valuation_point_count',True),
            lambda d:d['inputs'].__setitem__('point_in_time_verified',True),
            lambda d:d['inputs']['inputs']['candidate']['split_evidence_preserved'][next(iter(d['inputs']['inputs']['candidate']['split_evidence_preserved']))].clear(),
        ):
            tid,docs,refs,control=deepcopy(original);change(docs);call=Mock()
            with self.assertRaises(ValueError):core.assemble(tid,docs,refs,control,SimpleNamespace(diagnose_continuous_weights=call))
            call.assert_not_called()

    def test_shared_control_reference_and_original_weights(self):
        tid,docs,refs,control=fixtures();inp=docs['inputs']['inputs'];sids=inp['candidate']['original_security_order']
        for sid,w in zip(sids,[0.,1.0000000000000002]):
            inp['candidate']['schedule'][0]['targets'][sid]['target_weight']=w
            inp['original_fit_result']['targets'][sid]['target_weight']=w
        call=Mock(wraps=numeric.diagnose_continuous_weights)
        result=core.assemble(tid,docs,refs,control,SimpleNamespace(diagnose_continuous_weights=call))
        call.assert_called_once();self.assertEqual([p['target_weight'] for p in result['candidate']['positions_preserved']],[0.,1.0000000000000002])
        self.assertEqual(result['immutable_control_reference'],dict(core.BOUND['control'],json_pointer='/tracks/incumbent'))
        self.assertEqual(result['control_core_call_count'],0);self.assertNotIn('incumbent',result)

    def test_unexpected_output_kept_failed_and_cannot_retry(self):
        tid,docs,refs,control=fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'inputs'/tid;folder.mkdir(parents=True)
            ir=core.save(folder/'inputs.json',docs['inputs']);p=deepcopy(docs['publication']);p['inputs_reference']=ir
            pr=core.save(folder/'publication.json',p);a=deepcopy(docs['readback']);a.update(inputs_reference=ir,publication_reference=pr)
            ar=core.save(folder/'independent_readback.json',a);core.save(folder/'started.json',{})
            handle=dict(immutable_control_reference=deepcopy(core.BOUND['control']));output=root/'out'
            def inject(**kwargs):
                (output/tid/'unknown.json').write_text('{}')
                return numeric.diagnose_continuous_weights(**kwargs)
            core._CACHE[id(handle)]=(handle,{'control':control},{},SimpleNamespace(diagnose_continuous_weights=inject))
            try:
                with patch.object(core,'INPUT_ROOT',root/'inputs'),patch.object(core,'OUTPUT',output),patch.object(core,'guard'):
                    with self.assertRaises(ValueError):core.run(tid,ir,ar,execute=True,common=handle)
                    self.assertTrue((output/tid/'failure.json').exists());self.assertTrue((output/tid/'unknown.json').exists())
                    with self.assertRaises(ValueError):core.run(tid,ir,ar,execute=True,common=handle)
            finally:core._CACHE.pop(id(handle))

if __name__=='__main__':unittest.main()

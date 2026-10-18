"""Independent observation V2 readback, temporary physical V5 inputs only."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ndx_registered_observation_independent_readback_20261009_v2 as reader
from scripts import ndx_registered_observation_writer_20261009_v2 as writer
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from ndx_v5_physical_parent_fixture import envelope
import test_ndx_registered_observation_writer_20261009_v2 as fixture


def saved_context(root,late=False):
    context=fixture.physical_context(root);receipt=fixture.run_context(context,late=late)
    payload=reader.decode(Path(receipt['path']).read_bytes())['payload_reference']
    return context,payload,receipt


def read_context(context,payload,receipt):
    research,_,_,current,args=context
    with patch.multiple(reader,RESEARCH=research,CURRENT=current,WRITER_SHA=writer.LOADED_SHA):
        return reader.readback(registration_path=args['registration_path'],registration_sha256=args['registration_sha256'],
            payload_reference=payload,receipt_reference=receipt,execute=True)


class RegisteredObservationReadbackV2Tests(unittest.TestCase):
    def test_every_pending_host_pin_is_rejected_before_source_read(self):
        kwargs=dict(registration_path='E:/synthetic/reg.json',registration_sha256='a'*64,
            payload_reference=dict(path='E:/synthetic/payload.json',sha256='b'*64),receipt_reference=dict(path='E:/synthetic/receipt.json',sha256='c'*64))
        with patch.object(reader,'WRITER_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('Source IO')):
            self.assertEqual(reader.readback(**kwargs),dict(status='NOT_EXECUTED'))
            with self.assertRaises(ValueError):reader.readback(**kwargs,execute=True)
        for group,key in [('WRITER_SHA',None),('REGISTRATION_CORE',None),('REFERENCE_CORE',None),
                *(('DEPENDENCIES',key)for key in reader.DEPENDENCIES),*(('AUXILIARY_DEPENDENCIES',key)for key in reader.AUXILIARY_DEPENDENCIES)]:
            updates=dict(WRITER_SHA='a'*64)
            if key:
                value=deepcopy(getattr(reader,group));value[key]=(value[key][0],None)
            elif group=='WRITER_SHA':value=None
            else:value=(getattr(reader,group)[0],None)
            updates[group]=value
            with self.subTest(group=group,key=key),patch.multiple(reader,**updates),patch.object(Path,'read_bytes',side_effect=AssertionError('Pending host IO')):
                with self.assertRaises(ValueError):reader.readback(**kwargs,execute=True)

    def test_full_physical_v5_timely_and_late_are_independently_reconstructed(self):
        for late in (False,True):
            with self.subTest(late=late),TemporaryDirectory(prefix='SYNTHETIC_ONLY_v5_observer_')as folder:
                context,payload,receipt=saved_context(Path(folder),late)
                original=reader.private_module;forbidden={writer.SOURCE,writer.CORE}
                def no_producer(path,raw,sha,replacements=()):
                    if Path(path)in forbidden or Path(path).name in ('ndx_accounted_source_prefix_research_v1.py','ndx_prospective_gap_history_research_v5.py','ndx_forward_source_capture_scoped_research.py','ndx_forward_source_capture_research.py'):
                        raise AssertionError('Producer compiled')
                    module=original(path,raw,sha,replacements)
                    for name in ('readback','append_observation_history_v4','extend_gap_history','prepare_observation_payload'):
                        if hasattr(module,name):setattr(module,name,lambda **kwargs:(_ for _ in()).throw(AssertionError('Producer entry called')))
                    return module
                for path in context[3].values():path.write_bytes(b'cache changed after capture')
                readbytes=Path.read_bytes
                def no_live(path):
                    if path in context[3].values():raise AssertionError('Live source read')
                    return readbytes(path)
                with patch.object(reader,'private_module',side_effect=no_producer),patch.object(Path,'read_bytes',no_live),patch.dict('sys.modules',{
                        'backtest.ndx_prospective_observation_receipt_research':SimpleNamespace(),
                        'backtest.ndx_prospective_history_parent_view_research_v5':SimpleNamespace()}):
                    report=read_context(context,payload,receipt)
                audit=reader.decode(Path(report['path']).read_bytes());parent=view.inspect_parent_history_v5(envelope(context[1]))
                self.assertEqual(audit['schema'],'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3')
                self.assertEqual(audit['status'],'PASS');self.assertEqual(audit['writer_adapter_schema'],reader.ADAPTER)
                self.assertEqual(audit['actual_parent_schema'],'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5')
                self.assertEqual(audit['counts']['parent_typed_row_count'],72)
                self.assertEqual(audit['counts']['parent_actual_observation_count'],2)
                self.assertEqual(audit['counts']['parent_gap_count'],10)
                self.assertFalse(audit['counts']['month_first_actual_observation'])
                self.assertEqual(audit['counts']['timing_classification'],'LATE_OBSERVATION'if late else'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')
                self.assertEqual(parent['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
                for role in ('writer_called','payload_core_called','producer_prefix_core_called','gap_core_called'):
                    self.assertIs(audit[role],False)
                for path,sha in audit['source_hashes'].items():self.assertEqual(reader.sha(Path(path).read_bytes()),sha)
                self.assertEqual({p.name for p in Path(report['path']).parent.iterdir()},{'started.json','observation_payload.json','receipt.json','independent_readback.json'})
                with self.assertRaises(ValueError):read_context(context,payload,receipt)

    def test_coordinated_payload_receipt_nested_extra_is_rejected_and_preserved(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_v5_observer_forged_')as folder:
            context,payload_ref,receipt_ref=saved_context(Path(folder))
            payload=reader.decode(Path(payload_ref['path']).read_bytes())
            payload['full_original_sources_preserved']['QQQ']['extra_authority']=True
            Path(payload_ref['path']).write_bytes(reader.enc(payload));payload_ref=dict(path=payload_ref['path'],sha256=reader.sha(Path(payload_ref['path']).read_bytes()))
            receipt=reader.decode(Path(receipt_ref['path']).read_bytes());receipt['payload_reference']=payload_ref
            Path(receipt_ref['path']).write_bytes(reader.enc(receipt));receipt_ref=dict(path=receipt_ref['path'],sha256=reader.sha(Path(receipt_ref['path']).read_bytes()))
            with self.assertRaises(ValueError):read_context(context,payload_ref,receipt_ref)
            output=Path(payload_ref['path']).parent
            self.assertEqual(reader.decode((output/'failure.json').read_bytes())['status'],'INDEPENDENT_READBACK_FAILED_NO_RETRY')
            self.assertFalse((output/'independent_readback.json').exists())
            with self.assertRaises(ValueError):read_context(context,payload_ref,receipt_ref)

    def test_ancestor_started_drift_after_payload_inspection_is_rejected(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_v5_observer_drift_')as folder:
            context,payload_ref,receipt_ref=saved_context(Path(folder));original=reader.inspect
            parent=envelope(context[1]);ancestor=Path(parent['document']['history']['parent_references']['reference']['path']).parent/'started.json'
            def drift(*args,**kwargs):
                result=original(*args,**kwargs);ancestor.write_bytes(b'ancestor START drift');return result
            with patch.object(reader,'inspect',side_effect=drift):
                with self.assertRaises(ValueError):read_context(context,payload_ref,receipt_ref)
            output=Path(payload_ref['path']).parent
            self.assertTrue((output/'failure.json').exists());self.assertFalse((output/'independent_readback.json').exists())


if __name__=='__main__':unittest.main()

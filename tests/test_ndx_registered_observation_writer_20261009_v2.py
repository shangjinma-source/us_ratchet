"""Temporary physical V5 observations; no actual registration or output."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_observation_writer_20261009_v2 as writer
from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as capture
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as capture_reader
from scripts import ndx_registered_gap_history_independent_readback_20261009_v1 as gap_reader
from backtest import ndx_observation_runtime_registration_research_v1 as registration
from backtest import ndx_prospective_history_parent_view_research_v5 as parent_view
from ndx_v5_physical_parent_fixture import reference,envelope
import test_ndx_registered_gap_history_independent_readback_20261009_v1 as gap_fixture
import test_ndx_registered_forward_capture_runtime_20261009_v2_independent_review as capture_fixture


def physical_context(root,multi=False):
    context,gap=gap_fixture.published_context(root,'mixed')
    audit=gap_fixture.read_context(context,gap,'gap_parent_audit')
    research=context[0]
    parent=dict(reference=gap['history_reference'],publication_reference=gap['publication_reference'],
        readback_reference=audit,reader_reference=reference(gap_reader.SOURCE))
    current=capture_fixture.current_files(root,parent,'observation_v5')
    if multi:
        for path in current.values():
            with path.open('ab')as stream:stream.write(b'2026-10-14,100,110,90,100,1000\n')
    capargs,_=capture_fixture.registered(root,research,parent,'observation_v5_capture')
    day='2026-10-14'if multi else '2026-10-13'
    with patch.multiple(capture,RESEARCH=research,CURRENT=current),patch.object(capture,'now',side_effect=[day+'T20:05:00+00:00',day+'T20:05:01+00:00']):
        saved=capture.run(**capargs)
    with patch.multiple(capture_reader,RESEARCH=research,CURRENT=current):
        read=capture_reader.readback(registration_path=capargs['registration_path'],registration_sha256=capargs['registration_sha256'],
            **saved,output_directory=str(research/'observation_v5_capture_audit'),execute=True)
    captures=dict(reference=saved['capture_reference'],publication_reference=saved['publication_reference'],readback_reference=read,reader_reference=reference(capture_reader.SOURCE))
    value=dict(schema=registration.SCHEMA,runtime_reference=reference(writer.SOURCE),
        dependency_references={key:dict(path=str(path),sha256=sha)for key,(path,sha)in writer.DEPENDENCIES.items()},
        parent=parent,capture=captures,output_directory=str(research/'observation_v5_attempt'),**registration.FLAGS)
    path=root/'observation_registration.json';path.write_bytes(writer.encode(value))
    return research,parent,captures,current,dict(registration_path=str(path),registration_sha256=reference(path)['sha256'],execute=True)


def run_context(context,late=False):
    research,_,_,current,args=context
    times=['2026-10-14T14:00:00+00:00']*8 if late else ['2026-10-13T20:06:00+00:00','2026-10-13T20:06:01+00:00']+['2026-10-13T20:06:02+00:00']*8
    with patch.multiple(writer,RESEARCH=research,CURRENT=current),patch.object(writer,'now',side_effect=times):
        return writer.run(**args)


class RegisteredV5ObservationWriterTests(unittest.TestCase):
    def test_default_and_every_host_pin_are_pre_io(self):
        args=dict(registration_path='E:/synthetic/registration.json',registration_sha256='a'*64)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Source IO')):
            self.assertEqual(writer.run(**args),dict(status='NOT_EXECUTED'))
        for group,key in [('REGISTRATION_CORE',None),('REFERENCE_CORE',None),('CORE_SHA',None),
                *(('DEPENDENCIES',key)for key in writer.DEPENDENCIES),*(('AUXILIARY_DEPENDENCIES',key)for key in writer.AUXILIARY_DEPENDENCIES)]:
            if key:
                value=deepcopy(getattr(writer,group));value[key]=(value[key][0],None)
            elif group=='CORE_SHA':value=None
            else:value=(getattr(writer,group)[0],None)
            with self.subTest(group=group,key=key),patch.object(writer,group,value),patch.object(Path,'read_bytes',side_effect=AssertionError('Pending host IO')):
                with self.assertRaises(ValueError):writer.run(**args,execute=True)

    def test_registration_v1_is_structurally_version_agnostic_and_detached(self):
        parent={key:dict(path='E:/synthetic/parent/'+key+'.json',sha256=str(index)*64)for index,key in enumerate(writer.ROLES,1)}
        capture_refs={key:dict(path='E:/synthetic/capture/'+key+'.json',sha256=str(index)*64)for index,key in enumerate(writer.ROLES,5)}
        runtime=dict(path=str(writer.SOURCE),sha256=writer.LOADED_SHA)
        deps={key:dict(path=str(path),sha256=sha)for key,(path,sha)in writer.DEPENDENCIES.items()}
        value=dict(schema=registration.SCHEMA,runtime_reference=runtime,dependency_references=deps,parent=parent,capture=capture_refs,
            output_directory='E:/synthetic/research/observation_v5',**registration.FLAGS)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')):
            result=registration.prepare_observation_runtime(registration=value,registration_reference=dict(path='E:/synthetic/reg.json',sha256='a'*64),
                runtime_reference=runtime,dependency_references=deps,research_root='E:/synthetic/research')
        self.assertEqual(result['parent'],parent);self.assertFalse(result['parent_capture_schema_verified'])
        result['parent']['reference']['sha256']='f'*64;self.assertNotEqual(result['parent'],value['parent'])

    def test_real_pending13_becomes_single_actual13_without_truncation(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_v5_observation_')as folder:
            context=physical_context(Path(folder));before=parent_view.inspect_parent_history_v5(envelope(context[1]))
            self.assertEqual(before['last_accounted_session'],'2026-10-12')
            self.assertEqual([item['session']for item in before['pending_source_sessions']],['2026-10-13'])
            for path in context[3].values():path.write_bytes(b'cache changed after capture')
            original=Path.read_bytes
            def immutable_only(path):
                if path in context[3].values():raise AssertionError('Live cache read')
                return original(path)
            with patch.object(Path,'read_bytes',immutable_only):result=run_context(context)
            receipt=writer.decode(Path(result['path']).read_bytes());payload=writer.decode(Path(receipt['payload_reference']['path']).read_bytes())
            self.assertEqual(payload['schema'],'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1')
            self.assertEqual(payload['writer_adapter_schema'],writer.ADAPTER)
            self.assertEqual(payload['actual_parent_schema'],'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5')
            self.assertEqual((payload['session'],payload['sequence']),('2026-10-13',73))
            self.assertEqual(payload['known_typed_rows_preserved'],before['known_typed_rows'])
            self.assertEqual(payload['parent_attempt_inventory_preserved'],before['parent_attempt_inventory'])
            self.assertFalse(payload['month_first_actual_observation']);self.assertEqual(payload['first_actual_observed_session_of_month'],'2026-10-02')
            self.assertEqual(receipt['timing_classification'],'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')
            capture_doc=writer.decode(Path(context[2]['reference']['path']).read_bytes())
            for ticker in ('QQQ','SPY'):
                part=payload['full_original_sources_preserved'][ticker]['sources']
                self.assertEqual(part['reference'],capture_doc['captured_artifacts'][ticker])
                self.assertEqual(part['rows'][-1]['Date'],'2026-10-13')
                self.assertEqual(payload['full_original_sources_preserved'][ticker]['baseline_sources']['reference'],before['accounted_baseline_references'][ticker])
            self.assertEqual(set(Path(result['path']).parent.iterdir()),{Path(result['path']).parent/name for name in ('started.json','observation_payload.json','receipt.json')})
            for key in writer.FLAGS:self.assertIs(payload[key],False)
            with self.assertRaises(ValueError):run_context(context)

    def test_multi_unaccounted_preserves_pending_dates_and_is_blocked(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_v5_multi_')as folder:
            context=physical_context(Path(folder),multi=True)
            c=writer.decode(Path(context[2]['reference']['path']).read_bytes())
            self.assertEqual(c['plan']['source_evidence']['QQQ']['new_session_dates'],['2026-10-13','2026-10-14'])
            self.assertIn('MULTIPLE_UNACCOUNTED_SESSIONS',[item['reason']for item in c['plan']['diagnostics']])
            with self.assertRaises(ValueError):run_context(context)
            self.assertFalse((context[0]/'observation_v5_attempt').exists())

    def test_late_remains_actual_and_own_started_drift_preserves_failure(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_v5_late_')as folder:
            context=physical_context(Path(folder));original=writer.save
            def drift(path,value):
                result=original(path,value)
                if path.name=='receipt.json':(path.parent/'started.json').write_bytes(b'changed own started')
                return result
            with patch.object(writer,'save',side_effect=drift):
                with self.assertRaises(ValueError):run_context(context,late=True)
            output=context[0]/'observation_v5_attempt'
            receipt=writer.decode((output/'receipt.json').read_bytes())
            self.assertEqual(receipt['timing_classification'],'LATE_OBSERVATION')
            self.assertFalse(receipt['month_first_actual_observation'])
            self.assertEqual(writer.decode((output/'failure.json').read_bytes())['status'],'FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY')
            with self.assertRaises(ValueError):run_context(context)


if __name__=='__main__':unittest.main()

"""Disposable registered gap/readback chains; no actual registration or output."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ndx_registered_gap_history_independent_readback_20261009_v1 as reader
from scripts import ndx_registered_gap_history_runtime_20261009_v1 as publisher
from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as capture
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as capture_reader
from backtest import ndx_gap_runtime_registration_research_v1 as registration
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from ndx_v5_physical_parent_fixture import reference,envelope
import test_ndx_registered_gap_history_runtime_20261009_v1_independent_review as gap_physical
import test_ndx_registered_forward_capture_runtime_20261009_v2_independent_review as cap_physical
import test_ndx_registered_forward_capture_runtime_20261009_v1_independent_review as old_physical


def published_context(root,mode='mixed'):
    if mode=='mixed':
        context=gap_physical.physical_context(root);result=gap_physical.run_context(context)
        return context,result
    research=root/'research';research.mkdir();parent=old_physical.compact_parent(root,research)
    current=cap_physical.current_files(root,parent,'timely_gap')
    for path in current.values():
        with path.open('ab')as stream:stream.write(b'2026-10-09,100,110,90,100,1000\n')
    args,_=cap_physical.registered(root,research,parent,'timely_capture')
    with patch.multiple(capture,RESEARCH=research,CURRENT=current),patch.object(capture,'now',side_effect=[
            '2026-10-09T20:03:00+00:00','2026-10-09T20:03:01+00:00']):captured=capture.run(**args)
    with patch.multiple(capture_reader,RESEARCH=research,CURRENT=current):
        audit=capture_reader.readback(registration_path=args['registration_path'],registration_sha256=args['registration_sha256'],
            **captured,output_directory=str(research/'timely_capture_audit'),execute=True)
    captures=dict(reference=captured['capture_reference'],publication_reference=captured['publication_reference'],
        readback_reference=audit,reader_reference=reference(capture_reader.SOURCE))
    deps=deepcopy(reader.DEPENDENCIES)
    value=dict(schema=registration.SCHEMA,runtime_reference=reference(publisher.SOURCE),
        dependency_references={role:reader.reference(str(reader.ROOT/path),sha)for role,(path,sha)in deps.items()},
        parent=parent,capture=captures,output_directory=str(research/'timely_gap'),**registration.FLAGS)
    path=root/'gap_registration.json';path.write_bytes(reader.encode(value));args=dict(registration_path=str(path),registration_sha256=reference(path)['sha256'],execute=True)
    context=(research,parent,captures,current,deps,args)
    with patch.multiple(publisher,RESEARCH=research,CURRENT=current):result=publisher.run(**args)
    return context,result


def read_context(context,result,name='gap_readback'):
    research,_,_,current,_,args=context
    with patch.multiple(reader,RESEARCH=research,CURRENT=current,PRODUCER_SHA=publisher.LOADED_SHA):
        return reader.readback(registration_path=args['registration_path'],registration_sha256=args['registration_sha256'],
            **result,output_directory=str(research/name),execute=True)


class RegisteredGapReadbackTests(unittest.TestCase):
    def test_pending_and_all_host_anchors_fail_before_io(self):
        kwargs=dict(registration_path='E:/synthetic/registration.json',registration_sha256='a'*64,
            history_reference=dict(path='E:/synthetic/history.json',sha256='b'*64),
            publication_reference=dict(path='E:/synthetic/publication.json',sha256='c'*64),output_directory='E:/synthetic/research/audit')
        with patch.object(reader,'PRODUCER_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            self.assertEqual(reader.readback(**kwargs),dict(status='NOT_EXECUTED'))
            with self.assertRaises(ValueError):reader.readback(**kwargs,execute=True)
        for role in ('PRODUCER_SHA','REGISTRATION_CORE','REFERENCE_CORE','CSV_READER','INDEPENDENT_GAP','INDEPENDENT_PREFIX',*reader.DEPENDENCIES):
            updates=dict(PRODUCER_SHA='a'*64)
            if role=='PRODUCER_SHA':updates[role]=None
            elif role in reader.DEPENDENCIES:
                deps=deepcopy(reader.DEPENDENCIES);deps[role]=(deps[role][0],None);updates['DEPENDENCIES']=deps
            else:updates[role]=(getattr(reader,role)[0],None)
            with self.subTest(role=role),patch.multiple(reader,**updates),patch.object(Path,'read_bytes',side_effect=AssertionError('Premature source IO')):
                with self.assertRaises(ValueError):reader.readback(**kwargs,execute=True)

    def test_private_closure_never_compiles_producer_gap_prefix_scoped_or_base(self):
        raw={role:(reader.ROOT/path).read_bytes()for role,(path,_)in reader.DEPENDENCIES.items()}
        independents=dict(gap=reader.INDEPENDENT_GAP[0].read_bytes(),prefix=reader.INDEPENDENT_PREFIX[0].read_bytes())
        forbidden={reader.PRODUCER,*(reader.ROOT/reader.DEPENDENCIES[role][0]for role in ('gap_core','prefix_core','scoped','base'))}
        original=reader.private_module
        def guarded(path,raw,sha,replacements=()):
            if Path(path)in forbidden:raise AssertionError('Producer formula executed')
            result=original(path,raw,sha,replacements)
            for name in ('append_observation_history_v4','extend_gap_history','readback'):
                if hasattr(result,name):setattr(result,name,lambda **kwargs:(_ for _ in()).throw(AssertionError('Forbidden entry')))
            return result
        with patch.object(reader,'private_module',side_effect=guarded),patch.dict('sys.modules',{
                'backtest.ndx_prospective_gap_history_research_v5':SimpleNamespace(),
                'backtest.ndx_accounted_source_prefix_research_v1':SimpleNamespace()}):
            modules=reader.private_checkers(raw,independents,reader.CSV_READER[0].read_bytes())
        self.assertTrue(callable(modules['gap'].reconstruct_gap_history));self.assertTrue(callable(modules['prefix'].reconstruct_accounted_prefix))

    def test_full_physical_mixed_and_no_expired_parent_view_and_complete_source_map(self):
        for mode in ('mixed','timely'):
            with self.subTest(mode=mode),TemporaryDirectory(prefix='SYNTHETIC_ONLY_gap_readback_')as folder:
                context,result=published_context(Path(folder),mode)
                for live in context[3].values():live.write_bytes(b'changed after capture')
                original=Path.read_bytes
                def deny_live(path):
                    if path in context[3].values():raise AssertionError('Live cache read')
                    return original(path)
                with patch.object(Path,'read_bytes',deny_live):report=read_context(context,result)
                audit=reader.decode(Path(report['path']).read_bytes())
                self.assertEqual(audit['schema'],'PROSPECTIVE_GAP_HISTORY_INDEPENDENT_READBACK_V5')
                self.assertTrue(audit['entire_history_independently_reconstructed']);self.assertFalse(audit['new_pure_called'])
                self.assertFalse(audit['producer_prefix_core_called']);self.assertFalse(audit['producer_scoped_parser_called'])
                parent=dict(reference=result['history_reference'],publication_reference=result['publication_reference'],readback_reference=report,reader_reference=reference(reader.SOURCE))
                normalized=view.inspect_parent_history_v5(envelope(parent))
                expected_pending='2026-10-13'if mode=='mixed'else'2026-10-09'
                self.assertEqual([item['session']for item in normalized['pending_source_sessions']],[expected_pending])
                self.assertEqual(normalized['observation_count'],2)
                for path,sha in audit['source_hashes'].items():self.assertEqual(reader.digest(Path(path).read_bytes()),sha)
                self.assertEqual({path.name for path in Path(report['path']).parent.iterdir()},{'started.json','independent_readback.json'})
                with self.assertRaisesRegex(ValueError,'create-only'):read_context(context,result)

    def test_own_started_drift_after_report_preserves_failure_and_blocks_retry(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_gap_readback_drift_')as folder:
            context,result=published_context(Path(folder));output=context[0]/'failed_audit';original=reader.save
            def drift(path,value):
                result=original(path,value)
                if path.name=='independent_readback.json':(path.parent/'started.json').write_bytes(b'{}')
                return result
            with patch.object(reader,'save',side_effect=drift),self.assertRaises(ValueError):read_context(context,result,'failed_audit')
            self.assertTrue((output/'failure.json').exists());self.assertTrue((output/'independent_readback.json').exists())
            with self.assertRaisesRegex(ValueError,'create-only'):read_context(context,result,'failed_audit')

    def test_createonly_save_resource_and_strict_json(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_gap_readback_unit_')as folder:
            path=Path(folder)/'started.json';reader.save(path,dict(synthetic=True))
            with self.assertRaises(FileExistsError):reader.save(path,{})
            with patch.object(reader.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(ValueError,'RESOURCE_STOP'):reader.save(Path(folder)/'report.json',{})
                reader.save(Path(folder)/'failure.json',dict(status='FAILED_DO_NOT_CONSUME'))
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}'):
            with self.assertRaises(ValueError):reader.decode(raw)


if __name__=='__main__':unittest.main()

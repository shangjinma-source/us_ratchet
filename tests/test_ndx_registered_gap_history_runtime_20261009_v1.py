"""Pending gap runtime and private closure tests; no actual registration/output."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ndx_registered_gap_history_runtime_20261009_v1 as module
from backtest import ndx_prospective_gap_history_research_v5 as kernel
from test_ndx_prospective_gap_history_research_v5 import arguments


class RegisteredGapRuntimeTests(unittest.TestCase):
    def test_pending_checker_and_execution_gate_precede_all_io(self):
        dependencies=deepcopy(module.DEPENDENCIES)
        dependencies['capture_checker']=(dependencies['capture_checker'][0],None)
        with patch.object(module,'DEPENDENCIES',dependencies):
            for execute in (False,True):
                with patch.object(Path,'read_bytes',side_effect=AssertionError('Premature IO')),self.assertRaises(ValueError):
                    module.run(registration_path='E:/synthetic/registration.json',registration_sha256='a'*64,execute=execute)
            self.assertIsNone(module.DEPENDENCIES['capture_checker'][1])

    def test_private_eight_module_closure_ignores_cached_imports_and_checks_hosts(self):
        raw={role:(module.ROOT/path).read_bytes()for role,(path,_)in module.DEPENDENCIES.items()}
        # Only synthetic in-memory source compilation; no publisher/readback is run.
        raw['capture_checker']=raw['capture_checker'].replace(b'PRODUCER_SHA=None',b"PRODUCER_SHA='"+b'a'*64+b"'")
        deps=deepcopy(module.DEPENDENCIES);deps['capture_checker']=(deps['capture_checker'][0],module.digest(raw['capture_checker']))
        hostile=SimpleNamespace()
        with patch.object(module,'DEPENDENCIES',deps),patch.dict('sys.modules',{
                'backtest.ndx_prospective_history_parent_view_research_v5':hostile,
                'backtest.ndx_prospective_gap_history_research_v5':hostile,
                'backtest.ndx_accounted_source_prefix_research_v1':hostile}):
            private=module.private_dependencies(raw)
            self.assertIsNot(private['parent_view'],hostile)
            self.assertIs(private['gap_core'].parent_view,private['parent_view'])
            self.assertIs(private['gap_core'].prefix_core,private['prefix_core'])
            self.assertIs(private['prefix_core'].scoped_parser,private['scoped'])
            self.assertEqual(private['gap_core'].extend_gap_history(**arguments()),kernel.extend_gap_history(**arguments()))
            broken=deepcopy(raw);broken['gap_core']+=b'\n'
            with self.assertRaisesRegex(ValueError,'Private source SHA'):module.private_dependencies(broken)

    def test_mutable_sources_rejected_before_read_and_failed_namespace_rejected(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_gap_io_')as folder:
            source=Path(folder)/'current.csv';source.write_bytes(b'original');ref=module.reference(str(source),module.digest(b'original'))
            with patch.object(module,'CURRENT',{'QQQ':source,'SPY':source}),patch.object(Path,'read_bytes',side_effect=AssertionError('Live read')):
                with self.assertRaisesRegex(ValueError,'Mutable cache'):module.consume(ref,{})
            (Path(folder)/'failure.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'Failed source'):module.consume(ref,{})

    def test_create_only_resource_stop_and_failure_bytes_preserved(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_gap_save_')as folder:
            path=Path(folder)/'started.json';module.save(path,{'synthetic':True});before=path.read_bytes()
            with self.assertRaises(FileExistsError):module.save(path,{})
            with patch.object(module.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(ValueError,'RESOURCE_STOP'):module.save(Path(folder)/'history.json',{})
                module.save(Path(folder)/'failure.json',dict(status='FAILED_DO_NOT_CONSUME'))
            self.assertEqual(path.read_bytes(),before);self.assertFalse((Path(folder)/'history.json').exists())

    def test_duplicate_nonfinite_and_reference_authority_reject(self):
        for value in (b'{"a":1,"a":2}',b'{"a":NaN}'):
            with self.assertRaises(ValueError):module.decode(value)
        for ref in (dict(path='E:/x',sha256=None),dict(path='E:/x',sha256='a'*64,source_authenticity_verified=True)):
            with self.assertRaises(ValueError):module.merge({},ref)


class RegisteredGapPhysicalRuntimeTests(unittest.TestCase):
    def test_complete_physical_v3_and_v5_mixed_pending_gaps_without_live_read(self):
        from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as capture
        from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as capture_reader
        from scripts import ndx_prospective_observation_writer_v3_20261009 as oldwriter
        from backtest import ndx_gap_runtime_registration_research_v1 as registration
        from backtest import ndx_forward_capture_runtime_registration_research_v2 as capture_registration
        from backtest import ndx_prospective_history_parent_view_research_v5 as view
        from ndx_v5_physical_parent_fixture import physical_gap_parent,envelope
        import test_ndx_registered_forward_capture_runtime_20261009_v1_independent_review as oldphysical
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_registered_gap_physical_')as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            parents=[('v3',deepcopy(oldwriter.PARENT_BOUND))]
            timely_root=root/'timely_parent';timely_root.mkdir();timely_research=timely_root/'research';timely_research.mkdir()
            timely=oldphysical.compact_parent(timely_root,timely_research);parents.append(('v4_timely',timely))
            v5,_=physical_gap_parent(root,research,'prior_gap');parents.append(('v5',v5))
            for version,parent in parents:
                if version=='v3':
                    current=oldphysical.current_files(root,parent,'2026-10-08')
                    clocks=['2026-10-12T20:03:00+00:00','2026-10-12T20:03:01+00:00']
                elif version=='v4_timely':
                    current=oldphysical.current_files(timely_root,parent,'2026-10-09')
                    clocks=['2026-10-09T20:03:00+00:00','2026-10-09T20:03:01+00:00']
                else:
                    h=envelope(parent)['document']['history'];current={}
                    for ticker in ('QQQ','SPY'):
                        current[ticker]=root/(ticker+'_current_gap.csv')
                        current[ticker].write_bytes(Path(h['full_capture_source_references'][ticker]['path']).read_bytes())
                    clocks=['2026-10-13T20:03:00+00:00','2026-10-13T20:03:01+00:00']
                capture_deps=deepcopy(capture_reader.DEPENDENCIES)
                capvalue=dict(schema=capture_registration.SCHEMA,runtime_reference=module.reference(str(capture.SOURCE),capture.LOADED_SHA),
                    dependency_references={key:module.reference(str(module.ROOT/path),sha)for key,(path,sha)in capture_deps.items()},
                    parent=parent,output_directory=str(research/('current_capture_'+version)),**capture_registration.FLAGS)
                cappath=root/('capture_registration_'+version+'.json');cappath.write_bytes(module.encode(capvalue))
                with patch.multiple(capture,RESEARCH=research,CURRENT=current,DEPENDENCIES=capture_deps,REGISTRATION_CORE=capture_reader.REGISTRATION_CORE),patch.object(capture,'now',side_effect=clocks):
                    captured=capture.run(registration_path=str(cappath),registration_sha256=module.digest(cappath.read_bytes()),execute=True)
                with patch.multiple(capture_reader,RESEARCH=research,CURRENT=current,PRODUCER_SHA=capture.LOADED_SHA):
                    audit=capture_reader.readback(registration_path=str(cappath),registration_sha256=module.digest(cappath.read_bytes()),
                        **captured,output_directory=str(research/('current_capture_audit_'+version)),execute=True)
                capture_refs=dict(reference=captured['capture_reference'],publication_reference=captured['publication_reference'],
                    readback_reference=audit,reader_reference=module.reference(str(capture_reader.SOURCE),capture_reader.LOADED_SHA))
                deps=deepcopy(module.DEPENDENCIES);deps['capture_checker']=(deps['capture_checker'][0],capture_reader.LOADED_SHA)
                gapvalue=dict(schema=registration.SCHEMA,runtime_reference=module.reference(str(module.SOURCE),module.LOADED_SHA),
                    dependency_references={key:module.reference(str(module.ROOT/path),sha)for key,(path,sha)in deps.items()},
                    parent=parent,capture=capture_refs,output_directory=str(research/('new_gap_'+version)),**registration.FLAGS)
                gappath=root/('gap_registration_'+version+'.json');gappath.write_bytes(module.encode(gapvalue))
                private=module.private_module
                def synthetic_compile(path,raw,sha,replacements=()):
                    if Path(path)==capture_reader.SOURCE and b'PRODUCER_SHA=None'in raw:
                        self.assertEqual(raw.count(b'PRODUCER_SHA=None'),1)
                        # Explicit synthetic future pin binding in compiled bytes only;
                        # formal source/None stays untouched, all artifacts are disposable.
                        raw=raw.replace(b'PRODUCER_SHA=None',("PRODUCER_SHA='"+capture.LOADED_SHA+"'").encode())
                        sha=module.digest(raw)
                    return private(path,raw,sha,replacements)
                for live in current.values():live.write_bytes(b'changed after immutable capture')
                original=Path.read_bytes
                def deny_current(path):
                    if path in current.values():raise AssertionError('Current cache read by gap runtime')
                    return original(path)
                with patch.multiple(module,RESEARCH=research,CURRENT=current,DEPENDENCIES=deps),patch.object(module,'private_module',side_effect=synthetic_compile),patch.object(Path,'read_bytes',deny_current):
                    result=module.run(registration_path=str(gappath),registration_sha256=module.digest(gappath.read_bytes()),execute=True)
                    with self.assertRaisesRegex(ValueError,'Create-only'):module.run(registration_path=str(gappath),registration_sha256=module.digest(gappath.read_bytes()),execute=True)
                doc=module.decode(Path(result['history_reference']['path']).read_bytes());h=doc['history']
                previous=view.inspect_parent_history_v5(envelope(parent))
                self.assertEqual(h['known_typed_rows'][:previous['typed_row_count']],previous['known_typed_rows'])
                self.assertEqual(h['observation_count'],previous['observation_count']);self.assertEqual(h['new_missed_observation_count'],0 if version=='v4_timely'else 1)
                self.assertEqual(h['first_actual_observed_session_by_month'],previous['first_actual_observed_session_by_month'])
                self.assertEqual(h['baseline_references'],previous['baseline_references'])
                self.assertEqual({file.name for file in Path(result['history_reference']['path']).parent.iterdir()},
                    {'started.json','history.json','publication.json','QQQ.accounted_prefix.csv','SPY.accounted_prefix.csv','QQQ.prefix_evidence.json','SPY.prefix_evidence.json'})
                if version=='v5':self.assertEqual([item['session']for item in h['pending_source_sessions']],['2026-10-13'])
                if version=='v4_timely':
                    self.assertEqual(h['status'],'NO_EXPIRED_SESSION_TO_APPEND')
                    self.assertEqual(h['known_typed_rows'],previous['known_typed_rows'])
                    self.assertEqual([item['session']for item in h['pending_source_sessions']],['2026-10-09'])
                for path,sha in doc['source_hashes'].items():self.assertEqual(module.digest(Path(path).read_bytes()),sha)


if __name__=='__main__':unittest.main()

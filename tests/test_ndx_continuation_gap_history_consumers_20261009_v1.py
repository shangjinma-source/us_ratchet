"""Author boundaries for new gap consumers. No formal host family or actual IO."""
import ast
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ndx_continuation_gap_history_runtime_20261009_v1 as publisher
from scripts import ndx_continuation_gap_history_independent_readback_20261009_v1 as reader

HOST=dict(registration_path='E:/synthetic/day.json',registration_sha256='a'*64,
    implementation_pair_binding_path='E:/synthetic/B.json',implementation_pair_binding_sha256='b'*64,
    consumer_role_registry_path='E:/synthetic/C.json',consumer_role_registry_sha256='c'*64)

def physical_gap_consumers(root):
    """Bind both real gap roles when C is first created; never mutate C later."""
    import test_ndx_compact_reader_v2_optional_consumer_author_20261009 as factory
    original=factory.host_files
    def closed_host(root,actual_consumers=None,publisher_reference=None):
        actual=dict(actual_consumers or{})
        actual.update(gap_publisher=publisher.reference(str(publisher.SOURCE),publisher.LOADED_SHA),gap_independent_reader=reader.reference(str(reader.SOURCE),reader.LOADED_SHA))
        return original(root,actual,publisher_reference)
    with patch.object(factory,'host_files',side_effect=closed_host):
        research,parent,context,args,capture=factory.physical_continuation_capture(root)
    shared=(factory.reader.SOURCE,factory.reader.LOADED_SHA)
    def private_patch(module):
        original=module.compile_private
        def bound(path,raw,digest,replacements=()):
            loaded=original(path,raw,digest,replacements)
            if Path(path)==shared[0]:loaded.__dict__.update(factory.pins());loaded.RESEARCH=research;loaded.CURRENT=context['current']
            return loaded
        return bound
    return research,parent,context,args,capture,shared,private_patch


def publish_gap(context,parent,capture,name):
    from backtest import ndx_gap_runtime_registration_research_v1 as registration
    research,_,original,args,_,shared,private_patch=context
    value=dict(schema=registration.SCHEMA,runtime_reference=publisher.reference(str(publisher.SOURCE),publisher.LOADED_SHA),dependency_references=publisher.configured(publisher.DEPENDENCIES),parent=parent,capture=capture,output_directory=str(research/name),**registration.FLAGS)
    path=research.parent/(name+'_registration.json');path.write_bytes(publisher.encode(value))
    regargs=dict(registration_path=str(path),registration_sha256=publisher.digest(path.read_bytes()))
    with patch.multiple(publisher,RESEARCH=research,CURRENT=original['current'],SHARED_ANCESTRY_VERIFIER=shared),patch.object(publisher,'compile_private',side_effect=private_patch(publisher)):
        saved=publisher.run(**regargs,**args)
    with patch.multiple(reader,RESEARCH=research,CURRENT=original['current'],SHARED_ANCESTRY_VERIFIER=shared),patch.object(reader,'compile_private',side_effect=private_patch(reader)):
        audit=reader.readback(**regargs,**args,**saved,output_directory=str(research/(name+'_reader')))
    return dict(reference=saved['history_reference'],publication_reference=saved['publication_reference'],readback_reference=audit,reader_reference=reader.reference(str(reader.SOURCE),reader.LOADED_SHA))


class GapConsumerBoundaries(unittest.TestCase):
    def test_pending_shared_verifier_and_all_algorithm_pins_precede_io(self):
        for module in (publisher,reader):
            args=deepcopy(HOST)
            if module is reader:args.update(history_reference=dict(path='E:/synthetic/gap/history.json',sha256='d'*64),publication_reference=dict(path='E:/synthetic/gap/publication.json',sha256='e'*64),output_directory='E:/synthetic/research/audit')
            entry=module.run if module is publisher else module.readback
            with patch.object(Path,'read_bytes',side_effect=AssertionError('Pending source read')):
                self.assertEqual(entry(**args),dict(status='NOT_EXECUTED'))
                with self.assertRaises(ValueError):entry(**args,execute=True)
                shared=(module.SHARED_ANCESTRY_VERIFIER[0],'f'*64)
                for role in module.DEPENDENCIES:
                    deps=deepcopy(module.DEPENDENCIES);deps[role]=(deps[role][0],None)
                    with self.subTest(module=module.CONSUMER_ROLE,role=role),patch.multiple(module,SHARED_ANCESTRY_VERIFIER=shared,DEPENDENCIES=deps):
                        with self.assertRaises(ValueError):entry(**args,execute=True)
                if module is reader:
                    for role in ('INDEPENDENT_GAP','INDEPENDENT_PREFIX','CSV_READER'):
                        with self.subTest(role=role),patch.object(module,'SHARED_ANCESTRY_VERIFIER',shared),patch.object(module,role,(getattr(module,role)[0],None)):
                            with self.assertRaises(ValueError):entry(**args,execute=True)
    def test_business_dependency_values_are_unchanged_and_independent_source_has_no_producer_import(self):
        from scripts import ndx_registered_gap_history_runtime_20261009_v1 as old
        self.assertEqual(publisher.DEPENDENCIES,old.DEPENDENCIES);self.assertEqual(reader.DEPENDENCIES,old.DEPENDENCIES)
        self.assertEqual(publisher.REGISTRATION_CORE,old.REGISTRATION_CORE)
        self.assertEqual(reader.REGISTRATION_CORE,old.REGISTRATION_CORE)
        tree=ast.parse(reader.SOURCE.read_bytes())
        imported=[node.module for node in ast.walk(tree)if isinstance(node,ast.ImportFrom)]
        self.assertFalse(any(value and value.startswith(('scripts','backtest'))for value in imported))
        calls={node.func.attr for node in ast.walk(tree)if isinstance(node,ast.Call)and isinstance(node.func,ast.Attribute)}
        self.assertNotIn('extend_gap_history',calls);self.assertNotIn('derive_accounted_prefix',calls)
        self.assertIn('reconstruct_gap_history',calls);self.assertIn('reconstruct_accounted_prefix',calls)
    def test_private_producer_closure_is_pinned_and_ignores_sysmodules(self):
        from backtest import ndx_prospective_gap_history_research_v5 as frozen
        from test_ndx_prospective_gap_history_research_v5 import arguments
        raw={role:(publisher.ROOT/path).read_bytes()for role,(path,_)in publisher.DEPENDENCIES.items()}
        with patch.dict('sys.modules',{'backtest.ndx_prospective_gap_history_research_v5':SimpleNamespace(),'backtest.ndx_accounted_source_prefix_research_v1':SimpleNamespace()}):
            modules=publisher.private_core(raw)
            self.assertIs(modules['gap_core'].prefix_core,modules['prefix_core'])
            self.assertEqual(modules['gap_core'].extend_gap_history(**arguments()),frozen.extend_gap_history(**arguments()))
            raw['gap_core']+=b'\n'
            with self.assertRaises(ValueError):publisher.private_core(raw)
    def test_mutable_source_failed_namespace_and_path_alias_reject_before_read(self):
        for module in (publisher,reader):
            with TemporaryDirectory()as directory:
                path=Path(directory)/'current.csv';path.write_bytes(b'source');ref=module.reference(str(path),module.digest(b'source'))
                with patch.object(module,'CURRENT',dict(QQQ=path,SPY=path)),patch.object(Path,'read_bytes',side_effect=AssertionError('Mutable read')):
                    with self.assertRaises(ValueError):module.consume(ref,{})
                (path.parent/'failure.json').write_bytes(b'{}')
                with self.assertRaises(ValueError):module.consume(ref,{})
                for bad in ('E:/x/../a','E:/x/NUL.csv','E:/x/a.','//host/share/x'):
                    with self.subTest(path=bad),self.assertRaises(ValueError):module.reference(bad,'a'*64)
    def test_resource_create_only_and_json_strictness(self):
        for module in (publisher,reader):
            for raw in (b'{"a":1,"a":2}',b'{"a":NaN}'):
                with self.assertRaises(ValueError):module.decode(raw)
            with TemporaryDirectory()as directory:
                folder=Path(directory);ref=module.save(folder/'started.json',dict(schema='SYNTHETIC_ONLY'))
                with self.assertRaises(FileExistsError):module.save(folder/'started.json',{})
                with patch.object(module.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
                    with self.assertRaises(ValueError):module.save(folder/'history.json',{})
                    module.save(folder/'failure.json',dict(status='FAILED_DO_NOT_CONSUME'))
                self.assertEqual((folder/'started.json').read_bytes(),module.encode(dict(schema='SYNTHETIC_ONLY')))
                self.assertFalse((folder/'history.json').exists())

class GapConsumerPhysicalTests(unittest.TestCase):
    def test_real_shared_ancestry_mixed_gap_then_no_expired_same_host_family(self):
        from scripts import ndx_continuation_forward_capture_runtime_20261009_v1 as capture
        from scripts import ndx_continuation_forward_capture_independent_readback_20261009_v1 as capture_reader
        from backtest import ndx_forward_capture_runtime_registration_research_v2 as registration
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_true_C_gap_')as directory:
            context=physical_gap_consumers(Path(directory))
            research,parent,original,args,first_capture,shared,private_patch=context
            first=publish_gap(context,parent,first_capture,'continuation_gap_mixed')
            firstdoc=reader.decode(Path(first['reference']['path']).read_bytes());h=firstdoc['history']
            self.assertEqual((h['typed_row_count'],h['observation_count'],h['gap_count']),(72,2,10))
            self.assertEqual([row['session']for row in h['pending_source_sessions']],['2026-10-13'])
            self.assertEqual(h['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
            value=dict(schema=registration.SCHEMA,runtime_reference=capture.reference(str(capture.SOURCE),capture.LOADED_SHA),dependency_references=capture.configured(capture.DEPENDENCIES),parent=first,output_directory=str(research/'continuation_capture_after_gap'),**registration.FLAGS)
            path=Path(directory)/'continuation_capture_after_gap_registration.json';path.write_bytes(capture.encode(value))
            regargs=dict(registration_path=str(path),registration_sha256=capture.digest(path.read_bytes()))
            with patch.multiple(capture,RESEARCH=research,CURRENT=original['current'],SHARED_ANCESTRY_VERIFIER=shared),patch.object(capture,'compile_private',side_effect=private_patch(capture)),patch.object(capture,'now',side_effect=['2026-10-13T20:05:00+00:00','2026-10-13T20:05:01+00:00']):
                saved=capture.run(**regargs,**args)
            with patch.multiple(capture_reader,RESEARCH=research,CURRENT=original['current'],SHARED_ANCESTRY_VERIFIER=shared),patch.object(capture_reader,'compile_private',side_effect=private_patch(capture_reader)):
                audit=capture_reader.readback(**regargs,**args,**saved,output_directory=str(research/'continuation_capture_after_gap_reader'))
            second_capture=dict(reference=saved['capture_reference'],publication_reference=saved['publication_reference'],readback_reference=audit,reader_reference=reader.reference(str(capture_reader.SOURCE),capture_reader.LOADED_SHA))
            second=publish_gap(context,first,second_capture,'continuation_gap_no_expired')
            result=reader.decode(Path(second['reference']['path']).read_bytes())['history']
            self.assertEqual(result['status'],'NO_EXPIRED_SESSION_TO_APPEND')
            self.assertEqual(result['known_typed_rows'],h['known_typed_rows']);self.assertEqual(result['observations'],h['observations']);self.assertEqual(result['parent_attempt_inventory'],h['parent_attempt_inventory'])
            self.assertEqual([row['session']for row in result['pending_source_sessions']],['2026-10-13'])
            for refs in (first,second):
                report=reader.decode(Path(refs['readback_reference']['path']).read_bytes())
                self.assertIs(report['publisher_called'],False);self.assertIs(report['producer_prefix_core_called'],False)
                for name,digest in report['source_hashes'].items():self.assertEqual(reader.digest(Path(name).read_bytes()),digest)


if __name__=='__main__':unittest.main()

"""Temporary host C tests; synthetic peer roles are not producer acceptance."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import inspect

from scripts import ndx_registered_compact_history_independent_readback_20261009_v2 as reader
from backtest import ndx_compact_implementation_pair_binding_research_v1 as binder
from backtest import ndx_continuation_consumer_role_registry_research_v1 as registry


def pins():
    return {name:(getattr(reader,name)[0],digest)for name,digest in dict(
        PAIR_BINDING_CORE='dde8b681612d2b4fc0993bb9b697dcefb0222036d3e1bb6f4aa5f2dd76d7e4ad',
        ANCESTRY_CONTRACT='081ba024fa997c37c1f030fcec7d4d22ca6411eec652d15a5049b57d62a31a76',
        CONSUMER_ROLE_CORE='184479c5e0e6412265e00cc875af1f7902e4f500dc984ca2aaaf3251bc8c433b',
        CONSUMER_METADATA_CORE='b0d16b1b364d2c32e55d826c1f9d63dfffeb27df7bcabfe972efd029e8e2fdeb').items()}


def host_files(root,actual_consumers=None,publisher_reference=None):
    def saved(name,value):
        path=root/name;path.write_bytes(reader.encode(value));return reader.reference(path,reader.sha(path.read_bytes()))
    def identity(name):
        path=root/(name+'.py');path.write_bytes(('# Explicit unexecuted test identity '+name+'.\n').encode());return reader.reference(path,reader.sha(path.read_bytes()))
    pair=saved('SYNTHETIC_ONLY_B.json',dict(schema=binder.SCHEMA,family=binder.FAMILY,protocol=binder.PROTOCOL,role=binder.ROLE,
        publisher_reference=publisher_reference or identity('publisher'),independent_reader_reference=reader.reference(reader.SOURCE,reader.LOADED_SHA),
        contract_reference=reader.reference(*pins()['ANCESTRY_CONTRACT']),publisher_dependency_references=reader.publisher_dependencies(),
        reader_dependency_references={key:reader.reference(*value)for key,value in reader.READER_ALGORITHMS.items()},
        approved_legacy_binding_references=[],**binder.FLAGS))
    consumers={role:identity(role)for role in registry.CONSUMER_ROLES}
    consumers.update(actual_consumers or{})
    consumer=saved('SYNTHETIC_ONLY_C.json',dict(schema=registry.SCHEMA,family=registry.FAMILY,protocol=registry.PROTOCOL,role=registry.ROLE,
        implementation_pair_binding_reference=pair,ancestry_contract_reference=reader.reference(*pins()['ANCESTRY_CONTRACT']),consumer_references=consumers,**registry.FLAGS))
    return dict(implementation_pair_binding_path=pair['path'],implementation_pair_binding_sha256=pair['sha256'],
        consumer_role_registry_path=consumer['path'],consumer_role_registry_sha256=consumer['sha256'],execute=True),consumers


def physical_continuation_capture(root,*,publisher_reference=None,new_session=False):
    """Real locked capture pair; temporary in-memory R2 binding and four C stubs."""
    from ndx_registered_v5_parent_fixture_v2 import physical_registered_gap_parent
    from scripts import ndx_continuation_forward_capture_runtime_20261009_v1 as capture
    from scripts import ndx_continuation_forward_capture_independent_readback_20261009_v1 as capture_reader
    from backtest import ndx_forward_capture_runtime_registration_research_v2 as registration
    root=Path(root).resolve();research=root/'research';parent,context=physical_registered_gap_parent(root,research)
    capture_day='2026-10-13'
    if new_session:
        from ndx_registered_v5_observation_fixture_v2 import _capture,_gap
        captured,_=_capture(root,research,parent,context['current'],'registered_candidate_gap_capture',
            '2026-10-13T20:03:00+00:00','2026-10-13T20:03:01+00:00')
        parent,_=_gap(root,research,parent,context['current'],captured,'registered_candidate_gap_parent')
    actual={role:reader.reference(module.SOURCE,module.LOADED_SHA)for role,module in
        (('capture_publisher',capture),('capture_independent_reader',capture_reader))}
    args,_=host_files(root,actual,publisher_reference)
    value=dict(schema=registration.SCHEMA,runtime_reference=actual['capture_publisher'],dependency_references=capture.configured(capture.DEPENDENCIES),
        parent=parent,output_directory=str(research/'continuation_capture'),**registration.FLAGS)
    regpath=root/'capture_registration.json';regpath.write_bytes(reader.encode(value))
    regargs=dict(registration_path=str(regpath),registration_sha256=reader.sha(regpath.read_bytes()))
    shared=(reader.SOURCE,reader.LOADED_SHA)
    def private_patch(module):
        original=module.compile_private
        def compile_bound(path,raw,digest,replacements=()):
            loaded=original(path,raw,digest,replacements)
            if Path(path)==reader.SOURCE:
                loaded.__dict__.update(pins());loaded.RESEARCH=research;loaded.CURRENT=context['current']
            return loaded
        return compile_bound
    original_require=capture.require
    def diagnostic_require(condition,message):
        if not condition and message=='Plan claims do not select source IO':
            local=inspect.currentframe().f_back.f_locals
            missing={path:digest for path,digest in local['plan']['source_reference_claims'].items()if local['sources'].get(path)!=digest}
            raise ValueError(message+'; missing='+repr(missing))
        return original_require(condition,message)
    with patch.multiple(capture,RESEARCH=research,CURRENT=context['current'],SHARED_ANCESTRY_VERIFIER=shared), \
            patch.object(capture,'compile_private',private_patch(capture)), \
            patch.object(capture,'require',diagnostic_require), \
            patch.object(capture,'now',side_effect=[capture_day+'T20:04:00+00:00',capture_day+'T20:04:01+00:00']):
        saved=capture.run(**regargs,**args)
    with patch.multiple(capture_reader,RESEARCH=research,CURRENT=context['current'],SHARED_ANCESTRY_VERIFIER=shared), \
            patch.object(capture_reader,'compile_private',private_patch(capture_reader)):
        report=capture_reader.readback(**regargs,**args,**saved,output_directory=str(research/'continuation_capture_reader'))
    refs=dict(reference=saved['capture_reference'],publication_reference=saved['publication_reference'],readback_reference=report,reader_reference=actual['capture_independent_reader'])
    return research,parent,context,args,refs


class OptionalConsumerReaderAuthorTests(unittest.TestCase):
    def test_reader_only_partial_and_consumer_failure_are_semantic_attempts(self):
        for name,value in (('reader_started.json',dict(schema='PROSPECTIVE_OBSERVATION_CONTINUATION_READER_STARTED_V1')),
                ('failure.json',dict(consumer_role='observation_writer',status='FAILED_DO_NOT_CONSUME'))):
            with self.subTest(name=name),TemporaryDirectory(prefix='SYNTHETIC_ONLY_reader_partial_')as directory:
                research=Path(directory);folder=research/'partial';folder.mkdir();(folder/name).write_bytes(reader.encode(value))
                with self.assertRaises(ValueError):reader.current_attempt_inventory(dict(document=dict(history=dict(observations=[]))),None,{},[],research_root=research)

    def test_true_continuation_capture_producer_reader_and_independent_outer(self):
        from ndx_registered_v5_parent_fixture_v2 import physical_registered_gap_parent
        from scripts import ndx_continuation_forward_capture_runtime_20261009_v1 as capture
        from scripts import ndx_continuation_forward_capture_independent_readback_20261009_v1 as capture_reader
        from backtest import ndx_forward_capture_runtime_registration_research_v2 as registration
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_R2_C_true_capture_')as directory:
            research,parent,context,args,refs=physical_continuation_capture(Path(directory))
            with patch.multiple(reader,RESEARCH=research,CURRENT=context['current'],**pins()):
                host=reader.load_host_family(**{key:value for key,value in args.items()if key!='execute'})
                modules=host['modules'];sources=host['sources'];original=reader.parent_documents(parent,sources)
                reader.preflight_original_graph(original,None,modules,sources)
                inventories,_=reader.walk_parent_graph(original,modules,sources,host['auxiliary'])
                rebuilt=reader.capture_inventory(refs,modules['checker'],sources,inventories,modules)
                self.assertEqual(rebuilt,reader.decode(Path(refs['reference']['path']).read_bytes())['plan'])
                reader.guard(sources)
                replay=reader.verify_saved_parent_ancestry(parent_references=parent,consumer_capture_references=refs,**args)
                self.assertEqual(replay['capture_envelope']['reference'],refs['reference'])
                self.assertEqual(replay['capture_plan'],rebuilt)
                self.assertIsNone(replay['writer_input_sources']);replay['final_guard']()

    def test_pending_and_partial_consumer_anchors_pre_io(self):
        args=dict(implementation_pair_binding_path='E:/synthetic/B.json',implementation_pair_binding_sha256='a'*64,
            consumer_role_registry_path='E:/synthetic/C.json',consumer_role_registry_sha256='b'*64)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No pending source IO')):
            self.assertEqual(reader.inspect_host_continuation_family(**args),dict(status='NOT_EXECUTED'))
            with self.assertRaises(ValueError):reader.inspect_host_continuation_family(**args,execute=True)
            with self.assertRaises(ValueError):reader.load_host_family(**dict(args,consumer_role_registry_sha256=None))
            with self.assertRaises(ValueError):reader.verify_saved_parent_ancestry(parent_references={},
                consumer_writer_registration_reference={'path':'E:/synthetic/writer.json','sha256':'c'*64},**args,execute=True)

    def test_real_kernels_host_only_detached_private_inputs_and_guard(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_R2_C_host_')as directory:
            root=Path(directory);args,consumers=host_files(root)
            with patch.multiple(reader,**pins()):
                host=reader.load_host_family(**{key:value for key,value in args.items()if key!='execute'})
                family=reader.inspect_host_continuation_family(**args)
                self.assertEqual(family['consumer_registry_view']['consumer_references'],consumers)
                modules=host['modules']
                for role in ('capture_independent_reader','observation_independent_reader','gap_independent_reader'):
                    value=reader.reader_private_inputs(role,modules)
                    self.assertEqual(len(value),13);self.assertEqual(value['runtime'],consumers[role])
                    helper={'capture_independent_reader':modules['checker'],'observation_independent_reader':modules['observer'],'gap_independent_reader':modules['legacy_gap_reader']}[role]
                    self.assertEqual(value['dependencies'],{key:reader.reference(reader.ROOT/path,digest)for key,(path,digest)in helper.DEPENDENCIES.items()})
                original=deepcopy(family['bound_pair']);family['bound_pair'].clear()
                self.assertEqual(modules['bound_pair'],original)
                family['final_guard']()
                Path(consumers['gap_publisher']['path']).write_bytes(b'# drift\n')
                with self.assertRaises(ValueError):family['final_guard']()

    def test_complete_legacy_ancestry_with_host_c_and_no_producer_execution(self):
        from ndx_registered_v5_parent_fixture_v2 import physical_registered_gap_parent
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_R2_C_legacy_')as directory:
            root=Path(directory);research=root/'research';parent,context=physical_registered_gap_parent(root,research)
            args,_=host_files(root)
            before={str(path):reader.sha(path.read_bytes())for path in research.rglob('*')if path.is_file()}
            with patch.multiple(reader,RESEARCH=research,CURRENT=context['current'],**pins()):
                result=reader.verify_saved_parent_ancestry(parent_references=parent,**args)
            self.assertEqual(result['status'],'READ_ONLY_WHOLE_ANCESTRY_RECONSTRUCTION_PASS')
            self.assertEqual(result['parent_references'],parent);self.assertIsNotNone(result['consumer_registry_view'])
            self.assertGreater(result['parent_node_count'],1);result['final_guard']()
            self.assertEqual(before,{str(path):reader.sha(path.read_bytes())for path in research.rglob('*')if path.is_file()})


if __name__=='__main__':unittest.main()

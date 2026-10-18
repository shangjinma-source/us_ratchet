"""Temporary host-pair/consumer integration; never a formal B/C or actual run."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_compact_history_runtime_20261009_v3 as runtime
from backtest import ndx_continuation_consumer_role_registry_research_v1 as consumer_core
from backtest import ndx_continuation_consumer_metadata_research_v1 as metadata_core
import test_ndx_registered_compact_history_runtime_20261009_v3 as legacy_tests

PINS=dict(PAIR_BINDING_CORE=(runtime.PAIR_BINDING_CORE[0],'dde8b681612d2b4fc0993bb9b697dcefb0222036d3e1bb6f4aa5f2dd76d7e4ad'),
    ANCESTRY_CONTRACT=(runtime.ANCESTRY_CONTRACT[0],'081ba024fa997c37c1f030fcec7d4d22ca6411eec652d15a5049b57d62a31a76'),
    CONSUMER_REGISTRY_CORE=(runtime.CONSUMER_REGISTRY_CORE[0],'184479c5e0e6412265e00cc875af1f7902e4f500dc984ca2aaaf3251bc8c433b'),
    CONSUMER_METADATA_CONTRACT=(runtime.CONSUMER_METADATA_CONTRACT[0],'b0d16b1b364d2c32e55d826c1f9d63dfffeb27df7bcabfe972efd029e8e2fdeb'))


def context(root,with_consumers=False):
    with patch.object(legacy_tests,'CONTRACT_SHA',PINS['ANCESTRY_CONTRACT'][1]):
        value=legacy_tests.physical_context(root)
    if with_consumers:
        research,parent,observation,current,args,pair=value
        consumers={}
        for role in consumer_core.CONSUMER_ROLES:
            source=root/('SYNTHETIC_ONLY_'+role+'.py');source.write_bytes(('# Synthetic identity '+role+'; no consumer execution claimed.\n').encode())
            consumers[role]=runtime.reference(source,runtime.sha(source.read_bytes()))
        registry=dict(schema=consumer_core.SCHEMA,family=consumer_core.FAMILY,protocol=consumer_core.PROTOCOL,role=consumer_core.ROLE,
            implementation_pair_binding_reference=runtime.reference(args['implementation_pair_binding_path'],args['implementation_pair_binding_sha256']),
            ancestry_contract_reference=pair['contract_reference'],consumer_references=consumers,**consumer_core.FLAGS)
        cpath=root/'SYNTHETIC_ONLY_consumer_registry.json';cpath.write_bytes(runtime.encode(registry))
        args.update(consumer_role_registry_path=str(cpath),consumer_role_registry_sha256=runtime.sha(cpath.read_bytes()))
    return value


def run_context(value):
    with patch.multiple(runtime,RESEARCH=value[0],CURRENT=value[3],**PINS):return runtime.run(**value[4])


class OptionalConsumerTests(unittest.TestCase):
    def test_real_continuation_capture_whole_metadata_and_sources(self):
        from test_ndx_compact_reader_v2_optional_consumer_author_20261009 import physical_continuation_capture,pins,reader
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_P_true_capture_')as directory:
            research,parent,context,args,refs=physical_continuation_capture(Path(directory),publisher_reference=runtime.reference(runtime.SOURCE,runtime.LOADED_SHA))
            with patch.multiple(reader,RESEARCH=research,CURRENT=context['current'],**pins()),patch.multiple(runtime,RESEARCH=research,CURRENT=context['current'],**PINS):
                host=reader.load_host_family(**{key:value for key,value in args.items()if key!='execute'})
                sources=host['sources'];dependencies={key:runtime.reference(*value)for key,value in runtime.DEPENDENCIES.items()};auxiliary={key:runtime.reference(*value)for key,value in runtime.AUXILIARIES.items()}
                modules=runtime.load_modules(dependencies,auxiliary,sources)
                modules.update(bound_pair=host['pair'],ancestry=host['modules']['ancestry'],host_legacy=runtime.host_legacy_implementations(),consumer_registry_view=host['modules']['consumer_registry'],metadata_core=host['modules']['consumer_metadata'],consumer_core=host['modules']['consumer_registry_kernel'])
                modules['ancestry_arguments']=runtime.ancestry_arguments(modules)
                item=runtime.reference(*runtime.READER_ALGORITHMS['independent_gap_reconstructor'])
                modules['independent_gap']=runtime.private(item['path'],runtime.consume(item,sources),item['sha256'])
                original=runtime.parent_documents(parent,sources)
                entry=original['document']['history']['observations'][-1]
                observed=runtime.observation_documents({role:entry[role]for role in runtime.OBSERVATION_ROLES},sources)
                runtime.preflight_original_graph(original,observed,modules,sources)
                inventories,_=runtime.walk_parent_graph(original,modules,sources,auxiliary)
                saved=runtime.capture_inventory(refs,modules['checker'],sources,inventories,modules)
                self.assertEqual(saved['document']['plan'],runtime.decode(Path(refs['reference']['path']).read_bytes())['plan'])
                for folder,names in inventories:runtime.namespace(Path(folder),names,{})
                runtime.guard(sources)

    def test_pending_and_incomplete_host_c_are_before_io(self):
        args=dict(registration_path='E:/synthetic/reg.json',registration_sha256='a'*64,
            implementation_pair_binding_path='E:/synthetic/B.json',implementation_pair_binding_sha256='b'*64)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pending anchor source IO')):
            self.assertEqual(runtime.run(**args),dict(status='NOT_EXECUTED'))
            for key,value in PINS.items():
                values=deepcopy(PINS);values[key]=(value[0],None)
                with self.subTest(key=key),patch.multiple(runtime,**values):
                    with self.assertRaises(ValueError):runtime.run(**args,execute=True)
            with patch.multiple(runtime,**PINS):
                with self.assertRaises(ValueError):runtime.run(**args,consumer_role_registry_path='E:/synthetic/C.json',execute=True)

    def test_optional_c_legacy_bootstrap_keeps_genuine_v4(self):
        with TemporaryDirectory()as directory:
            value=context(Path(directory),True);published=run_context(value)
            document=runtime.decode(Path(published['history_reference']['path']).read_bytes())
            h=document['history'];self.assertEqual(h['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4')
            self.assertEqual((h['typed_row_count'],h['observation_count'],h['gap_count']),(73,3,10))
            self.assertEqual(h['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
            self.assertNotIn('consumer_role',document);self.assertNotIn('shared_ancestry_verifier_reference',document)
            self.assertEqual(document['consumer_role_registry_reference']['sha256'],value[4]['consumer_role_registry_sha256'])
            for key in ('source_authenticity_verified','clock_authenticity_verified','future_independent_oos','observation_created'):
                self.assertIs(document[key],False)
            sources=document['source_hashes']
            for path in value[0].rglob('*started.json'):
                self.assertEqual(sources.get(str(path)),runtime.sha(path.read_bytes()))
            with self.assertRaises(ValueError):run_context(value)

    def test_no_c_legacy_bootstrap_with_new_k2(self):
        with TemporaryDirectory()as directory:
            value=context(Path(directory));published=run_context(value)
            document=runtime.decode(Path(published['history_reference']['path']).read_bytes())
            self.assertNotIn('consumer_role_registry_reference',document)
            self.assertEqual(document['history']['typed_row_count'],73)

    def test_business_payload_diagnostics_are_not_capture_diagnostics(self):
        raw=b'Date,Open,High,Low,Close,Volume\n2026-07-01,4,3,2,4,1\n2026-07-02,2,4,1,3,1\n'
        rows,diagnostics=runtime.observation_csv_rows(raw,'2026-07-02')
        self.assertEqual(diagnostics,[dict(original_data_row_index=0,session='2026-07-01',issue='OUTSIDE_REQUIRED_SCOPE_OHLC_INCONSISTENCY',raw_row=rows[0])])

    def test_unknown_consumer_registry_rejects_before_peer_and_registration(self):
        from backtest import ndx_compact_implementation_pair_binding_research_v1 as binder
        with TemporaryDirectory()as directory,patch.multiple(runtime,**PINS):
            root=Path(directory);peer=root/'UNREAD_PEER.py';peer.write_bytes(b'# peer identity only\n')
            peerref=runtime.reference(peer,runtime.sha(peer.read_bytes()))
            pair=dict(schema=binder.SCHEMA,family=binder.FAMILY,protocol=binder.PROTOCOL,role=binder.ROLE,
                publisher_reference=runtime.reference(runtime.SOURCE,runtime.LOADED_SHA),independent_reader_reference=peerref,
                contract_reference=runtime.reference(*PINS['ANCESTRY_CONTRACT']),publisher_dependency_references=runtime.publisher_dependencies(),
                reader_dependency_references={key:runtime.reference(*item)for key,item in runtime.READER_ALGORITHMS.items()},approved_legacy_binding_references=[],**binder.FLAGS)
            bp=root/'B.json';bp.write_bytes(runtime.encode(pair));bref=runtime.reference(bp,runtime.sha(bp.read_bytes()))
            registry=dict(schema=consumer_core.SCHEMA,family=consumer_core.FAMILY,protocol=consumer_core.PROTOCOL,role=consumer_core.ROLE,
                implementation_pair_binding_reference=bref,ancestry_contract_reference=pair['contract_reference'],
                consumer_references={role:peerref for role in consumer_core.CONSUMER_ROLES},**consumer_core.FLAGS)
            cp=root/'C.json';cp.write_bytes(runtime.encode(registry));registration=root/'UNREAD_REGISTRATION.json'
            original=runtime.consume;reads=[]
            def consume(item,sources):
                reads.append(item['path'])
                if Path(item['path'])in (peer,registration):raise AssertionError('Unknown C read peer/daily input')
                return original(item,sources)
            with patch.object(runtime,'consume',side_effect=consume):
                with self.assertRaises(ValueError):runtime.run(registration_path=str(registration),registration_sha256='a'*64,
                    implementation_pair_binding_path=str(bp),implementation_pair_binding_sha256=bref['sha256'],
                    consumer_role_registry_path=str(cp),consumer_role_registry_sha256=runtime.sha(cp.read_bytes()),execute=True)
            self.assertNotIn(str(peer),reads);self.assertNotIn(str(registration),reads)

    def test_private_inputs_exact_thirteen_and_fixed_business_maps(self):
        from test_ndx_continuation_consumer_metadata_research_v1 import host_context
        from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as checker
        from scripts import ndx_registered_observation_independent_readback_20261009_v2 as observer
        host=host_context();modules=dict(bound_pair=host['bound_pair'],consumer_registry_view=host['consumer_registry_view'],metadata_core=metadata_core,checker=checker,observer=observer)
        keys={'runtime','dependencies','auxiliary_dependencies','independent_dependencies','registration_core','reference_core','pair_binding_core','implementation_pair_binding','consumer_role_registry','ancestry_contract','shared_ancestry_verifier','consumer_registry_core','consumer_metadata_contract'}
        with patch.multiple(runtime,**PINS),patch.object(Path,'read_bytes',side_effect=AssertionError('Private role selection is pure')):
            for role,count in [('capture_independent_reader',2),('observation_independent_reader',0),('gap_independent_reader',3)]:
                value=runtime.reader_private_inputs(role,modules);self.assertEqual(set(value),keys)
                self.assertEqual(len(value['independent_dependencies']),count)
                self.assertEqual(value['runtime'],host['consumer_registry_view']['consumer_references'][role])
                self.assertEqual(value['shared_ancestry_verifier'],host['bound_pair']['independent_reader_reference'])
                value['dependencies'].clear();self.assertTrue(runtime.reader_private_inputs(role,modules)['dependencies'])
            with self.assertRaises(ValueError):runtime.reader_private_inputs('observation_writer',modules)

    def test_new_observer_business_math_rebuilds_whole_saved_payload(self):
        from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as checker
        from backtest import ndx_prospective_history_parent_view_research_v5 as view
        with TemporaryDirectory()as directory:
            value=context(Path(directory));parent=runtime.parent_documents(value[1],{});observation=runtime.observation_documents(value[2],{})
            capture=runtime.parent_documents(observation['payload']['input_references']['capture'],{})
            started=runtime.decode((Path(value[2]['payload_reference']['path']).parent/'started.json').read_bytes())
            modules=dict(view=view,checker=checker)
            normalized,fields=runtime.continuation_observation_math(parent,observation,capture,started,modules,{})
            self.assertEqual(fields['sequence'],73);self.assertIs(fields['month_first_actual_observation'],False)
            self.assertEqual(fields['first_actual_observed_session_of_month'],'2026-10-02')
            for key,expected in fields.items():self.assertEqual(runtime.encode(observation['payload'][key]),runtime.encode(expected))
            for key,value in [('sequence',True),('source_hash_claims',{}),('known_typed_rows_preserved',[]),('selected_original_rows',{}),('source_row_locations',{})]:
                forged=deepcopy(observation);forged['payload'][key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):runtime.continuation_observation_math(parent,forged,capture,started,modules,{})

    def test_reader_only_and_consumer_failure_only_attempts_cannot_change_namespace(self):
        with TemporaryDirectory()as directory:
            research=Path(directory)/'research';research.mkdir()
            parent=dict(document=dict(history=dict(observations=[])))
            observation={role:dict(path=str(research/'known'/name),sha256='a'*64)for role,name in [('payload_reference','observation_payload.json'),('receipt_reference','receipt.json'),('audit_reference','independent_readback.json')]}
            for name,value in [('reader_started.json',dict(schema='PROSPECTIVE_OBSERVATION_CONTINUATION_READER_STARTED_V1')),
                    ('failure.json',dict(status='FAILED_DO_NOT_CONSUME',consumer_role='observation_independent_reader'))]:
                folder=research/('UNREGISTERED_'+name.replace('.','_'));folder.mkdir();path=folder/name;path.write_bytes(runtime.encode(value))
                with self.subTest(name=name),patch.object(runtime,'RESEARCH',research):
                    with self.assertRaisesRegex(ValueError,'partial or failed'):runtime.current_attempt_inventory(parent,observation,{},[])
                self.assertTrue(path.exists());path.unlink();folder.rmdir()


if __name__=='__main__':unittest.main()

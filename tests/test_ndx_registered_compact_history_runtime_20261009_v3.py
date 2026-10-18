"""Temporary-only host B. Production pair/contract pins remain pending."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_compact_history_runtime_20261009_v3 as runtime
from backtest import ndx_compact_implementation_pair_binding_research_v1 as binder
from backtest import ndx_compact_history_runtime_registration_research_v1 as registration
from ndx_registered_v5_observation_fixture_v2 import physical_registered_v5_observation

PAIR_SHA='dde8b681612d2b4fc0993bb9b697dcefb0222036d3e1bb6f4aa5f2dd76d7e4ad'
CONTRACT_SHA='1f50f4d5a893c163149bf69593880f73a1387293ee04b2ab9c0fcbb58090fc5e'


def pins():
    return dict(PAIR_BINDING_CORE=(runtime.PAIR_BINDING_CORE[0],PAIR_SHA),
        ANCESTRY_CONTRACT=(runtime.ANCESTRY_CONTRACT[0],CONTRACT_SHA))


def physical_context(root,name='compact_pair_v3'):
    research=root/'research'
    parent,observation,original=physical_registered_v5_observation(root,research)
    peer=root/'SYNTHETIC_ONLY_unexecuted_peer.py'
    peer.write_bytes(b'# Synthetic peer identity; not executed or claimed as audited reader.\n')
    dependency_references={key:runtime.reference(*value)for key,value in runtime.DEPENDENCIES.items()}
    reg=dict(schema=registration.SCHEMA,runtime_reference=runtime.reference(runtime.SOURCE,runtime.LOADED_SHA),
        dependency_references=dependency_references,parent=parent,observation=observation,
        output_directory=str(research/name),**registration.FLAGS)
    regpath=root/(name+'_registration.json');regpath.write_bytes(runtime.encode(reg))
    value=dict(schema=binder.SCHEMA,family=binder.FAMILY,protocol=binder.PROTOCOL,role=binder.ROLE,
        publisher_reference=runtime.reference(runtime.SOURCE,runtime.LOADED_SHA),
        independent_reader_reference=runtime.reference(peer,runtime.sha(peer.read_bytes())),
        contract_reference=runtime.reference(runtime.ANCESTRY_CONTRACT[0],CONTRACT_SHA),
        publisher_dependency_references=runtime.publisher_dependencies(),
        reader_dependency_references={key:runtime.reference(*item)for key,item in runtime.READER_ALGORITHMS.items()},
        approved_legacy_binding_references=[],**binder.FLAGS)
    pairpath=root/(name+'_SYNTHETIC_ONLY_pair.json');pairpath.write_bytes(runtime.encode(value))
    args=dict(registration_path=str(regpath),registration_sha256=runtime.sha(regpath.read_bytes()),
        implementation_pair_binding_path=str(pairpath),implementation_pair_binding_sha256=runtime.sha(pairpath.read_bytes()),execute=True)
    return research,parent,observation,original['current'],args,value


def run_context(context):
    research,_,_,current,args,_=context
    with patch.multiple(runtime,RESEARCH=research,CURRENT=current,**pins()):
        return runtime.run(**args)


class CompactPairPublisherTests(unittest.TestCase):
    def test_envelope_loader_does_not_follow_source_claims(self):
        refs={role:dict(path='E:/synthetic/'+role,sha256='a'*64)for role in runtime.ROLES}
        trap='E:/synthetic/source_claim_trap'
        consumed=[]
        def consume(item,sources):
            consumed.append(item['path'])
            if item['path']==trap:raise AssertionError('Claimed path read')
            return runtime.encode(dict(source_hashes={trap:'b'*64}))
        with patch.object(runtime,'consume',side_effect=consume):runtime.parent_documents(refs,{})
        self.assertEqual(set(consumed),{refs[key]['path']for key in ('reference','publication_reference','readback_reference')})

    def test_unknown_pair_is_rejected_before_namespace_or_claim_read(self):
        from backtest import ndx_compact_ancestry_contract_research_v1 as contract
        from test_ndx_compact_ancestry_contract_research_v1 import envelope,pair,refs
        parent=envelope('child',contract.ACTUAL_SCHEMA,refs('prior'),modern=True)
        for field in ('document','publication','readback'):
            parent[field]['implementation_pair_binding_reference']=dict(path='E:/unapproved/B',sha256='f'*64)
            parent[field]['source_hashes']={'E:/trap':'d'*64}
            parent[field]['extra_evidence']={'path':'E:/trap','sha256':'d'*64}
        modules=dict(ancestry=contract,bound_pair=pair(),host_legacy=[])
        with (patch.object(Path,'read_bytes',side_effect=AssertionError('Unclassified source IO')),
                patch.object(runtime,'consume',side_effect=AssertionError('Unclassified source IO'))):
            with self.assertRaises(ValueError):runtime.preflight_original_graph(parent,{},modules,{})

    def test_default_and_pending_all_host_roles_before_io(self):
        args=dict(registration_path='E:/synthetic/registration.json',registration_sha256='a'*64,
            implementation_pair_binding_path='E:/synthetic/binding.json',implementation_pair_binding_sha256='b'*64)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pending source IO')):
            self.assertEqual(runtime.run(**args),dict(status='NOT_EXECUTED'))
            with self.assertRaises(ValueError):runtime.run(**args,execute=True)
        for group,key in [('PAIR_BINDING_CORE',None),('ANCESTRY_CONTRACT',None),('REGISTRATION_CORE',None),
                *(('DEPENDENCIES',key)for key in runtime.DEPENDENCIES),
                *(('AUXILIARIES',key)for key in runtime.AUXILIARIES),
                *(('READER_ALGORITHMS',key)for key in runtime.READER_ALGORITHMS)]:
            updates=pins()
            if key:
                values=deepcopy(getattr(runtime,group));values[key]=(values[key][0],None);updates[group]=values
            else:updates[group]=(getattr(runtime,group)[0],None)
            with self.subTest(group=group,key=key),patch.multiple(runtime,**updates),patch.object(Path,'read_bytes',side_effect=AssertionError('Pending source IO')):
                with self.assertRaises(ValueError):runtime.run(**args,execute=True)

    def test_pair_input_shapes_do_not_relabel_daily_registration(self):
        deps=runtime.publisher_dependencies()
        pair=dict(binding_reference=dict(path='E:/synthetic/B.json',sha256='b'*64),contract_reference=dict(path='E:/synthetic/K.py',sha256='c'*64))
        with patch.multiple(runtime,**pins()):
            result=runtime.pair_inputs(parent={},observation={},registration={},runtime={},dependencies=deps,auxiliary={},registration_core={},pair=pair)
        self.assertEqual(set(result['dependencies']),set(binder.PUBLISHER_DEPENDENCY_ROLES))
        self.assertEqual(set(result['registration_dependency_references']),{'history_core','compact_helpers'})
        self.assertEqual(result['registration_dependency_references'],{key:deps[key]for key in ('history_core','compact_helpers')})

    def test_whole_registered_ancestry_publish_with_temporary_pair(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_pair_publisher_')as folder:
            context=physical_context(Path(folder));result=run_context(context)
            wrapper=runtime.decode(Path(result['history_reference']['path']).read_bytes());h=wrapper['history']
            self.assertEqual((h['typed_row_count'],h['observation_count'],h['gap_count']),(73,3,10))
            self.assertEqual(h['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
            self.assertEqual(wrapper['compact_adapter_schema'],runtime.ADAPTER)
            self.assertEqual(wrapper['implementation_pair_binding_reference'],result['implementation_pair_binding_reference'])
            self.assertEqual(wrapper['input_references']['dependencies'],context[-1]['publisher_dependency_references'])
            self.assertEqual({path.name for path in Path(result['history_reference']['path']).parent.iterdir()},
                {'started.json','history.json','publication.json'})
            for path,digest in wrapper['source_hashes'].items():self.assertEqual(runtime.sha(Path(path).read_bytes()),digest)
            with self.assertRaises(ValueError):run_context(context)


if __name__=='__main__':unittest.main()

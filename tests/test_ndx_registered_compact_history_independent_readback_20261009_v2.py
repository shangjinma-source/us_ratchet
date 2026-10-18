"""Temporary-only complete registered ancestry; real independent peer source."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_compact_history_independent_readback_20261009_v2 as reader
from scripts import ndx_registered_compact_history_runtime_20261009_v3 as publisher
from test_ndx_registered_compact_history_runtime_20261009_v3 import physical_context,pins


def actual_context(root):
    context=physical_context(root)
    research,parent,observation,current,args,binding=context
    binding['independent_reader_reference']=reader.reference(reader.SOURCE,reader.LOADED_SHA)
    pairpath=Path(args['implementation_pair_binding_path']);pairpath.write_bytes(reader.encode(binding))
    args['implementation_pair_binding_sha256']=reader.sha(pairpath.read_bytes())
    with patch.multiple(publisher,RESEARCH=research,CURRENT=current,**pins()):result=publisher.run(**args)
    rargs=dict(args,history_reference=result['history_reference'],publication_reference=result['publication_reference'],output_directory=str(research/'compact_pair_reader_v2'))
    return context,rargs


def read_context(context,args):
    with patch.multiple(reader,RESEARCH=context[0],CURRENT=context[3],**pins()):return reader.readback(**args)


class CompactPairReaderTests(unittest.TestCase):
    def test_default_pending_pre_io(self):
        args=dict(registration_path='E:/synthetic/reg.json',registration_sha256='a'*64,
            history_reference=dict(path='E:/synthetic/history.json',sha256='b'*64),publication_reference=dict(path='E:/synthetic/pub.json',sha256='c'*64),
            output_directory='E:/synthetic/audit',implementation_pair_binding_path='E:/synthetic/B.json',implementation_pair_binding_sha256='d'*64)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pending IO')):
            self.assertEqual(reader.readback(**args),dict(status='NOT_EXECUTED'))
            with self.assertRaises(ValueError):reader.readback(**args,execute=True)
        for group,key in [('PAIR_BINDING_CORE',None),('ANCESTRY_CONTRACT',None),('REGISTRATION_CORE',None),
                *(('DEPENDENCIES',key)for key in reader.DEPENDENCIES),*(('AUXILIARIES',key)for key in reader.AUXILIARIES),
                *(('READER_ALGORITHMS',key)for key in reader.READER_ALGORITHMS)]:
            updates=pins()
            if key:
                values=deepcopy(getattr(reader,group));values[key]=(values[key][0],None);updates[group]=values
            else:updates[group]=(getattr(reader,group)[0],None)
            with self.subTest(group=group,key=key),patch.multiple(reader,**updates),patch.object(Path,'read_bytes',side_effect=AssertionError('Pending IO')):
                with self.assertRaises(ValueError):reader.readback(**args,execute=True)

    def test_read_only_default_pending_pre_io(self):
        args=dict(parent_references={},implementation_pair_binding_path='E:/synthetic/B.json',implementation_pair_binding_sha256='d'*64)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pending readonly IO')):
            self.assertEqual(reader.verify_saved_parent_ancestry(**args),dict(status='NOT_EXECUTED'))
            with self.assertRaises(ValueError):reader.verify_saved_parent_ancestry(**args,execute=True)

    def test_untrusted_claim_and_reader_are_not_initial_io_queue(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_claim_gate_')as directory:
            root=Path(directory);refs={};trap=root/'untrusted_trap.py'
            for role,name in [('reference','document'),('publication_reference','publication'),('readback_reference','readback')]:
                path=root/(name+'.json');path.write_bytes(reader.encode(dict(source_hashes={str(trap):'a'*64})))
                refs[role]=reader.reference(path,reader.sha(path.read_bytes()))
            refs['reader_reference']=reader.reference(trap,'b'*64)
            original=Path.read_bytes
            def bounded(path):
                if path==trap:raise AssertionError('Untrusted declaration followed before role gate')
                return original(path)
            sources={}
            with patch.object(Path,'read_bytes',bounded):
                reader.parent_documents(refs,sources)
            self.assertEqual(set(sources),{item['path']for key,item in refs.items()if key!='reader_reference'})

    def test_read_only_registered_legacy_ancestry_with_unexecuted_peer_identity(self):
        # This certifies R arithmetic on complete registered legacy ancestors;
        # the publisher identity stub is expressly not a paired-P acceptance.
        from ndx_registered_v5_observation_fixture_v2 import physical_registered_v5_observation
        from backtest import ndx_compact_implementation_pair_binding_research_v1 as binder
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_readonly_legacy_')as directory:
            root=Path(directory);research=root/'research'
            parent,observation,original=physical_registered_v5_observation(root,research)
            peer=root/'SYNTHETIC_ONLY_unexecuted_publisher.py';peer.write_bytes(b'# Unexecuted peer identity; no publisher validation claim.\n')
            binding=dict(schema=binder.SCHEMA,family=binder.FAMILY,protocol=binder.PROTOCOL,role=binder.ROLE,
                publisher_reference=reader.reference(peer,reader.sha(peer.read_bytes())),
                independent_reader_reference=reader.reference(reader.SOURCE,reader.LOADED_SHA),
                contract_reference=reader.reference(reader.ANCESTRY_CONTRACT[0],pins()['ANCESTRY_CONTRACT'][1]),
                publisher_dependency_references=reader.publisher_dependencies(),
                reader_dependency_references={key:reader.reference(*item)for key,item in reader.READER_ALGORITHMS.items()},
                approved_legacy_binding_references=[],**binder.FLAGS)
            pairpath=root/'SYNTHETIC_ONLY_binding.json';pairpath.write_bytes(reader.encode(binding))
            # Original fixture has an extra saved current observation beyond its
            # parent. Include it by checking that observation's true V5 parent
            # graph using the main replay components, without a publication.
            with patch.multiple(reader,RESEARCH=research,CURRENT=original['current'],**pins()):
                with self.assertRaisesRegex(ValueError,'Unregistered or duplicate semantic observation'):
                    reader.verify_saved_parent_ancestry(parent_references=parent,
                        implementation_pair_binding_path=str(pairpath),implementation_pair_binding_sha256=reader.sha(pairpath.read_bytes()),execute=True)

    def test_entire_registered_actual_and_gap_ancestry(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_pair_reader_')as directory:
            context,args=actual_context(Path(directory));report=read_context(context,args)
            value=reader.decode(Path(report['path']).read_bytes())
            self.assertEqual((value['counts']['typed_row_count'],value['counts']['observation_count'],value['counts']['gap_count']),(73,3,10))
            self.assertTrue(value['entire_history_independently_reconstructed'])
            self.assertFalse(value['publisher_called']);self.assertFalse(value['new_pure_called'])
            for path,digest in value['source_hashes'].items():self.assertEqual(reader.sha(Path(path).read_bytes()),digest)
            with self.assertRaises(ValueError):read_context(context,args)
            parent_refs=dict(reference=args['history_reference'],publication_reference=args['publication_reference'],
                readback_reference=report,reader_reference=reader.reference(reader.SOURCE,reader.LOADED_SHA))
            before={str(path):reader.sha(path.read_bytes())for path in context[0].rglob('*')if path.is_file()}
            with patch.multiple(reader,RESEARCH=context[0],CURRENT=context[3],**pins()):
                verified=reader.verify_saved_parent_ancestry(parent_references=parent_refs,
                    implementation_pair_binding_path=args['implementation_pair_binding_path'],
                    implementation_pair_binding_sha256=args['implementation_pair_binding_sha256'],execute=True)
            self.assertEqual(verified['status'],'READ_ONLY_WHOLE_ANCESTRY_RECONSTRUCTION_PASS')
            self.assertEqual(before,{str(path):reader.sha(path.read_bytes())for path in context[0].rglob('*')if path.is_file()})
            verified['final_guard']()
            # Unknown metadata references and claims are coordinated across all
            # three originals, but may not select a file for private-helper IO.
            saved={role:Path(item['path']).read_bytes()for role,item in parent_refs.items()if role!='reader_reference'}
            trap=Path(directory)/'never_follow_unknown_metadata.py'
            changed=deepcopy(parent_refs)
            for role in ('reference','publication_reference','readback_reference'):
                path=Path(changed[role]['path']);value=reader.decode(saved[role])
                value['unexpected_metadata_reference']=reader.reference(trap,'f'*64)
                value['source_hashes'][str(trap)]='f'*64
                if role!='reference':value['history_reference']=changed['reference']
                if role=='readback_reference':
                    value['publication_reference']=changed['publication_reference']
                    for refrole in ('reference','publication_reference'):value['source_hashes'][changed[refrole]['path']]=changed[refrole]['sha256']
                path.write_bytes(reader.encode(value));changed[role]=reader.reference(path,reader.sha(path.read_bytes()))
            original=Path.read_bytes
            def reject_trap(path):
                if path==trap:raise AssertionError('Unknown metadata source followed before closed-role rejection')
                return original(path)
            try:
                with patch.multiple(reader,RESEARCH=context[0],CURRENT=context[3],**pins()),patch.object(Path,'read_bytes',reject_trap):
                    with self.assertRaisesRegex(ValueError,'no independently discovered role'):
                        reader.verify_saved_parent_ancestry(parent_references=changed,
                            implementation_pair_binding_path=args['implementation_pair_binding_path'],
                            implementation_pair_binding_sha256=args['implementation_pair_binding_sha256'],execute=True)
            finally:
                for role,raw in saved.items():Path(parent_refs[role]['path']).write_bytes(raw)
            ancestor=Path(context[1]['reference']['path']).parent/'new_unregistered_extra.json'
            ancestor.write_bytes(b'{}')
            with self.assertRaises(ValueError):verified['final_guard']()

if __name__=='__main__':unittest.main()

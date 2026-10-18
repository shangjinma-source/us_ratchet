"""Real saved P/R parent closure attacks; temporary registered chain only."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backtest import ndx_compact_implementation_pair_binding_research_v1 as binder
from backtest import ndx_compact_ancestry_contract_research_v1 as ancestry
from scripts import ndx_registered_compact_history_runtime_20261009_v3 as publisher
from scripts import ndx_registered_compact_history_independent_readback_20261009_v2 as reader
from test_ndx_registered_compact_history_runtime_20261009_v3 import pins
from test_ndx_registered_compact_history_independent_readback_20261009_v2 import actual_context, read_context
from test_ndx_registered_compact_history_runtime_20261009_v3_preclosure_independent_review import coordinated_source_omission


class RealPairParentSourceOmissionTests(unittest.TestCase):
    def test_each_peer_derives_mandatory_closure_instead_of_trusting_resigned_maps(self):
        with TemporaryDirectory(prefix='REAL_PAIR_PARENT_CLOSURE_ONLY_') as folder:
            context, args = actual_context(Path(folder))
            report = read_context(context, args)
            refs = dict(reference=args['history_reference'], publication_reference=args['publication_reference'],
                readback_reference=report, reader_reference=reader.reference(reader.SOURCE, reader.LOADED_SHA))
            folder = Path(refs['reference']['path']).parent
            auditfolder = Path(report['path']).parent
            paths = [folder/'started.json', folder/'history.json', folder/'publication.json',
                auditfolder/'started.json', auditfolder/'independent_readback.json']
            saved = {path:path.read_bytes() for path in paths}
            wrapper = publisher.decode(saved[paths[1]])
            mandatory = {
                'host_binding':args['implementation_pair_binding_path'],
                'ancestry_contract':str(publisher.ANCESTRY_CONTRACT[0]),
                'pair_kernel':str(publisher.PAIR_BINDING_CORE[0]),
                'reader_independent_algorithm':str(reader.READER_ALGORITHMS['history_reconstructor'][0])
            }
            mandatory['old_observation_started'] = next(path for path in wrapper['source_hashes']
                if Path(path).name == 'started.json' and Path(path).parent.name == 'registered_v4_root_observation')
            # All targets really belong to each saved START/published/audited map.
            for name, target in mandatory.items():
                for path in (paths[0],paths[1],paths[2],paths[4]):
                    self.assertIn(target, publisher.decode(saved[path])['source_hashes'], (name,path))
            captures = {}
            # Build P's genuine host-loaded replay context, never R's arithmetic.
            with patch.multiple(publisher, RESEARCH=context[0], CURRENT=context[3], **pins()):
                sources = {}
                dependencies = {key:publisher.reference(*item) for key,item in publisher.DEPENDENCIES.items()}
                auxiliary = {key:publisher.reference(*item) for key,item in publisher.AUXILIARIES.items()}
                modules = publisher.load_modules(dependencies, auxiliary, sources)
                pair = binder.inspect_pair_binding(binding=publisher.decode(Path(args['implementation_pair_binding_path']).read_bytes()),
                    binding_reference=publisher.reference(args['implementation_pair_binding_path'],args['implementation_pair_binding_sha256']),
                    host_binding_reference=publisher.reference(args['implementation_pair_binding_path'],args['implementation_pair_binding_sha256']),
                    self_role='publisher', self_reference=publisher.reference(publisher.SOURCE,publisher.LOADED_SHA),
                    expected_contract_reference=publisher.reference(publisher.ANCESTRY_CONTRACT[0],pins()['ANCESTRY_CONTRACT'][1]),
                    expected_algorithm_dependencies=dict(publisher=publisher.publisher_dependencies(),
                        independent_reader={key:publisher.reference(*item) for key,item in publisher.READER_ALGORITHMS.items()}))
                modules.update(bound_pair=pair, ancestry=ancestry,host_legacy=publisher.host_legacy_implementations())
                parent = publisher.parent_documents(refs,sources)
                observation=publisher.observation_documents(context[2],sources)
                publisher.preflight_original_graph(parent,observation,modules,sources)
                original = publisher.verify_actual_outer
                def capture_p(*values):
                    result=original(*values)
                    if values[0]['reference']==refs['reference']: captures['P']=values
                    return result
                with patch.object(publisher,'verify_actual_outer',side_effect=capture_p):
                    publisher.walk_parent_graph(parent,modules,sources,auxiliary)
            # R's exact same outer-parent validator must pass on the genuine audit.
            original_r = reader.verify_actual_outer
            def capture_r(*values):
                result=original_r(*values)
                if values[0]['reference']==refs['reference']: captures['R']=values
                return result
            with patch.multiple(reader,RESEARCH=context[0],CURRENT=context[3],**pins()), \
                    patch.object(reader,'verify_actual_outer',side_effect=capture_r):
                verified=reader.verify_saved_parent_ancestry(parent_references=refs,
                    implementation_pair_binding_path=args['implementation_pair_binding_path'],
                    implementation_pair_binding_sha256=args['implementation_pair_binding_sha256'],execute=True)
                self.assertEqual(verified['status'],'READ_ONLY_WHOLE_ANCESTRY_RECONSTRUCTION_PASS')
            self.assertEqual(set(captures),{'P','R'})
            for name,target in mandatory.items():
                try:
                    coordinated_source_omission(paths,target)
                    changed=deepcopy(refs)
                    for role in ('reference','publication_reference','readback_reference'):
                        path=Path(changed[role]['path']);changed[role]=publisher.reference(path,publisher.sha(path.read_bytes()))
                    for label,host,validator in (('P',publisher,original),('R',reader,original_r)):
                        oldparent,prior,history,modules,_,auxiliary=captures[label]
                        # Cache only values independently derived by this exact peer's
                        # successful full baseline replay; no claims-derived substitute.
                        key=(oldparent['reference']['path'],oldparent['reference']['sha256'])
                        newkey=(changed['reference']['path'],changed['reference']['sha256'])
                        modules['pair_initial_source_cache'][newkey]=deepcopy(modules['pair_initial_source_cache'][key])
                        with self.subTest(omitted=name,peer=label), \
                                patch.multiple(host,RESEARCH=context[0],CURRENT=context[3],**pins()):
                            altered=host.parent_documents(changed,{})
                            with self.assertRaisesRegex(ValueError,'Whole host-derived pair publisher source closure'):
                                validator(altered,prior,history,modules,{},auxiliary)
                finally:
                    for path,raw in saved.items():path.write_bytes(raw)
            self.assertEqual(saved,{path:path.read_bytes()for path in paths})
            self.assertFalse((context[0]/'unrequested_descendant').exists())


if __name__=='__main__':unittest.main()

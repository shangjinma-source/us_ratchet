"""Root independent formula and ancestor inventory review; disposable IO only."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_compact_history_runtime_20261009_v2 as runtime
from scripts import ndx_registered_compact_history_independent_readback_20261009_v1 as formula
from backtest import ndx_compact_actual_independent_reconstruction_research_v1 as independent
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from backtest import ndx_capture_source_csv_independent_reconstruction_research_v1 as csv_checker
import test_ndx_registered_compact_history_runtime_20261009_v2 as fixture


class RootCompactV2OriginalChainReview(unittest.TestCase):
    def test_whole_independent_formula_and_all_temporary_start_namespaces(self):
        with TemporaryDirectory(prefix='ROOT_REGISTERED_COMPACT_V2_ONLY_') as directory:
            root=Path(directory)
            context=fixture.physical_context(root)
            result=fixture.run_context(context)
            document=runtime.decode(Path(result['history_reference']['path']).read_bytes())
            parent=runtime.parent_documents(context[1],{})
            observation=runtime.observation_documents(context[2],{})
            state=view.inspect_parent_history_v5(parent)
            blobs={}
            for parts in observation['payload']['full_original_sources_preserved'].values():
                for part in parts.values():
                    item=part['reference'];blobs[item['path']]=Path(item['path']).read_bytes()
            for item in (*state['baseline_references'].values(),*state['accounted_baseline_references'].values(),observation['payload']['tzif_reference']):
                blobs[item['path']]=Path(item['path']).read_bytes()
            expected=independent.reconstruct_compact_actual(parent=parent,observation=observation,blobs=blobs,
                parent_checker=view,csv_rows=csv_checker.csv_rows,independent_formula=formula)
            self.assertEqual(runtime.encode(document['history']),runtime.encode(expected))
            # Derive inventories from the actual temporary tree, not the producer's source table.
            starts=sorted(root.rglob('started.json'))
            self.assertGreaterEqual(len(starts),10)
            for path in starts:
                self.assertEqual(document['source_hashes'].get(str(path)),runtime.sha(path.read_bytes()),str(path))
            output=Path(result['history_reference']['path']).parent
            ancestor_dirs=sorted({path.parent for path in starts if path.parent!=output})
            self.assertGreaterEqual(len(ancestor_dirs),9)
            original_args=context[-1]
            registration=runtime.decode(Path(original_args['registration_path']).read_bytes())
            save=runtime.save
            for index,ancestor in enumerate(ancestor_dirs):
                with self.subTest(ancestor=str(ancestor)):
                    extra=ancestor/'unexpected_ancestor_file.txt'
                    value=deepcopy(registration)
                    value['output_directory']=str(context[0]/('root_drift_'+str(index)))
                    regpath=root/('root_drift_registration_'+str(index)+'.json')
                    regpath.write_bytes(runtime.encode(value))
                    args=dict(registration_path=str(regpath),registration_sha256=runtime.sha(regpath.read_bytes()),execute=True)
                    attempted=(*context[:-1],args)
                    def save_with_extra(path,value):
                        reference=save(path,value)
                        if path.name=='history.json':extra.write_bytes(b'Unexpected original ancestor inventory drift\n')
                        return reference
                    try:
                        with patch.object(runtime,'save',side_effect=save_with_extra),self.assertRaises(ValueError):
                            fixture.run_context(attempted)
                        failed=Path(value['output_directory'])
                        self.assertTrue((failed/'history.json').is_file())
                        self.assertTrue((failed/'failure.json').is_file())
                        self.assertFalse((failed/'publication.json').exists())
                    finally:
                        if extra.exists():extra.unlink()

            # A new semantic writer attempt outside the bound ancestry is still
            # inside the declared local direct-child discovery scope.
            partial=context[0]/'root_unregistered_writer_attempt'
            partial.mkdir()
            (partial/'started.json').write_bytes(runtime.encode(dict(
                schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V5',
                writer_started_at_utc='2026-10-13T20:07:00+00:00')))
            value=deepcopy(registration)
            value['output_directory']=str(context[0]/'root_unregistered_attempt_reject')
            regpath=root/'root_unregistered_attempt_registration.json'
            regpath.write_bytes(runtime.encode(value))
            args=dict(registration_path=str(regpath),registration_sha256=runtime.sha(regpath.read_bytes()),execute=True)
            with self.assertRaises(ValueError):fixture.run_context((*context[:-1],args))
            self.assertFalse(Path(value['output_directory']).exists())
            self.assertTrue((partial/'started.json').is_file())



if __name__=='__main__':unittest.main()

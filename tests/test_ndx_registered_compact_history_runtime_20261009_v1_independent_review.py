"""Private dependency and full physical registered publication in temp only."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_registered_compact_history_runtime_20261009_v1 as runtime
from scripts import ndx_prospective_observation_writer_v3_20261009 as writer
from scripts import ndx_prospective_observation_independent_readback_v3_20261009 as observation_reader
from backtest import ndx_compact_history_runtime_registration_research_v1 as registration_core
from test_ndx_prospective_observation_v3_full_temporary_io_independent_review import physical_capture

REGISTRATION_SHA='d0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23'


def physical_observation(root):
    capture,producer,core=physical_capture(root);output=root/'synthetic_observation'
    with (patch.multiple(writer,OUTPUT=output,CAPTURE_BOUND=capture,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core),
          patch.object(writer,'now',side_effect=['2026-10-08T20:01:00+00:00','2026-10-08T20:01:01+00:00','2026-10-09T13:30:00+00:00'])):
        receipt=writer.run(execute=True)
    payload=runtime.reference(output/'observation_payload.json',runtime.sha((output/'observation_payload.json').read_bytes()))
    with patch.multiple(observation_reader,BASE=output,CAPTURE_BOUND=capture,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core,
        WRITER=(str(writer.SOURCE),writer.LOADED_SHA),PAYLOAD_SHA=payload['sha256'],RECEIPT_SHA=receipt['sha256']):
        audit=observation_reader.readback(execute=True)
    return dict(payload_reference=payload,receipt_reference=receipt,audit_reference=audit,
        reader_reference=runtime.reference(observation_reader.SOURCE,observation_reader.LOADED))


def registration(root,research,observation,name='synthetic_compact_pass'):
    value=dict(schema=registration_core.SCHEMA,runtime_reference=runtime.reference(runtime.SOURCE,runtime.LOADED_SHA),
        dependency_references={key:runtime.reference(*ref) for key,ref in runtime.DEPENDENCIES.items()},
        parent=deepcopy(writer.PARENT_BOUND),observation=deepcopy(observation),
        output_directory=str(research/name),**registration_core.FLAGS)
    path=root/(name+'_registration.json');path.write_bytes(runtime.encode(value))
    return path,runtime.sha(path.read_bytes()),value


class IndependentRegisteredCompactTests(unittest.TestCase):
    def test_pending_all_host_references_are_rejected_before_source_io(self):
        cases=('registration_core','registration','dependency')
        for mode in cases:
            core=(runtime.REGISTRATION_CORE[0],None if mode=='registration_core' else REGISTRATION_SHA)
            dependencies=deepcopy(runtime.DEPENDENCIES)
            if mode=='dependency':dependencies['history_core']=(dependencies['history_core'][0],None)
            with (patch.multiple(runtime,REGISTRATION_CORE=core,DEPENDENCIES=dependencies),
                  patch.object(Path,'read_bytes',side_effect=AssertionError('IO before pending')),
                  patch.object(Path,'mkdir',side_effect=AssertionError('Output before pending'))):
                with self.subTest(mode=mode),self.assertRaises(ValueError):runtime.run(
                    registration_path='E:/synthetic.json',registration_sha256=None if mode=='registration' else 'a'*64,execute=True)

    def test_conflicting_windows_path_alias_and_link_cannot_be_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source';path.write_bytes(b'original');ref=runtime.reference(path,runtime.sha(b'original'))
            sources={str(path).upper():'f'*64}
            with self.assertRaisesRegex(ValueError,'Conflicting path alias'):runtime.consume(ref,sources)
            target=Path(folder)/'target';target.write_bytes(b'original');path.unlink()
            try:path.symlink_to(target)
            except OSError as error:self.skipTest(str(error))
            with self.assertRaises(ValueError):runtime.consume(ref,{})

    def test_full_physical_publication_private_closure_failure_retained_and_host_binding(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_registered_compact_') as folder:
            root=Path(folder);research=root/'research';research.mkdir();observation=physical_observation(root)
            path,digest,reg=registration(root,research,observation)
            fake=SimpleNamespace(rows_check=lambda *args: (_ for _ in ()).throw(AssertionError('sys.modules helper')))
            with (patch.multiple(runtime,RESEARCH=research,REGISTRATION_CORE=(runtime.REGISTRATION_CORE[0],REGISTRATION_SHA)),
                  patch.dict(sys.modules,{'backtest.ndx_prospective_observation_parent_history_research':fake})):
                result=runtime.run(registration_path=str(path),registration_sha256=digest,execute=True)
                document=runtime.decode(Path(result['history_reference']['path']).read_bytes());history=document['history']
                self.assertEqual((history['typed_row_count'],history['observation_count'],history['gap_count']),(70,2,8))
                self.assertEqual(history['observations'][-1]['timing_classification'],'LATE_OBSERVATION')
                self.assertFalse(history['observations'][-1]['month_first_actual_observation'])
                self.assertEqual(history['baseline_references'],history['accounted_baseline_references'])
                self.assertTrue(all(result[key] is False for key in runtime.FLAGS))
                self.assertEqual({p.name for p in Path(reg['output_directory']).iterdir()},{'started.json','history.json','publication.json'})
                for source,sha in document['source_hashes'].items():self.assertEqual(runtime.sha(Path(source).read_bytes()),sha)
                with self.assertRaisesRegex(ValueError,'Create-only'):runtime.run(registration_path=str(path),registration_sha256=digest,execute=True)
                # A caller cannot redirect host-owned dependencies by rehashing registration.
                badpath,badsha,bad=registration(root,research,observation,'synthetic_bad_host')
                bad['dependency_references']['history_core']['sha256']='f'*64
                badpath.write_bytes(runtime.encode(bad));badsha=runtime.sha(badpath.read_bytes())
                with self.assertRaisesRegex(ValueError,'Host dependency'):runtime.run(registration_path=str(badpath),registration_sha256=badsha,execute=True)
                self.assertFalse(Path(bad['output_directory']).exists())
                failedpath,failedsha,failed=registration(root,research,observation,'synthetic_failed_compact')
                real_save=runtime.save
                def fail_history(path,value):
                    if path.name=='history.json':raise ValueError('Injected publication failure')
                    return real_save(path,value)
                with patch.object(runtime,'save',side_effect=fail_history):
                    with self.assertRaisesRegex(ValueError,'Injected publication failure'):
                        runtime.run(registration_path=str(failedpath),registration_sha256=failedsha,execute=True)
                failed_output=Path(failed['output_directory'])
                self.assertTrue((failed_output/'started.json').is_file());self.assertTrue((failed_output/'failure.json').is_file())
                self.assertFalse((failed_output/'publication.json').exists())
                with self.assertRaisesRegex(ValueError,'Create-only'):
                    runtime.run(registration_path=str(failedpath),registration_sha256=failedsha,execute=True)


if __name__=='__main__':unittest.main()

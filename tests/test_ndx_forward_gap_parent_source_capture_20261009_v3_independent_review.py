"""Independent temporary IO attacks; never accesses the actual output namespace."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_forward_gap_parent_source_capture_20261009_v3 as producer
import test_ndx_forward_gap_parent_source_capture_20261009_v3 as author_tests


class IndependentProducerTests(unittest.TestCase):
    def test_private_compilation_ignores_module_cache_and_rejects_drift(self):
        raw={key:(producer.ROOT/path).read_bytes() for key,(path,_) in producer.DEPENDENCIES.items()}
        raw['pure']=producer.PURE.read_bytes()
        fake=SimpleNamespace(scoped_csv=lambda *a: (_ for _ in ()).throw(AssertionError('Fake parser')))
        with (patch.object(producer,'PURE_SHA',producer.digest(raw['pure'])),
              patch.dict(sys.modules,{'backtest.ndx_forward_source_capture_scoped_research':fake,
                                      'backtest.ndx_forward_gap_parent_capture_research_v3':fake})):
            core=producer.private_core(raw)
            self.assertEqual(core.scoped_csv.__module__,'_gap_parent_capture_scoped')
            changed=dict(raw,scoped=raw['scoped']+b'\n# changed')
            with self.assertRaises(ValueError):producer.private_core(changed)

    def test_plan_source_outside_verified_closure_keeps_failure_and_no_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            stack,core=author_tests.CaptureIOTests().fixture(Path(folder))
            original=core.plan_gap_parent_capture
            def attack(**arguments):
                plan=original(**arguments)
                plan['source_reference_claims']['unverified-source']='a'*64
                return plan
            core.plan_gap_parent_capture=attack
            with stack:
                with self.assertRaisesRegex(ValueError,'outside immutable'):
                    producer.run(execute=True)
                self.assertTrue((producer.OUTPUT/'failure.json').is_file())
                self.assertFalse((producer.OUTPUT/'publication.json').exists())

    def test_live_cache_drift_between_capture_and_publication_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            stack,core=author_tests.CaptureIOTests().fixture(Path(folder))
            original=core.plan_gap_parent_capture
            def drift(**arguments):
                producer.CURRENT['QQQ'].write_bytes(b'late cache revision')
                return original(**arguments)
            core.plan_gap_parent_capture=drift
            with stack:
                with self.assertRaisesRegex(ValueError,'SHA changed'):
                    producer.run(execute=True)
                self.assertTrue((producer.OUTPUT/'failure.json').is_file())
                self.assertFalse((producer.OUTPUT/'capture.json').exists())

    def test_parent_namespace_files_directories_links_and_source_drift_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);source=path/'source.json';source.write_bytes(b'original')
            producer.namespace(path,('source.json',))
            item=producer.reference(str(source),producer.digest(b'original'))
            source.write_bytes(b'drift')
            with self.assertRaises(ValueError):producer.consume(item,{})
            source.unlink();source.mkdir()
            with self.assertRaises(ValueError):producer.namespace(path,('source.json',))
            source.rmdir();target=path.parent/(path.name+'-target')
            target.write_bytes(b'original')
            try:
                source.symlink_to(target)
                with self.assertRaises(ValueError):producer.namespace(path,('source.json',))
            except OSError as error:self.skipTest('Symlink unavailable: '+str(error))
            finally:target.unlink()


if __name__=='__main__':unittest.main()

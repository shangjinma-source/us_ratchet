"""Temporary physical publication/readback integration, no actual namespaces."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_multidecision_path_presentation_20261008 as publisher
from scripts import ndx_multidecision_path_presentation_independent_readback_20261008 as reader
from backtest import ndx_multidecision_path_presentation_research as projection
import test_ndx_multidecision_path_presentation_source_20261008 as fixture_source


class ReaderSourceTests(unittest.TestCase):
    def environment(self, directory):
        env = fixture_source.SourceTests().environment(directory)
        with patch.multiple(publisher, **env):
            result = publisher.run(execute=True)
        publication = env['OUTPUT'] / 'publication.json'
        artifacts = dict(presentation=(result['path'], result['sha256']),
            publication=(str(publication), reader.sha(publication.read_bytes())),
            publisher=(str(publisher.SOURCE), publisher.LOADED),
            checker=(reader.ARTIFACT_BOUND['checker'][0], reader.sha(Path(reader.ARTIFACT_BOUND['checker'][0]).read_bytes())))
        return dict(BOUND=env['BOUND'], PURE_SHA=env['PURE_SHA'], PARENT=env['PARENT'], AUDIT_ROOT=env['AUDIT_ROOT'],
            PRESENTATION_ROOT=env['OUTPUT'], OUTPUT=Path(directory) / 'readback', ARTIFACT_BOUND=artifacts)

    def test_complete_readback_without_publisher_or_projection_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.environment(directory)
            with patch.multiple(reader, **env), patch.object(publisher, 'run', side_effect=AssertionError('publisher execution')), patch.object(projection, 'build_tables', side_effect=AssertionError('projection execution')):
                ref = reader.readback(execute=True)
                report = json.loads(Path(ref['path']).read_bytes())
                self.assertEqual(report['inspection']['table_count'], 11)
                self.assertEqual(report['status'], 'PASS_SAVED_EVIDENCE_PROJECTION')
                self.assertFalse(report['projection_core_called'])
                self.assertFalse(report['full_h_delivery_complete'])
                self.assertEqual({p.name for p in reader.OUTPUT.iterdir()}, {'started.json', 'independent_readback.json'})

    def test_resigned_wrong_cell_rejected_by_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.environment(directory)
            path = Path(env['ARTIFACT_BOUND']['presentation'][0])
            document = json.loads(path.read_bytes())
            document['presentation']['tables'][-1]['rows'][-1][7] = 'invented exposure'
            ref = fixture_source.write(path, document)
            pubpath = Path(env['ARTIFACT_BOUND']['publication'][0])
            pub = json.loads(pubpath.read_bytes()); pub['presentation_reference'] = ref
            pubref = fixture_source.write(pubpath, pub)
            env['ARTIFACT_BOUND']['presentation'] = (ref['path'], ref['sha256'])
            env['ARTIFACT_BOUND']['publication'] = (pubref['path'], pubref['sha256'])
            with patch.multiple(reader, **env):
                with self.assertRaises(ValueError): reader.readback(execute=True)
                self.assertTrue((reader.OUTPUT / 'failure.json').exists())
                self.assertFalse((reader.OUTPUT / 'independent_readback.json').exists())

    def test_pending_pin_and_extra_parent_prevent_output(self):
        for attack in ('pending', 'extra'):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as directory:
                env = self.environment(directory)
                if attack == 'pending': env['ARTIFACT_BOUND']['presentation'] = (env['ARTIFACT_BOUND']['presentation'][0], None)
                else: (env['PRESENTATION_ROOT'] / 'orphan.json').write_text('{}')
                with patch.multiple(reader, **env):
                    with self.assertRaises(ValueError): reader.readback(execute=True)
                    self.assertFalse(reader.OUTPUT.exists())


if __name__ == '__main__':
    unittest.main()

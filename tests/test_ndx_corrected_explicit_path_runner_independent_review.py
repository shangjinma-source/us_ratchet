import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_corrected_explicit_path_runner_research as m
import test_ndx_corrected_explicit_path_runner_research as fixtures


class Tests(unittest.TestCase):
    def test_competing_marker_created_during_prepare_never_builds(self):
        with tempfile.TemporaryDirectory() as folder:
            args=fixtures.Tests().arguments(folder);marker=Path(args['output']+'.started.json')
            def raced(**kwargs):
                marker.write_text('{}');return object()
            with patch.object(m.core,'prepare_explicit_path',side_effect=raced),patch.object(m.core,'build_path_targets') as build:
                with self.assertRaises(FileExistsError):m.run(**args,execute=True)
                build.assert_not_called()
            self.assertFalse(Path(args['output']).exists())

    def test_source_drift_after_publication_never_returns_success(self):
        with tempfile.TemporaryDirectory() as folder:
            args=fixtures.Tests().arguments(folder);source=Path(folder)/'evidence.txt';source.write_text('original')
            sources={str(source):hashlib.sha256(source.read_bytes()).hexdigest()}
            result=dict(schema='CORRECTED_EXPLICIT_STRATEGIC_TARGET_PATH_V1',first_seed_imported_without_refit=True,new_fit_count=1,
                schedule=[{},{}],historical_expected_source_hashes=sources,archive_resolution={},historical_loader_gap_observations=[])
            original_publish=m.core.snapshot.single.publish
            def publish(path,value):
                saved=original_publish(path,value)
                if Path(path)==Path(args['output']):source.write_text('changed during publication')
                return saved
            def verify(expected,contract):
                m.core.adapter.archive.strict(expected);return {}
            with patch.object(m.core,'prepare_explicit_path'),patch.object(m.core,'build_path_targets',return_value=result),patch.object(m.core.adapter.archive,'load_contract',return_value={}),patch.object(m.core.adapter.archive,'verify_expected_sources',side_effect=verify),patch.object(m.core.snapshot.single,'publish',side_effect=publish):
                with self.assertRaises(ValueError):m.run(**args,execute=True)
            self.assertTrue(Path(args['output']).exists())
            with patch.object(m.core,'prepare_explicit_path') as prepare:
                with self.assertRaises(FileExistsError):m.run(**args,execute=True)
                prepare.assert_not_called()


if __name__=='__main__':unittest.main()

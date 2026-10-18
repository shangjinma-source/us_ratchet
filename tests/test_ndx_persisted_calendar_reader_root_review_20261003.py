"""Independent checks for source-only readback and re-signed authority attacks."""
import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_persisted_candidate_calendar_independent_readback_20261003 as subject
from test_ndx_persisted_candidate_calendar_independent_readback_20261003 import staged, patched, w


class CalendarReadbackReview(unittest.TestCase):
    def test_readback_never_runs_producer_or_reads_live_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = staged(Path(directory))
            original_read = Path.read_bytes
            forbidden = {(subject.ROOT / 'data/cache' / f'{ticker}.csv').resolve()
                         for ticker in ('QQQ', 'SPY')}

            def read(path):
                self.assertNotIn(path.resolve(), forbidden)
                return original_read(path)

            with patched(settings), patch.object(w, 'run', side_effect=AssertionError('producer call')), \
                 patch.object(Path, 'read_bytes', read):
                output = subject.readback(execute=True)
            self.assertEqual(json.loads(Path(output['path']).read_bytes())['status'], 'PASS')
        tree = ast.parse(Path(subject.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ('exec', 'eval', 'compile', '__import__'))

    def test_resigned_permission_upgrade_cannot_be_accepted(self):
        for value in (True, 0):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                settings = staged(Path(directory))
                parent = settings['PARENT']
                result = json.loads((parent / 'result.json').read_bytes())
                publication = json.loads((parent / 'publication.json').read_bytes())
                for obj in (result, result['evidence'], publication):
                    obj['candidate_seal_allowed'] = value
                result_bytes = subject.enc(result)
                (parent / 'result.json').write_bytes(result_bytes)
                settings['RESULT_SHA'] = subject.sha(result_bytes)
                publication['result_reference']['sha256'] = settings['RESULT_SHA']
                publication_bytes = subject.enc(publication)
                (parent / 'publication.json').write_bytes(publication_bytes)
                settings['PUBLICATION_SHA'] = subject.sha(publication_bytes)
                with patched(settings):
                    with self.assertRaises(ValueError):
                        subject.readback(execute=True)
                    self.assertTrue((settings['OUTPUT'] / 'failure.json').exists())
                    with self.assertRaises(ValueError):
                        subject.readback(execute=True)


if __name__ == '__main__':
    unittest.main()

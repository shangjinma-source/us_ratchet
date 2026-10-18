from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from test_collect_monthly_automatic_review_evidence import fixture
from scripts.collect_monthly_automatic_review_evidence import collect
from scripts.coordinate_monthly_simulation import run


class CollectorReuseIntegrityTests(unittest.TestCase):
    def test_changed_training_bytes_reject_completed_collection_without_refetch(self):
        with TemporaryDirectory() as directory:
            root, arguments, calls, daily, collection, requests = fixture(directory)
            manual = {key:value for key,value in arguments.items() if not key.startswith('auto_review_')}
            self.assertEqual(run(**manual, execute=True)['status'], 'WAITING_REVIEW')
            self.assertEqual(collect(**collection, execute=True)['status'], 'EVIDENCE_READY')
            originals = list((root/'actual-capture').rglob('*.response.bin'))
            self.assertTrue(originals)
            database = Path(daily['database_path'])
            before = database.read_bytes()
            source = originals[0]
            source.write_bytes(source.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                collect(**collection, execute=True)
            self.assertEqual(requests, ['RSS'])
            self.assertEqual(len(calls), 1)
            self.assertEqual(database.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

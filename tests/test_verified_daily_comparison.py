import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data import verified_daily_comparison as reader
from api.verified_daily_comparison import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


class VerifiedDailyComparisonTests(unittest.TestCase):
    def test_saved_evidence_and_read_only_route(self):
        result = reader.read_verified_daily_comparison()
        self.assertEqual(result['status'], 'AVAILABLE')
        self.assertEqual(len(result['columns']), 5)
        self.assertEqual(result['columns'][-1]['arm'],'latch')
        self.assertFalse(result['automatic_promotion'])
        self.assertAlmostEqual(result['columns'][2]['cagr'], 1.3820632608829402)
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        self.assertEqual(client.get('/api/verified_daily_comparison').json(), result)
        self.assertEqual(client.post('/api/verified_daily_comparison').status_code, 405)

    def test_missing_or_bad_report_or_review_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(reader.read_verified_daily_comparison(root)['status'], 'UNAVAILABLE')
        for name in ('REPORT_SHA', 'REVIEW_SHA'):
            with patch.object(reader, name, '0' * 64):
                self.assertEqual(reader.read_verified_daily_comparison()['status'], 'UNAVAILABLE')

    def test_report_sources_verified_after_manifest_hash(self):
        # Build a minimal isolated evidence tree; never mutate sealed research artifacts.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / reader.REPORT
            review_path = root / reader.REVIEW
            report_path.parent.mkdir(parents=True)
            review_path.parent.mkdir(parents=True)
            review_path.write_bytes((reader.ROOT / reader.REVIEW).read_bytes())
            report = json.loads((reader.ROOT / reader.REPORT).read_bytes())
            source = root / 'source.json'
            source.write_bytes(b'original')
            review=json.loads(review_path.read_bytes())
            candidate_path='tmp/monthly_latched_sma20_exit_20261016_v1/outcome.json'
            candidate=root/candidate_path;candidate.write_bytes((reader.ROOT/candidate_path).read_bytes())
            report['source_hashes'] = {'source.json': hashlib.sha256(b'original').hexdigest(),candidate_path:review['outcome_sha256']}
            report_path.write_text(json.dumps(report), encoding='utf-8')
            digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
            with patch.object(reader, 'REPORT_SHA', digest):
                self.assertEqual(reader.read_verified_daily_comparison(root)['status'], 'AVAILABLE')
                source.write_bytes(b'changed')
                self.assertEqual(reader.read_verified_daily_comparison(root)['status'], 'UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()

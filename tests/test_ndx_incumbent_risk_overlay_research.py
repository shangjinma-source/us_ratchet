import csv
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import yaml

from backtest.ndx_incumbent_risk_overlay_research import load_incumbent_risk_overlay as load
from backtest import ndx_incumbent_risk_overlay_research as overlay


class IncumbentRiskOverlayTests(unittest.TestCase):
    def execute(self, *, missing=False, duplicate=False, late=False, drift=False, wrong_hash=False, poison=None):
        base = Path('synthetic_overlay_test').resolve()
        reviewed = base/'reviewed'
        files = {}
        def publish(path, raw):
            files[path] = raw
            return hashlib.sha256(raw).hexdigest()
        def encoded(value):
            return json.dumps(value).encode()
        def table(records):
            stream = io.StringIO()
            fields = list(records[0]) if records else ['ticker']
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader();writer.writerows(records)
            return stream.getvalue().encode()
        available = '2023-01-01' if late else '2019-01-01'
        coverage = dict(ticker='A', security_id='security:A', issuer_id='issuer:A', risk_chain='memory',
            confidence='high', effective_from=available, effective_to='', evidence_available_date=available,
            status='accepted', evidence_locator='https://example.org/filing', accession_number='one')
        excerpt = 'Synthetic business evidence.'
        excerpt_hash = hashlib.sha256(excerpt.encode()).hexdigest()
        raw_path, sidecar_path = base/'raw.html', base/'raw.json'
        raw_hash = publish(raw_path, b'synthetic raw filing')
        sidecar_hash = publish(sidecar_path, encoded(dict(content_sha256=raw_hash, evidence_available_date=available)))
        evidence = dict(coverage, evidence_id='evidence:A', evidence_excerpt=excerpt)
        document = dict(ticker='A', security_id='security:A', issuer_id='issuer:A', accession_number='one',
            evidence_available_date=available, document_url=coverage['evidence_locator'], raw_manifest_verified='True',
            raw_path=str(raw_path), raw_manifest_path=str(sidecar_path), raw_sha256=raw_hash,
            raw_manifest_sha256=sidecar_hash, business_excerpt=excerpt, business_excerpt_sha256=excerpt_hash)
        decision = dict(ticker='A', security_id='security:A', issuer_id='issuer:A', risk_chain='memory',
            confidence='high', status='accepted', evidence_id='evidence:A', expected_accession_number='one',
            effective_from='evidence_available_date', effective_to='', expected_raw_sha256=raw_hash,
            expected_excerpt_sha256=excerpt_hash)
        coverage_rows = [] if missing else [coverage, coverage] if duplicate else [coverage]
        artifacts = {}
        for key, filename, raw in (
            ('coverage', 'coverage.csv', table(coverage_rows)),
            ('evidence_reviewed', 'evidence.csv', table([evidence])),
            ('decision_snapshot', 'decision.yaml', yaml.safe_dump({'decisions': [decision]}).encode())):
            if key == 'coverage' and poison == 'csv_header':
                raw = b'ticker,ticker\nA,A\n'
            if key == 'coverage' and poison == 'csv_width':
                raw = b'ticker,risk_chain\nA\n'
            if key == 'decision_snapshot' and poison == 'yaml_key':
                raw = b'decisions: []\ndecisions: []\n'
            artifacts[key] = dict(filename=filename, sha256=publish(reviewed/filename, raw))
        document_hash = publish(base/'review_documents.csv', table([document]))
        source_hash = publish(reviewed/'fetch_manifest_snapshot.json', b'{}')
        manifest = dict(manifest_type='ndx_incumbent_overlay_reviewed_bundle',
            classification_status='accepted_evidence_applied', artifacts=artifacts,
            decision_registry_sha256=artifacts['decision_snapshot']['sha256'],
            source_overlay_manifest_sha256=source_hash,
            summary={'input_versions': {'documents': {'content_sha256': document_hash}}})
        manifest_path = reviewed/'manifest.json'
        manifest_raw = encoded(manifest)
        if poison == 'json_key':
            manifest_raw = b'{"same":1,"same":2}'
        digest = publish(manifest_path, manifest_raw)
        reads = {}
        original_read = Path.read_bytes
        def read(path):
            if path == overlay._SOURCE:
                return original_read(path)
            reads[path] = reads.get(path, 0) + 1
            return files[path] + (b' ' if drift and path == raw_path and reads[path] > 1 else b'')
        with patch.object(Path, 'read_bytes', read):
            return load(reviewed_manifest_path=manifest_path, expected_manifest_sha256='0'*64 if wrong_hash else digest,
                        tickers=['A'], date_start='2022-01-12', date_end='2023-03-31')

    def test_bound_historical_evidence_not_external_authentication(self):
        result = self.execute()
        self.assertEqual(result['risk_chain_by_ticker'], {'A': 'memory'})
        self.assertFalse(result['provenance']['external_point_in_time_authenticity_verified'])
        self.assertFalse(result['provenance']['annual_revalidation_verified'])
        self.assertEqual(len(result['provenance']['source_hashes']), 9)

    def test_missing_coverage_rejected(self):
        with self.assertRaisesRegex(ValueError, 'coverage or uniqueness'):
            self.execute(missing=True)

    def test_duplicate_ticker_rejected(self):
        with self.assertRaisesRegex(ValueError, 'coverage or uniqueness'):
            self.execute(duplicate=True)

    def test_late_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError, 'does not cover'):
            self.execute(late=True)

    def test_raw_source_changed_at_end_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Source changed during'):
            self.execute(drift=True)

    def test_wrong_manifest_hash_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Source digest differs'):
            self.execute(wrong_hash=True)

    def test_duplicate_serialized_keys_and_bad_csv_width_rejected(self):
        for poison in ('csv_header', 'csv_width', 'yaml_key', 'json_key'):
            with self.subTest(poison=poison), self.assertRaises(ValueError):
                self.execute(poison=poison)

    def test_loader_source_mismatch_rejected(self):
        with patch.object(overlay, '_LOADED_SOURCE_SHA256', '0'*64), self.assertRaisesRegex(ValueError, 'Source digest differs'):
            self.execute()


if __name__ == '__main__':
    unittest.main()

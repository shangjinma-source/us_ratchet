import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('quote_audit', ROOT/'scripts/ndx_current_quote_observation_independent_audit_20260923.py')
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


class ObservationAuditTests(unittest.TestCase):
    def fixture(self):
        path = audit.BASE/audit.NEW[0]/'manifest.json'
        manifest = json.loads(path.read_bytes())
        raw = Path(manifest['request']['raw_path']).read_bytes()
        return path, manifest, raw

    def test_real_both_raws_complete_and_no_http(self):
        value = audit.build()
        self.assertEqual([d['security_count'] for d in value['details']], [101, 101])
        self.assertFalse(value['point_in_time_membership_verified'])

    def test_rewritten_raw_denominator_and_duplicate_key_rejected(self):
        path, manifest, raw = self.fixture()
        for mutation in ('bool_offset', 'duplicate_symbol', 'duplicate_key'):
            payload = json.loads(raw)
            if mutation == 'bool_offset': payload['data']['offset'] = False
            if mutation == 'duplicate_symbol': payload['data']['data']['rows'][1]['symbol'] = payload['data']['data']['rows'][0]['symbol']
            changed = json.dumps(payload).encode()
            if mutation == 'duplicate_key': changed = changed.replace(b'"offset": 0', b'"offset": 0, "offset": 0')
            receipt = copy.deepcopy(manifest)
            receipt['request'].update(raw_bytes=len(changed), raw_sha256=audit.sha(changed))
            receipt['request']['headers']['Content-Length'] = str(len(changed))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                audit.inspect(changed, receipt, path)

    def test_receipt_scope_url_and_time_rejected(self):
        path, manifest, raw = self.fixture()
        for key, value in [('final_url', 'https://example.com/api'), ('status', True), ('received_at_utc', '2026-09-22T21:57:36')]:
            changed = copy.deepcopy(manifest); changed['request'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): audit.inspect(raw, changed, path)
        changed = copy.deepcopy(manifest); changed['promotion_allowed'] = 0
        with self.assertRaises(ValueError): audit.inspect(raw, changed, path)

    def test_publisher_rejects_resigned_scope(self):
        valid = dict(schema='test', promotion_allowed=False)
        with patch.object(audit, 'build', return_value=valid):
            with self.assertRaises(ValueError):
                audit.publish_verified('not-created.json', dict(valid, promotion_allowed=True))


if __name__ == '__main__': unittest.main()

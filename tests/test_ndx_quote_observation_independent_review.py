import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_ndx_current_quote_observation_independent_audit_20260923 as owner

m = owner.audit


class IndependentReview(unittest.TestCase):
    def test_nonfinite_exponents_and_duplicate_nested_keys(self):
        for raw in (b'{"x":1e999}', b'{"x":-1e999}', b'{"x":{"a":1,"a":2}}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                m.strict_json(raw)

    def test_reversed_receipt_and_ambiguous_header(self):
        path = m.BASE / m.NEW[0] / 'manifest.json'
        manifest = json.loads(path.read_bytes())
        raw = Path(manifest['request']['raw_path']).read_bytes()
        for mode in ('clock', 'header'):
            changed = copy.deepcopy(manifest)
            if mode == 'clock':
                changed['request']['started_at_utc'] = '2099-01-01T00:00:00+00:00'
            else:
                changed['request']['headers']['content-type'] = 'application/json'
                changed['request']['headers']['Content-Type'] = 'application/json'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                m.inspect(raw, changed, path)

    def test_atomic_publication_does_not_leave_target_or_overwrite(self):
        value = {'source_hashes': {}, 'promotion_allowed': False}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audit.json'
            with patch.object(m, 'build', return_value=value), patch.object(m.os, 'link', side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):
                    m.publish_verified(path, value)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])
            path.write_bytes(b'original')
            with patch.object(m, 'build', return_value=value):
                with self.assertRaises(FileExistsError):
                    m.publish_verified(path, value)
            self.assertEqual(path.read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()

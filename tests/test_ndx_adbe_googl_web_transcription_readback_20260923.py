import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/ndx_adbe_googl_web_transcription_readback_20260923.py'
spec = importlib.util.spec_from_file_location('two_web_readback', SOURCE)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class ReadbackTests(unittest.TestCase):
    def row(self, ticker='GOOGL'):
        return json.loads((reader.BASE / (ticker + '.json')).read_bytes())

    def test_actual_sources_and_cover_readback(self):
        value = reader.build()
        self.assertEqual(value['security_count'], 2)
        self.assertEqual(value['raw_http_original_verified_count'], 0)
        self.assertTrue(all(value[k] is False for k in reader.FLAGS))

    def test_class_c_and_reporter_substitution(self):
        for key, value in [('cusip', '02079K107'), ('security_class', 'Class C Capital Stock'),
                           ('subject_cik', '0001364742')]:
            row = self.row(); row[key] = value
            with self.assertRaises(ValueError): reader.inspect(row)

    def test_promotion_and_fabricated_clock(self):
        for key in reader.FLAGS:
            row = self.row(); row[key] = True
            with self.assertRaises(ValueError): reader.inspect(row)
        row = self.row(); row['tool_call_started_utc'] = '2026-09-23T04:00:00Z'
        with self.assertRaises(ValueError): reader.inspect(row)

    def test_wrong_cover_context_cannot_bridge_share_classes(self):
        row = self.row()
        raw = Path(row['cover_reference']['path']).read_bytes()
        row['cover_context'] = 'i16fd1186b22d4dc4955e3956b71fc8a4_D20210101-20211231'
        with self.assertRaises(ValueError): reader.parse_cover(raw, row)

    def test_changed_tool_locator_rejected_by_external_artifact_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for ticker in reader.ARTIFACTS:
                row = self.row(ticker)
                row['tool_reference'] = 'invented'
                (base / (ticker + '.json')).write_text(json.dumps(row), encoding='utf8')
            with patch.object(reader, 'BASE', base), self.assertRaises(ValueError):
                reader.build()

    def test_loaded_source_lock(self):
        with patch.object(reader, 'LOADED_SHA', '0' * 64), self.assertRaises(ValueError):
            reader.build()


if __name__ == '__main__':
    unittest.main()

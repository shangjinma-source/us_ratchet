"""Offline V2 review: synthetic bytes and temporary namespaces only."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_forward_network_saved_diagnostic_20261003 import inputs, m, core
from test_ndx_sina_saved_day_response_research import fixture, raw


class SavedResponseReview(unittest.TestCase):
    def test_exact_banner_never_general_comment_stripping(self):
        body, baseline, rows = fixture()
        source = core.EXACT_BANNER + body
        out = core.inspect_response(raw_bytes=source, ticker='QQQ', baseline_csv_bytes=baseline)
        self.assertEqual(out['raw_sha256'], core.sha(source))
        self.assertEqual(out['parsing_bytes_sha256'], core.sha(source[out['parsing_byte_offset']:]))
        for modified in (b' ' + source, core.EXACT_BANNER.replace(b'\n', b'\r\n') + body,
                         source+b'alert(1);', core.EXACT_BANNER+body.replace(b'QQQ_day', b'SPY_day')):
            with self.subTest(prefix=modified[:50]), self.assertRaises(ValueError):
                core.inspect_response(raw_bytes=modified, ticker='QQQ', baseline_csv_bytes=baseline)
        rows.pop()
        out = core.inspect_response(raw_bytes=core.EXACT_BANNER+raw(rows), ticker='QQQ', baseline_csv_bytes=baseline)
        self.assertEqual(out['new_provider_sessions'], [])
        self.assertIsNone(out['target_row'])
        self.assertIs(out['exact_single_new_target'], False)
        self.assertTrue(all(out[k] is False for k in core.FLAGS))

    def test_original_transport_flags_clock_and_ticker_binding(self):
        for mode in ('boolattempt', 'clock', 'ticker', 'parentauthority'):
            docs, refs = inputs()
            key = 'started' if mode == 'parentauthority' else 'receipt_SPY'
            saved = json.loads(docs[key])
            if mode == 'boolattempt': saved['network_attempt_count'] = True
            elif mode == 'clock': saved['started_at_utc'] = '2026-10-02T20:00:00+00:00'
            elif mode == 'ticker': saved['ticker'] = 'QQQ'
            else: saved['fresh_observation'] = 0
            docs[key] = m.encode(saved)
            with self.subTest(mode=mode), self.assertRaises(ValueError): m.validate(docs, refs)

    def test_offline_failure_preserves_parent_and_blocks_retry(self):
        docs, refs = inputs()
        original = dict(docs)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)/'new'
            with patch.object(m, 'OUTPUT', out), patch.object(m, 'load', return_value=(docs, refs, {}, core)), patch.object(m, 'guard', side_effect=ValueError('synthetic final source drift')):
                with self.assertRaises(ValueError): m.run(execute=True)
                self.assertTrue((out/'started.json').is_file())
                self.assertTrue((out/'diagnostic.json').is_file())
                self.assertTrue((out/'failure.json').is_file())
                with self.assertRaises(ValueError): m.run(execute=True)
        self.assertEqual(docs, original)
        tree = ast.parse(Path(m.__file__).read_text(encoding='utf-8-sig'))
        names = {a.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names}
        names.update(node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
        self.assertTrue(names.isdisjoint({'urllib', 'requests', 'httpx', 'socket', 'subprocess'}))


if __name__ == '__main__': unittest.main()

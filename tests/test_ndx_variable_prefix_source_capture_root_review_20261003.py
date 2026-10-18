"""Check immutable evidence lifetime separately from mutable capture-time cache."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_variable_prefix_source_capture_20261003 as writer
from test_ndx_variable_prefix_capture_research import fixture


class RootReview(unittest.TestCase):
    def exercise(self, change_during_capture=False):
        arguments = fixture()
        raw = {key: (writer.ROOT / relative).read_bytes()
               for key, (relative, _) in writer.PINS.items() if key != 'tzif'}
        core = writer.private_core(raw)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'capture'
            caches = {ticker: root / (ticker + '.csv') for ticker in ('QQQ', 'SPY')}
            for ticker, path in caches.items():
                path.write_bytes(arguments['source_bytes'][ticker])
            state = (arguments['parent'], {}, {}, {'tzif': arguments['tzif_bytes']},
                     arguments['baseline_bytes'], {}, core)
            original_save = writer.save_bytes

            def save(path, content):
                result = original_save(path, content)
                if change_during_capture and path == output / 'SPY.csv':
                    caches['QQQ'].write_bytes(b'normal concurrent cache refresh')
                return result

            with patch.object(writer, 'OUTPUT', output), patch.object(writer, 'CURRENT', caches), \
                 patch.object(writer, 'load', return_value=state), \
                 patch.object(writer, 'resource_gate'), \
                 patch.object(writer, 'now', side_effect=[arguments['capture_started_at'], arguments['capture_completed_at']]), \
                 patch.object(writer, 'save_bytes', side_effect=save):
                if change_during_capture:
                    with self.assertRaisesRegex(ValueError, 'drift'):
                        writer.run(execute=True)
                    self.assertTrue((output / 'failure.json').is_file())
                    self.assertEqual((output / 'QQQ.csv').read_bytes(), arguments['source_bytes']['QQQ'])
                    return
                result = writer.run(execute=True)
                capture = writer.loads(Path(result['capture_reference']['path']).read_bytes())
                for ticker, path in caches.items():
                    self.assertNotIn(str(path), capture['source_hashes'])
                    self.assertEqual(capture['current_cache_references'][ticker]['sha256'],
                                     writer.sha(arguments['source_bytes'][ticker]))
                    path.write_bytes(b'later normal cache refresh')
                # The permanent snapshot closure must remain verifiable after normal refresh.
                writer.guard(capture['source_hashes'])
                self.assertFalse(capture['observation_created'])

    def test_later_refresh_does_not_invalidate_saved_capture_sources(self):
        self.exercise()

    def test_concurrent_refresh_still_fails_and_preserves_saved_bytes(self):
        self.exercise(change_during_capture=True)

    def test_parent_mutable_claim_is_rejected_not_silently_discarded(self):
        path = writer.CURRENT['QQQ']
        claims = {str(path.parent / '.' / path.name): 'a' * 64}
        before = dict(claims)
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_PARENT_LIVE_CACHE_SOURCE_CLAIM'):
            writer.reject_live_claims(claims)
        self.assertEqual(claims, before)


if __name__ == '__main__':
    unittest.main()

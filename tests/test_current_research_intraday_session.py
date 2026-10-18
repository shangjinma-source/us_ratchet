import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from data.current_research_intraday_session import load_intraday_market_session


class SessionTests(unittest.TestCase):
    def fixture(self, root, offset='-04:00'):
        root = Path(root)
        (root / 'evidence.json').write_bytes(b'{"scheduled":true}')
        evidence = {'evidence.json': sha256((root / 'evidence.json').read_bytes()).hexdigest()}
        artifact = dict(schema='SCHEDULED_REGULAR_SESSIONS_V1', source_hashes=evidence,
                        calendar=['2026-10-14'], sessions=[dict(date='2026-10-14', timezone='America/New_York',
                        open_at='2026-10-14T09:30:00'+offset, close_at='2026-10-14T16:00:00'+offset)])
        (root / 'calendar.json').write_text(json.dumps(artifact), encoding='utf-8')
        return dict(root=root, calendar_path='calendar.json', source_hashes={**evidence,
                    'calendar.json': sha256((root / 'calendar.json').read_bytes()).hexdigest()},
                    now=datetime.fromisoformat('2026-10-14T19:30:00+00:00'))

    def test_actual_clock_timezone_and_open_close_boundaries(self):
        with tempfile.TemporaryDirectory() as root:
            args = self.fixture(root)
            value = load_intraday_market_session(**args)
            self.assertEqual(value['market_session']['date'], '2026-10-14')
            self.assertFalse(value['actual_market_open_certified'])
            args['now'] = datetime.fromisoformat('2026-10-14T13:30:00+00:00')
            self.assertTrue(load_intraday_market_session(**args)['local_source_bytes_verified'])
            for stamp in ['2026-10-14T13:29:59+00:00','2026-10-14T20:00:00+00:00','2026-10-15T15:00:00+00:00']:
                with self.assertRaises(ValueError):
                    load_intraday_market_session(**dict(args, now=datetime.fromisoformat(stamp)))

    def test_source_tampering_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            args = self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'CALENDAR_EVIDENCE_UNBOUND'):
                load_intraday_market_session(**dict(args, source_hashes={'calendar.json':args['source_hashes']['calendar.json']}))
            (Path(root) / 'evidence.json').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'CALENDAR_SOURCE_CHANGED'):
                load_intraday_market_session(**args)

    def test_wrong_dst_offset_rejected_even_with_matching_hashes(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, 'INVALID_SESSION_TIMES'):
                load_intraday_market_session(**self.fixture(root, '-05:00'))

    def test_unbound_session_reference_cannot_be_relabelled(self):
        with tempfile.TemporaryDirectory() as root:
            for addition in [{'source':'unbound'}, {'source_references':['unbound']}]:
                args = self.fixture(root)
                path = Path(root) / 'calendar.json'
                artifact = json.loads(path.read_bytes())
                artifact['sessions'][0].update(addition)
                path.write_text(json.dumps(artifact), encoding='utf-8')
                args['source_hashes']['calendar.json'] = sha256(path.read_bytes()).hexdigest()
                with self.assertRaisesRegex(ValueError, 'SESSION_SOURCE_UNBOUND'):
                    load_intraday_market_session(**args)


if __name__ == '__main__':
    unittest.main()

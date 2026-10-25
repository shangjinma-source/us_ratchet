"""Independent deadline check at the final route-write boundary."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import publish_registered_paper_monthly_route as publisher


class PublicationDeadlineTests(unittest.TestCase):
    def test_deadline_reached_after_lock_preserves_failure_without_route(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / 'routes' / '2026-11'
            deadline = datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc)
            before = deadline - timedelta(seconds=1)
            ticks = iter([before, before, before, before, deadline])
            checked = dict(
                output=output, saved={'revision': 'fixed'},
                bound={'validated_revision': 'fixed'}, deadline=deadline,
                input_hashes={}, route={'fixture': True},
                validated={'documents': {'daily': {}}},
            )
            with patch.object(publisher, '_check', return_value=checked), patch.object(
                publisher.binder, 'publication_guard', return_value=nullcontext()
            ):
                with self.assertRaisesRegex(ValueError, 'PUBLICATION_WINDOW_MISSED'):
                    publisher.run(
                        root=root, registration_directory='registration',
                        expected_request_sha256='a' * 64,
                        policy_path='policy.json', expected_policy_sha256='b' * 64,
                        target_month='2026-11', execute=True,
                        clock=lambda: next(ticks),
                    )
            self.assertTrue((output / 'started.json').is_file())
            self.assertTrue((output / 'failed.json').is_file())
            self.assertFalse((output / 'route.json').exists())
            self.assertFalse((output / 'complete.json').exists())
            self.assertFalse((root / publisher.registrar.LOCK).exists())


if __name__ == '__main__':
    unittest.main()

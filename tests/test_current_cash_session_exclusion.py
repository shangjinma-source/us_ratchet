from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources


class SessionExclusionTests(unittest.TestCase):
    def test_outside_window_revokes_previous_capture_without_sources_or_io(self):
        with TemporaryDirectory() as folder:
            for value in ('2026-10-16T13:29:59+00:00','2026-10-16T20:00:00+00:00',
                          '2026-10-17T15:00:00+00:00','2026-10-18T15:00:00+00:00',
                          '2026-11-02T14:29:59+00:00','2026-11-02T21:00:00+00:00'):
                with self.subTest(clock=value):
                    source=CurrentQuantityV2CurrentCashSources(root=folder,snapshot_service=None,server_account_id='isolated',
                        clock=lambda:datetime.fromisoformat(value),fetch=lambda *_:self.fail('No quote fetch'),audit_storage_root=Path(folder)/'audit')
                    source._current={'old':'capture'}
                    with patch.object(source,'_base',side_effect=AssertionError('No source load')):
                        with self.assertRaisesRegex(ValueError,'OUTSIDE_REGULAR_SESSION'):source.capture('prior-decision')
                    self.assertIsNone(source._current);self.assertEqual(source._attempt,1)
                    self.assertFalse((Path(folder)/'audit').exists())

    def test_inside_window_only_continues_original_validation(self):
        with TemporaryDirectory() as folder:
            for value in ('2026-10-16T13:30:00+00:00','2026-10-16T19:59:59+00:00',
                          '2026-11-02T14:30:00+00:00','2026-11-02T20:59:59+00:00',
                          '2026-12-25T15:00:00+00:00'):
                with self.subTest(clock=value):
                    source=CurrentQuantityV2CurrentCashSources(root=folder,snapshot_service=None,server_account_id='isolated',
                        clock=lambda:datetime.fromisoformat(value),fetch=lambda *_:self.fail('No quote fetch'))
                    with patch.object(source,'_base',side_effect=ValueError('ORIGINAL_SOURCE_GATE')) as original:
                        with self.assertRaisesRegex(ValueError,'ORIGINAL_SOURCE_GATE'):source.capture('decision')
                        original.assert_called_once_with('decision')


if __name__=='__main__':unittest.main()

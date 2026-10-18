"""Independent transaction-boundary regression for slow continuation sources."""
import unittest
from datetime import timedelta
from tempfile import TemporaryDirectory

from test_current_quantity_v2_continuation_service import fixture


class ContinuationFinalClockTests(unittest.TestCase):
    def test_expiry_after_source_validation_rolls_back_acceptance(self):
        with TemporaryDirectory() as folder:
            paper, bridge, _, clock, closed = fixture(folder)
            proposal = bridge.preview(
                account_id=closed['account_id'], expected_revision=closed['revision'])
            before = paper.store.read(closed['account_id'])
            times = iter((clock[0], clock[0] + timedelta(minutes=3)))
            paper.clock = lambda: next(times)
            request = dict(account_id=closed['account_id'],
                           proposal_id=proposal['proposal_id'],
                           operation_id='slow-source-final-clock',
                           expected_revision=closed['revision'])
            with self.assertRaises(ValueError):
                paper.accept_continuation(**request)
            self.assertEqual(paper.store.read(closed['account_id']), before)
            # A rollback must not consume the operation ID or create a reservation.
            # This injected test clock returns to the original instant; no real
            # expired market reference is reused.
            paper.clock = lambda: clock[0]
            accepted = paper.accept_continuation(**request)
            self.assertEqual(accepted['cash'], closed['cash'])
            self.assertEqual(accepted['shares'], closed['shares'])
            self.assertNotEqual(accepted['revision'], closed['revision'])


if __name__ == '__main__':
    unittest.main()

"""Real-store callback races and monotonic clock boundaries; no live accounts."""
from datetime import timedelta
from tempfile import TemporaryDirectory
import unittest

import test_registered_paper_settlement_runtime as fixtures
from backtest.registered_paper_settlement_runtime import finalize_registered_paper
from backtest.current_quantity_v2_simulated_settlement import record_close
from data.current_quantity_v2_minute_close_marks import build_marks


class SettlementConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.FinalSettlementTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.FinalSettlementTests.tearDownClass()

    def test_clock_rollback_after_capture_arguments_blocks_before_fetch(self):
        with TemporaryDirectory() as folder:
            args, captures, _, clock = fixtures.FinalSettlementTests().setup_final(folder)
            original = args['capture_arguments']
            before = args['store'].path.read_bytes()

            def rollback(state, day):
                options = original(state, day)
                clock[0] -= timedelta(seconds=1)
                return options

            args['capture_arguments'] = rollback
            with self.assertRaisesRegex(ValueError, 'SETTLEMENT_CLOCK_ROLLBACK'):
                finalize_registered_paper(**args)
            self.assertEqual(captures, [])
            self.assertEqual(before, args['store'].path.read_bytes())

    def test_concurrent_revision_after_settlement_blocks_close_write(self):
        with TemporaryDirectory() as folder:
            args, _, _, clock = fixtures.FinalSettlementTests().setup_final(folder)
            original = args['close_arguments']
            store = args['store']

            def competing_write(state, day):
                supplied = original(state, day)
                current = store.read(args['simulation_id'])
                observed = clock[0].isoformat()
                close = state['valuation']['registration']['calendar']['closes'][day]
                marks = build_marks(chain=state['chain'], session=day,
                                    session_close=close, observed_at=observed,
                                    **supplied)['marks']
                store.apply(simulation_id=args['simulation_id'],
                            expected_revision=current['revision'],
                            operation_id='isolated-concurrent-close',
                            request={'kind': 'ISOLATED_TEST_CLOSE'},
                            transform=lambda value: record_close(simulation=value,
                                session=day, marks=marks, observed_at=observed))
                return supplied

            args['close_arguments'] = competing_write
            with self.assertRaisesRegex(ValueError, 'STALE_SIMULATION_REVISION'):
                finalize_registered_paper(**args)
            current = store.read(args['simulation_id'])
            self.assertEqual(len(current['simulation']['valuation']['records']), 1)
            self.assertTrue(all(order['closed'] == 'FILLED'
                                for order in current['simulation']['chain']['ledger']['orders'].values()))


if __name__ == '__main__':
    unittest.main()

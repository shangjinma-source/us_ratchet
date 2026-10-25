from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.monthly_peak_exit_store import MonthlyPeakExitStore


class PeakExitStoreTests(unittest.TestCase):
    def observation(self, day, close, digest='a'):
        return dict(decision_date='2026-10-01', session_date=day,
                    closes={'SNDK': close}, unit_ids={'SNDK': 'nominal-v1'},
                    evidence_sha256=digest * 64)

    def test_restart_and_failed_batch_rollback(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'risk.sqlite'
            def run(previous, rows):
                return MonthlyPeakExitStore(path).advance(account_id='test',
                    expected_previous_session=previous, observations=rows,
                    baseline_targets={'SNDK': 13})
            run(None, [self.observation('2026-10-01', '100')])
            with self.assertRaises(ValueError):
                run('2026-10-01', [self.observation('2026-10-02', '80'),
                                   self.observation('2026-10-02', '90', 'b')])
            # The failed batch must not leave the first observation committed.
            result = run('2026-10-01', [self.observation('2026-10-02', '90')])
            self.assertEqual(result['effective_target_quantities']['SNDK'], 13)
            run('2026-10-02', [self.observation('2026-10-05', '80')])
            result = run('2026-10-05', [self.observation('2026-10-06', '120')])
            self.assertEqual(result['effective_target_quantities']['SNDK'], 0)

    def test_concurrent_stale_writer_cannot_overwrite(self):
        with TemporaryDirectory() as directory:
            store = MonthlyPeakExitStore(Path(directory) / 'risk.sqlite')
            def run():
                try:
                    store.advance(account_id='test', expected_previous_session=None,
                        observations=[self.observation('2026-10-01', '100')],
                        baseline_targets={'SNDK': 13})
                    return 'COMMITTED'
                except ValueError as error:
                    return str(error)
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda _: run(), range(2)))
            self.assertCountEqual(outcomes, ['COMMITTED', 'RISK_STATE_CHANGED_RELOAD'])

    def test_new_security_replays_history_and_preserves_old_exit(self):
        with TemporaryDirectory() as directory:
            store = MonthlyPeakExitStore(Path(directory) / 'risk.sqlite')
            old = [self.observation('2026-10-01', '100'),
                   self.observation('2026-10-02', '80'),
                   self.observation('2026-10-05', '110')]
            store.advance(account_id='test', expected_previous_session=None,
                observations=old, baseline_targets={'SNDK': 13})
            expanded = []
            for row, price in zip(old, ['200', '150', '210']):
                expanded.append(dict(row, closes=dict(row['closes'], MRNA=price),
                    unit_ids=dict(row['unit_ids'], MRNA='nominal-v1'),
                    evidence_sha256='b'*64))
            result = store.advance(account_id='test', expected_previous_session='2026-10-05',
                observations=expanded, baseline_targets={'SNDK': 20, 'MRNA': 30})
            self.assertEqual(result['effective_target_quantities'], {'SNDK': 0, 'MRNA': 0})
            with self.assertRaisesRegex(ValueError, 'RISK_RECORDED_PRICE_CHANGED'):
                changed = dict(expanded[0], closes={'SNDK': '101', 'MRNA': '200'},
                               evidence_sha256='b'*64)
                store.advance(account_id='test', expected_previous_session='2026-10-05',
                    observations=[changed]+expanded[1:], baseline_targets={'SNDK': 20, 'MRNA': 30})
            result = store.advance(account_id='test', expected_previous_session='2026-10-05',
                observations=expanded, baseline_targets={'SNDK': 20, 'MRNA': 30})
            self.assertEqual(result['state']['exited'], ['MRNA', 'SNDK'])

    def test_balance_refresh_cannot_change_monthly_epoch(self):
        with TemporaryDirectory() as directory:
            store = MonthlyPeakExitStore(Path(directory) / 'risk.sqlite')
            store.advance(account_id='test', expected_previous_session=None,
                observations=[self.observation('2026-10-01', '100'),
                              self.observation('2026-10-02', '80')],
                baseline_targets={'SNDK': 13})
            row = dict(self.observation('2026-10-05', '110'), decision_date='2026-10-05')
            with self.assertRaisesRegex(ValueError, 'RESET_AUTHORIZATION'):
                store.advance(account_id='test', expected_previous_session='2026-10-02',
                    observations=[row], baseline_targets={'SNDK': 30})
            reset = dict(self.observation('2026-11-02', '110'), decision_date='2026-11-02')
            result = store.advance(account_id='test', expected_previous_session='2026-10-02',
                observations=[reset], baseline_targets={'SNDK': 13},
                authorized_monthly_reset='2026-11-02')
            self.assertEqual(result['effective_target_quantities'], {'SNDK': 13})


if __name__ == '__main__':
    unittest.main()

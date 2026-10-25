"""Real registered bootstrap; scheduling seams isolate market capture timing."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from scripts.run_prospective_paper_v3 import run_scheduled, load_runner, SOURCE
import test_paper_runtime_initialization_v2 as fixture


def configured(folder):
    policy = canonical({'test_only': 'monthly-maintenance-boundary'})
    with patch.object(fixture, 'SOURCE', SOURCE):
        args = fixture.configured(folder, extra_sources={'runtime/chain.json': policy})
    path = Path(folder)/args['configuration_path']
    config = json.loads(path.read_bytes())
    config['selection_monthly_policy'] = dict(path='runtime/chain.json', sha256=sha256(policy).hexdigest())
    body = canonical(config)
    path.write_bytes(body)
    args['expected_sha256'] = sha256(body).hexdigest()
    return args


class ScheduledChainTests(unittest.TestCase):
    def test_maintenance_waits_until_outside_decision_window(self):
        with TemporaryDirectory() as folder:
            args = configured(folder)
            now = ['2026-11-03T14:59:30+00:00']
            args['clock'] = lambda:datetime.fromisoformat(now[0])
            with patch('scripts.run_prospective_paper_v3.maintain_monthly_chain',
                       return_value=dict(status='WAITING_SESSION_CLOSE', account_writes=False)) as monthly, \
                 patch('scripts.run_prospective_paper_v3.ProspectivePaperRunOnce.publish_monthly',
                       return_value=dict(status='MONTHLY_TARGET_ALREADY_PUBLISHED')) as publish, \
                 patch('scripts.run_prospective_paper_v3.ProspectivePaperRunOnce.run_once',
                       return_value=dict(status='TEST_DAILY')):
                self.assertEqual(run_scheduled(**args)['status'], 'WAIT_REGISTERED_START')
                self.assertFalse(list(Path(folder).rglob('book.sqlite3')))
                now[0] = '2026-11-03T15:00:10+00:00'
                self.assertEqual(run_scheduled(**args)['status'], 'TEST_DAILY')
                monthly.assert_not_called()
                publish.assert_called_once()
                book = load_runner(**args).coordinator.read()
                self.assertEqual(book['cash'], '20000')
                now[0] = '2026-11-03T15:02:00+00:00'
                result = run_scheduled(**args)
                self.assertEqual(result['monthly_maintenance']['status'], 'WAITING_SESSION_CLOSE')
                monthly.assert_called_once()
                self.assertTrue(monthly.call_args.kwargs['execute'])
                self.assertEqual(load_runner(**args).coordinator.read(), book)

    def test_policy_tamper_and_missed_start_do_not_initialize(self):
        with TemporaryDirectory() as folder:
            args = configured(folder)
            args['clock'] = lambda:datetime.fromisoformat('2026-11-03T15:02:00+00:00')
            with self.assertRaisesRegex(ValueError, 'MISSED_REGISTERED_START'):
                run_scheduled(**args)
            self.assertFalse(list(Path(folder).rglob('book.sqlite3')))
            (Path(folder)/'runtime/chain.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                run_scheduled(**args)
            self.assertFalse(list(Path(folder).rglob('book.sqlite3')))


if __name__ == '__main__':
    unittest.main()

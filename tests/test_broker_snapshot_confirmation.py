"""Bulk snapshot confirmation cannot overwrite an intervening broker edit."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from api.server import api_sync_broker_snapshot
from core.broker_account import save_broker_account, load_broker_account, validate_broker_account


class BrokerSnapshotConfirmationTests(unittest.TestCase):
    def test_preview_conflict_and_confirm_preserve_cash_and_strategy(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'broker.json'
            account = validate_broker_account(dict(snapshot_as_of='2026-10-15', deployable_cash_session_date='2026-10-15',
                deployable_cash_usd=20000, positions=[dict(ticker='MU', shares=3, average_cost=100, observed_price=100)]))
            save_broker_account(account, path)
            body = dict(mode='snapshot', text='ticker,shares,avg_price\nSNDK,2,1412')
            with patch('api.server.BROKER_ACCOUNT_PATH', path), patch('api.server.audit_log'), \
                    patch('api.server.load_portfolio', return_value=None), \
                    patch('api.server.save_portfolio', side_effect=AssertionError('strategy mutation')):
                original = path.read_bytes()
                preview = api_sync_broker_snapshot(dict(body, preview=True))
                self.assertEqual(path.read_bytes(), original)
                self.assertFalse(path.with_suffix('.json.bak').exists())
                self.assertEqual(next(d for d in preview['diff'] if d['ticker']=='MU')['status'], 'missing_in_import')
                self.assertEqual(api_sync_broker_snapshot(body).status_code, 409)
                self.assertEqual(api_sync_broker_snapshot(dict(body, preview='false')).status_code, 400)
                account['positions'][0]['shares'] = 4
                save_broker_account(account, path)
                changed = path.read_bytes()
                self.assertEqual(api_sync_broker_snapshot(dict(body,
                    expected_account_fingerprint=preview['account_fingerprint'])).status_code, 409)
                self.assertEqual(path.read_bytes(), changed)
                fresh = api_sync_broker_snapshot(dict(body, preview=True))
                result = api_sync_broker_snapshot(dict(body,
                    expected_account_fingerprint=fresh['account_fingerprint']))
                self.assertEqual(result['broker_snapshot_synced'][0]['ticker'], 'SNDK')
                self.assertEqual(path.with_suffix('.json.bak').read_bytes(), changed)
                saved = load_broker_account(path)
                self.assertEqual(saved['deployable_cash_usd'], 20000)
                self.assertEqual([p['ticker'] for p in saved['positions']], ['SNDK'])


if __name__ == '__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from data.broker_transfer_composition import attach_transfers


class TransferCompositionTests(unittest.TestCase):
    def test_mounted_roundtrip_leaves_strategy_account_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            account_path = root / 'data/strategy_account/real.sqlite3'
            account_path.parent.mkdir(parents=True)
            account_path.write_bytes(b'unchanged account fixture')
            account = SimpleNamespace(account_id='isolated', store=SimpleNamespace(path=account_path))
            permitted = [True]
            def gate():
                if not permitted[0]:
                    raise ValueError('SOURCE_CHANGED')
            prepared = dict(router=APIRouter(), roa_service=SimpleNamespace(account_service=account))
            mounted = attach_transfers(prepared=prepared, root=root, validate_sources=gate,
                clock=lambda: datetime(2026, 11, 15, tzinfo=timezone.utc))
            app = FastAPI(); app.include_router(mounted['router']); client = TestClient(app)
            url = '/api/strategy-account/internal-transfers'
            initial = client.get(url).json()
            body = dict(expected_revision=initial['state']['revision'], event=dict(
                event_id='s', transfer_id='t', kind='SENT', source='HSBC', destination='USMART',
                principal='100.25', fee='0', occurred_at='2026-11-14T00:00:00Z'))
            self.assertEqual(client.post(url, json=body).status_code, 200)
            self.assertEqual(client.get(url).json()['summary']['in_transit_usd'], '100.25')
            permitted[0] = False
            self.assertEqual(client.post(url, json=body).status_code, 422)
            self.assertEqual(account_path.read_bytes(), b'unchanged account fixture')
            permitted[0] = True
            self.assertEqual(len(client.get(url).json()['state']['events']), 1)
            with self.assertRaisesRegex(ValueError, 'TRANSFER_ROUTE_ALREADY_MOUNTED'):
                attach_transfers(prepared=mounted, root=root, validate_sources=gate)

    def test_outside_account_directory_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            account = SimpleNamespace(account_id='isolated', store=SimpleNamespace(path=root/'wrong.sqlite3'))
            with self.assertRaisesRegex(ValueError, 'TRANSFER_STORE_PATH_INVALID'):
                attach_transfers(prepared=dict(router=APIRouter(), roa_service=SimpleNamespace(account_service=account)),
                    root=root, validate_sources=lambda: None)
            self.assertEqual(list(root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()

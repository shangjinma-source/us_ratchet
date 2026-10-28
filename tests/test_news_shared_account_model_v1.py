"""Shared reservation regression against an explicitly selected candidate or release."""
from contextlib import closing
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from data.news_model_coordinator_v1 import ModelCoordinator


candidate = os.environ.get('NEWS_EVENT_ACCOUNT_MODEL_CANDIDATE')
if candidate:
    spec = importlib.util.spec_from_file_location('account_model_candidate', candidate)
    model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model)
else:
    from data import news_investment_model_v1 as model


@unittest.skipUnless(hasattr(model, 'SCHEMA_VERSION'), 'Shared budget candidate not released')
class AccountModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root/'investment_analysis'
        self.source = dict(id='s', title='Official', url='https://issuer', published_at='2026-10-28T10:00:00Z',
                           observed_at='2026-10-28T10:01:00Z', security_ids=['S'], tickers=['T'],
                           content_kind='FULL_TEXT', text='Complete.', text_sha256=sha256(b'Complete.').hexdigest())
        self.positions = [dict(security_id='S', ticker='T', original_qty=1, target_qty=2)]
        self.answer = dict(rows=[dict(security_id='S', ticker='T', action='ABSTAIN', reason='Evidence insufficient',
            buy_fraction='1/1', holding_fraction='1/1', counterevidence=[], uncertainty=[], evidence=[])])

    def call(self):
        return model.analyze_review([self.source], self.positions, self.cache)

    def test_busy_is_zero_attempt_and_success_cache_avoids_second_reservation(self):
        with ModelCoordinator(self.root).reserve('event'):
            result = self.call()
            self.assertEqual((result['status'], result['attempts']), ('DEFERRED', 0))
            self.assertFalse(list(self.cache.glob('*/receipt.json')))
        with closing(ModelCoordinator(self.root).connection()) as connection, connection:
            connection.execute('UPDATE reservations SET started=started-61')
        with patch.object(model, '_invoke', return_value=(self.answer, {})) as invoke:
            self.assertEqual(self.call()['status'], 'SUCCEEDED')
            receipt_path = next(self.cache.glob('*/receipt.json'))
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            receipt.pop('schema_sha256')  # An old receipt still receives current schema/quote validation.
            receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
            self.assertEqual(self.call()['status'], 'CACHED')
            self.assertEqual(invoke.call_count, 1)

    def test_input_save_failure_releases_reservation_and_no_inference(self):
        with patch.object(model, '_save', side_effect=OSError('fixture')), patch.object(model, '_invoke') as invoke:
            result = self.call()
        self.assertEqual(result['attempts'], 0)
        invoke.assert_not_called()
        with closing(ModelCoordinator(self.root).connection()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM reservations WHERE status='RUNNING'").fetchone()[0], 0)

    def test_old_deferred_migration_is_inside_reservation(self):
        with patch.object(model, '_invoke', return_value=(self.answer, {})):
            self.call()
        receipt_path = next(self.cache.glob('*/receipt.json'))
        receipt_path.write_text(json.dumps(dict(status='DEFERRED', attempts=0)), encoding='utf-8')
        with closing(ModelCoordinator(self.root).connection()) as connection, connection:
            connection.execute('UPDATE reservations SET started=started-61')
        with patch.object(model, '_invoke', return_value=(self.answer, {})) as invoke:
            self.assertEqual(self.call()['status'], 'SUCCEEDED')
            self.assertEqual(invoke.call_count, 1)
        self.assertTrue(receipt_path.with_name('deferred_receipt_migrated.json').exists())


if __name__ == '__main__':
    unittest.main()

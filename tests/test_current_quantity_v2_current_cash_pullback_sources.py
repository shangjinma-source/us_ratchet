from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta
from fractions import Fraction
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_current_quantity_v2_current_cash_sources import snapshot_fixture, month_config
from test_current_quantity_v2_pullback_sources import payload
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_current_cash_factory import create_services
from data.current_quantity_v2_pullback_cap_store import PullbackCapStore
from data.current_quantity_v2_current_cash_plan import build_current_cash_plan


POLICY = dict(schema='V2_PULLBACK_EXECUTION_POLICY_V1',
              status='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED',
              rebound_fraction='1/2', minimum_discount='1/200', maximum_age_seconds=120)


class CurrentCashPullbackSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshots, self.view = snapshot_fixture(self.root)
        self.current = datetime.fromisoformat('2026-10-15T09:32:17-04:00')
        self.database = self.root / 'cap.sqlite3'
        self.cap = PullbackCapStore(self.database, clock=lambda: self.current.isoformat(),
                                   max_history_rows=100, max_history_bytes=1000000)
        self.fetches = []

    def fetch(self, ticker):
        self.fetches.append(ticker)
        doc = payload()
        result = doc['chart']['result'][0]
        result['meta']['symbol'] = ticker
        result['meta']['regularMarketPrice'] = 10
        result['meta']['regularMarketTime'] = int(self.current.timestamp()) - 1
        result['indicators']['quote'][0] = dict(open=[9, 9.5, None], high=[10, 10, None],
            low=[8, 9.5, None], close=[9.5, 10, None], volume=[100, 100, 0])
        return json.dumps(doc).encode()

    def provider_arguments(self):
        return dict(root=self.root, snapshot_service=self.snapshots, server_account_id='paper-test',
                    fetch=self.fetch, clock=lambda: self.current,
                    execution_month_mandate=month_config(self.root))

    def row_count(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute('SELECT COUNT(*) FROM pullback_caps').fetchone()[0]

    def test_capture_freezes_two_proofs_and_resolve_does_not_write_or_fetch(self):
        policy = deepcopy(POLICY)
        source = CurrentQuantityV2CurrentCashSources(**self.provider_arguments(),
            pullback_policy=policy, pullback_cap_store=self.cap)
        policy['rebound_fraction'] = '1/4'
        source.capture(self.view['decision_id'])
        self.assertEqual(self.row_count(), 2)
        self.assertEqual(self.fetches, ['AAA', 'BBB'])
        with patch.object(self.cap, 'candidate', side_effect=AssertionError('resolve wrote cap')):
            supplied = source.resolve(self.view['decision_id'])
            self.assertEqual(source.resolve(self.view['decision_id']), supplied)
        documents = supplied['execution_package']['documents']
        self.assertEqual(set(documents['pullback_proofs']), {'A', 'B'})
        files = supplied['execution_package']['files']
        self.assertEqual(json.loads(files[documents['pullback_policy']]), POLICY)
        result = build_current_cash_plan(**supplied, now=self.current.isoformat())
        self.assertEqual(result['status'], 'READY', result)
        self.assertTrue(all(Fraction(row['limit_price']) == 9 for row in result['rows']))
        for sid, path in documents['pullback_proofs'].items():
            proof = json.loads(files[path])
            self.assertEqual(proof['parameters']['security_id'], sid)
            self.assertEqual(proof['ordinal'], 0)
        self.assertEqual(self.row_count(), 2)
        self.current += timedelta(minutes=2)
        with self.assertRaises(ValueError):
            source.resolve(self.view['decision_id'])
        self.assertEqual(self.row_count(), 2)

    def test_factory_forwards_explicit_store_without_capture_or_paper_db_creation(self):
        paper_path = self.root / 'paper.sqlite3'
        with patch.object(self.cap, 'candidate', side_effect=AssertionError('constructor captured')):
            services = create_services(**self.provider_arguments(), database_path=paper_path,
                pullback_policy=POLICY, pullback_cap_store=self.cap)
        self.assertIs(services['sources'].pullback_cap_store, self.cap)
        self.assertEqual(self.row_count(), 0)
        self.assertEqual(self.fetches, [])
        self.assertFalse(paper_path.exists())

    def test_legacy_capture_has_no_pullback_documents_or_cap_write(self):
        source = CurrentQuantityV2CurrentCashSources(**self.provider_arguments())
        source.capture(self.view['decision_id'])
        supplied = source.resolve(self.view['decision_id'])
        self.assertNotIn('pullback_policy', supplied['execution_package']['documents'])
        result = build_current_cash_plan(**supplied, now=self.current.isoformat())
        self.assertTrue(all(Fraction(row['limit_price']) == Fraction('9.5') for row in result['rows']))
        self.assertEqual(self.row_count(), 0)

    def test_pair_schema_validation_and_missing_minute_fail_closed(self):
        for values in [dict(pullback_policy=POLICY), dict(pullback_cap_store=self.cap),
                       dict(pullback_policy={**POLICY, 'minimum_discount': '0'}, pullback_cap_store=self.cap),
                       dict(pullback_policy=POLICY, pullback_cap_store=object())]:
            with self.assertRaises(ValueError):
                CurrentQuantityV2CurrentCashSources(**self.provider_arguments(), **values)
        def incomplete(ticker):
            doc = json.loads(self.fetch(ticker))
            doc['chart']['result'][0]['indicators']['quote'][0]['low'][0] = None
            return json.dumps(doc).encode()
        source = CurrentQuantityV2CurrentCashSources(**{**self.provider_arguments(), 'fetch': incomplete},
            pullback_policy=POLICY, pullback_cap_store=self.cap)
        with self.assertRaises(ValueError):
            source.capture(self.view['decision_id'])
        self.assertEqual(self.row_count(), 0)
        with self.assertRaisesRegex(ValueError, 'CAPTURE_REQUIRED'):
            source.resolve(self.view['decision_id'])


if __name__ == '__main__':
    unittest.main()

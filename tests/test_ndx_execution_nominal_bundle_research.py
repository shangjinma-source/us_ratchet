import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from backtest.ndx_execution_nominal_bundle_research import load_execution_nominal_bundle as load


class NominalBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dates = pd.DatetimeIndex(['2022-07-14', '2022-07-15'])
        self.rows = []
        for ticker in ('A', 'B'):
            raw = self.root/(ticker+'.csv')
            raw.write_bytes(b'Date,Close\n2022-07-14,100\n2022-07-15,101\n')
            sidecar = self.root/(ticker+'.json')
            metadata = dict(dataset_key=ticker, content_sha256=self.sha(raw),
                price_basis='unadjusted_nominal_trade_price', whole_lot_execution_use_only=True,
                return_usage_allowed=False, corporate_action_adjustment='none')
            sidecar.write_text(json.dumps(metadata), encoding='utf-8')
            self.rows.append(dict(ticker=ticker, status='FETCHED', path=str(raw), sha256=self.sha(raw),
                                  sidecar_path=str(sidecar), sidecar_sha256=self.sha(sidecar)))
        self.inventory = self.root/'inventory.csv'
        self.write_inventory()

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_inventory(self):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(self.rows[0]))
        writer.writeheader()
        writer.writerows(self.rows)
        self.inventory.write_text(output.getvalue(), encoding='utf-8')

    def refresh_raw(self):
        row = self.rows[0]
        row['sha256'] = self.sha(Path(row['path']))
        sidecar = Path(row['sidecar_path'])
        metadata = json.loads(sidecar.read_text())
        metadata['content_sha256'] = row['sha256']
        sidecar.write_text(json.dumps(metadata))
        row['sidecar_sha256'] = self.sha(sidecar)
        self.write_inventory()

    def call(self, **overrides):
        args = dict(inventory_path=self.inventory, expected_inventory_sha256=self.sha(self.inventory),
                    tickers=['B', 'A'], execution_calendar=self.dates)
        return load(**{**args, **overrides})

    def test_full_calendar_order_and_semantics(self):
        result = self.call()
        self.assertEqual(list(result['prices']), ['B', 'A'])
        self.assertTrue(result['prices'].index.equals(self.dates))
        self.assertEqual(result['prices'].loc[self.dates[1], 'A'], 101.)
        self.assertFalse(result['external_authenticity_verified'])
        self.assertFalse(result['corporate_action_coverage_verified'])
        self.assertFalse(result['forward_fill_performed'])

    def test_missing_day_duplicate_date_and_columns_rejected(self):
        for raw in (b'Date,Close\n2022-07-14,100\n',
                    b'Date,Close\n2022-07-14,100\n2022-07-14,101\n',
                    b'Date,Close,Close\n2022-07-14,100,100\n2022-07-15,101,101\n',
                    b'Date,Close\n2022-07-15,101\n2022-07-14,100\n',
                    b'Date,Close\n2022-07-14T00:00:00,100\n2022-07-15,101\n'):
            Path(self.rows[0]['path']).write_bytes(raw)
            self.refresh_raw()
            with self.assertRaises(ValueError):
                self.call()

    def test_resigned_wrong_sidecar_semantics_rejected(self):
        row = self.rows[0]
        sidecar = Path(row['sidecar_path'])
        original = json.loads(sidecar.read_text())
        for field, value in (('dataset_key', 'Z'), ('price_basis', 'adjusted'),
                             ('whole_lot_execution_use_only', 1), ('return_usage_allowed', True),
                             ('corporate_action_adjustment', 'split_adjusted')):
            sidecar.write_text(json.dumps({**original, field: value}))
            row['sidecar_sha256'] = self.sha(sidecar)
            self.write_inventory()
            with self.assertRaisesRegex(ValueError, 'semantics'):
                self.call()

    def test_inventory_and_ticker_set_must_be_complete_unique(self):
        for tickers in (['A', 'Z'], ['A', 'A'], []):
            with self.assertRaises(ValueError):
                self.call(tickers=tickers)
        self.rows.append(dict(self.rows[0]))
        self.write_inventory()
        with self.assertRaisesRegex(ValueError, 'Duplicate inventory'):
            self.call()

    def test_sha_mismatch_or_after_read_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            self.call(expected_inventory_sha256='0'*64)
        watched = Path(self.rows[0]['path'])
        original_read = Path.read_bytes
        calls = []

        def changed(path):
            raw = original_read(path)
            if path == watched:
                calls.append(True)
                if len(calls) > 1:
                    return raw+b'\n'
            return raw

        with patch.object(Path, 'read_bytes', changed):
            with self.assertRaisesRegex(ValueError, 'changed during'):
                self.call()

    def test_nonfinite_nonpositive_close_and_calendar_poison(self):
        for value in ('NaN', 'inf', '0', '-1'):
            Path(self.rows[0]['path']).write_text('Date,Close\n2022-07-14,'+value+'\n2022-07-15,101\n')
            self.refresh_raw()
            with self.assertRaises(ValueError):
                self.call()
        for dates in (self.dates[::-1], self.dates[[0, 0]], self.dates.tz_localize('UTC')):
            with self.assertRaises(ValueError):
                self.call(execution_calendar=dates)


if __name__ == '__main__':
    unittest.main()

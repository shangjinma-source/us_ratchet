import hashlib
import json
import unittest
from unittest.mock import Mock

import pandas as pd
from backtest.ndx_dynamic_nav_research import load_nav


class NavTests(unittest.TestCase):
    def run_nav(self, text, **changes):
        raw = text.encode()
        digest = hashlib.sha256(raw).hexdigest()
        manifest = json.dumps(dict(content_sha256=digest, content_bytes=len(raw),
                                   row_count=len(text.strip().splitlines())-1,
                                   fund_code='012922')).encode()
        args = dict(csv_path=Mock(read_bytes=lambda: raw),
                    manifest_path=Mock(read_bytes=lambda: manifest),
                    expected_csv_sha256=digest,
                    expected_manifest_sha256=hashlib.sha256(manifest).hexdigest(),
                    calendar=pd.to_datetime(['2023-03-31', '2023-04-01', '2023-04-03']))
        args.update(changes)
        return load_nav(**args)

    def test_backward_not_future_and_scope(self):
        result = self.run_nav('Date,Close\n2023-03-31,1\n2023-04-03,2\n')
        self.assertEqual([row['equity_index'] for row in result['rows']], [1,1,2])
        self.assertFalse(result['publication_time_verified'])
        self.assertFalse(result['promotion_allowed'])

    def test_invalid_prices(self):
        for value in ('inf', '0', '-1', 'True'):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                self.run_nav('Date,Close\n2023-03-31,'+value+'\n2023-04-03,'+value+'\n')

    def test_digest_and_missing_initial_nav(self):
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.run_nav('Date,Close\n2023-03-31,1\n', expected_csv_sha256='0'*64)
        with self.assertRaisesRegex(ValueError, 'prior NAV'):
            self.run_nav('Date,Close\n2023-04-03,1\n')


if __name__ == '__main__':
    unittest.main()

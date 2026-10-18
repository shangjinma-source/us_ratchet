from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from test_current_research_intraday_execution import NOW, payload
from data.current_research_intraday_execution_reference import read_intraday_execution_reference


class ReferenceTests(unittest.TestCase):
    def fixture(self, root):
        base, pins, receipts, previous = Path(root), {}, [], None
        for i in range(2):
            capture = NOW + timedelta(seconds=10 * i)
            data = payload()
            row = data['chart']['result'][0]
            row['meta']['regularMarketTime'] = int(capture.timestamp()) - 5
            row['meta']['regularMarketPrice'] += 10 * i
            for key in ('open', 'high', 'low', 'close'):
                row['indicators']['quote'][0][key][0] += 10 * i
            raw_name = f'quote{i}.json'
            raw = json.dumps(data).encode()
            (base / raw_name).write_bytes(raw)
            pins[raw_name] = sha256(raw).hexdigest()
            receipt = dict(schema='INTRADAY_EXECUTION_QUOTE_RECEIPT_V1', scope_id='account:2026-10',
                security_id='sndk', ticker='SNDK', session='2026-10-15', sequence=i+1,
                previous_receipt_sha256=previous, captured_at=capture.isoformat(),
                raw_path=raw_name, raw_sha256=pins[raw_name])
            name = f'receipt{i}.json'
            raw = json.dumps(receipt).encode()
            (base / name).write_bytes(raw)
            previous = pins[name] = sha256(raw).hexdigest()
            receipts.append(name)
        return dict(root=root, security_id='sndk', ticker='SNDK', session='2026-10-15',
            scope_id='account:2026-10', receipt_paths=receipts, source_hashes=pins,
            expected_tip_sha256=previous, now=NOW + timedelta(seconds=10))

    def test_rising_market_preserves_buy_cap_separate_sell_limit(self):
        with tempfile.TemporaryDirectory() as root:
            args = self.fixture(root)
            result = read_intraday_execution_reference(**args)
            self.assertEqual(Fraction(result['buy_limit']), Fraction('1412.12'))
            self.assertEqual(Fraction(result['sell_limit']), Fraction('1422.35'))
            self.assertEqual(result['receipt_count'], 2)
            self.assertTrue(result['source_bytes_verified'])
            self.assertFalse(result['latest_tip_authenticated'])

    def test_chain_gap_wrong_scope_tip_and_staleness_reject(self):
        with tempfile.TemporaryDirectory() as root:
            args = self.fixture(root)
            changes = [dict(receipt_paths=['receipt1.json']), dict(scope_id='another:2026-10'),
                dict(expected_tip_sha256='0'*64), dict(now=NOW+timedelta(seconds=140))]
            for change in changes:
                with self.subTest(change=change), self.assertRaises(ValueError):
                    read_intraday_execution_reference(**dict(args, **change))

    def test_changed_raw_and_partial_minute_cannot_be_revived(self):
        with tempfile.TemporaryDirectory() as root:
            args = self.fixture(root)
            (Path(root) / 'quote1.json').write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
                read_intraday_execution_reference(**args)
        with tempfile.TemporaryDirectory() as root:
            args = self.fixture(root)
            # Pin a response with no completed positive-volume candle at capture.
            data = payload()
            row = data['chart']['result'][0]
            row['timestamp'][0] = int(NOW.timestamp())
            path = Path(root) / 'quote0.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            digest = sha256(path.read_bytes()).hexdigest()
            args['source_hashes']['quote0.json'] = digest
            receipt_path = Path(root) / 'receipt0.json'
            receipt = json.loads(receipt_path.read_text())
            receipt['raw_sha256'] = digest
            receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
            args['source_hashes']['receipt0.json'] = sha256(receipt_path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, 'NO_COMPLETED_VALID_MINUTE'):
                read_intraday_execution_reference(**args)


if __name__ == '__main__':
    unittest.main()

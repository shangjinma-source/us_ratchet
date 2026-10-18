"""Synthetic metadata/delta tests only; no saved raw or inventory build."""
from copy import deepcopy
import gzip
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('currency_inventory_owner', Path(__file__).resolve().parents[1] / 'scripts/ndx_conditional_new_cash_inventory_v2_20260925.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def metadata_fixture(compressed=True):
    decoded = module.encode({'chart': {'error': None, 'result': [{'meta': {'symbol': 'AAA', 'currency': 'USD'}, 'indicators': 'NOT_READ'}]}})
    raw = gzip.compress(decoded) if compressed else decoded
    raw_ref = {'path': 'synthetic/AAA.bin', 'sha256': module.sha(raw)}
    receipt_ref = {'path': 'synthetic/AAA.receipt', 'sha256': 'a' * 64}
    url = 'https://example.invalid/chart/AAA?x=1'
    channel = dict(ticker='AAA', raw_path=raw_ref['path'], raw_sha256=raw_ref['sha256'],
                   decoded_sha256=module.sha(decoded), request={'url': url}, received_at_utc='2026-09-18T00:00:00Z')
    receipt = dict(http_status=200, raw_path=raw_ref['path'], raw_sha256=raw_ref['sha256'],
                   request_url=url, final_url=url, ticker='AAA', received_at_utc=channel['received_at_utc'])
    return ['AAA', channel, raw, receipt, raw_ref, receipt_ref, module.sha(decoded)]


def increment_fixture():
    reference = {'path': 'synthetic/price.json', 'sha256': 'b' * 64, 'json_pointer': '/matrices/open/2023-05-01/AAA'}
    observation = dict(currency=None, currency_status='NOT_SAVED_IN_BOUND_MATRIX_UNVERIFIED',
                       decimal_literal='123.456789123456789', reference=reference)
    security = dict(security_id='SID_A', gaps=[module.GAP, 'DATED_IDENTITY_NOT_IN_BOUND_LANE_EVIDENCE'],
                    execution_open_observations=[observation], original_fact={'interval': False})
    row = dict(securities=[security], gaps=[dict(security_id='SID_A', reason=gap) for gap in security['gaps']],
               status='INVENTORIED_WITH_EVIDENCE_GAPS', fork_executable=False, baseline={'cash': '1478.4820750045776'})
    parent = dict(schema='CONDITIONAL_NEW_CASH_SIX_COORDINATE_INVENTORY_V1', branch_coordinate_count=36,
                  rows=[deepcopy(row) for _ in range(36)], source_hashes={'old': 'c' * 64},
                  cash_fork_called=False, point_in_time_verified=False, promotion_allowed=False)
    proof = dict(currency='USD', provider_currency_metadata_observed=True, historical_currency_interval_verified=False)
    evidence = {(module.normalized(reference['path']), reference['sha256'], 'AAA'): proof}
    return parent, evidence


class CurrencyIncrementTests(unittest.TestCase):
    def test_gzip_and_identity_metadata_only(self):
        for compressed in (True, False):
            arguments = metadata_fixture(compressed)
            result = module.inspect_metadata(*arguments)
            self.assertEqual(result['currency'], 'USD')
            self.assertEqual(result['transport_encoding'], 'gzip' if compressed else 'identity')
            self.assertFalse(result['historical_currency_interval_verified'])

    def test_legacy_metadata_shape(self):
        args = metadata_fixture(False)
        receipt = args[3]
        receipt['response_path'] = receipt.pop('raw_path')
        receipt['response_sha256'] = receipt.pop('raw_sha256')
        receipt['request'] = {'url': receipt.pop('request_url')}
        args[1]['metadata_reference'] = args[5]
        self.assertEqual(module.inspect_metadata(*args)['currency'], 'USD')

    def test_raw_receipt_url_time_and_symbol_tamper(self):
        for key in ('raw_sha256', 'received_at_utc', 'final_url', 'ticker'):
            args = metadata_fixture()
            args[3][key] = 'wrong'
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.inspect_metadata(*args)
        args = metadata_fixture()
        args[-1] = 'e' * 64
        with self.assertRaises(ValueError):
            module.inspect_metadata(*args)

    def test_only_currency_fields_and_gap_change(self):
        parent, evidence = increment_fixture()
        original = deepcopy(parent)
        result = module.increment(parent, evidence, expected_removed=36, expected_identity=36)
        self.assertEqual(parent, original)
        self.assertEqual(result['v1_source_hashes_preserved'], parent['source_hashes'])
        for old, new in zip(parent['rows'], result['rows']):
            expected = deepcopy(old)
            expected['securities'][0]['gaps'].remove(module.GAP)
            expected['gaps'] = [gap for gap in expected['gaps'] if gap['reason'] != module.GAP]
            price = expected['securities'][0]['execution_open_observations'][0]
            price.update(currency='USD', currency_status='SAVED_PROVIDER_META_OBSERVED_NOT_HISTORICAL_INTERVAL_CERTIFICATION', currency_evidence=next(iter(evidence.values())))
            self.assertEqual(new, expected)
        self.assertFalse(result['promotion_allowed'])
        self.assertEqual(len(result['currency_increment']['changed_observations']), 36)
        self.assertEqual(result['currency_increment']['row_status_semantics'], 'UNCHANGED_V1_SNAPSHOT_NOT_RECOMPUTED')
        self.assertEqual(result['currency_increment']['current_gap_row_count'], 36)
        self.assertEqual(result['currency_increment']['current_no_gap_row_count'], 0)

    def test_unbound_or_permissions_or_denominator_fail(self):
        parent, evidence = increment_fixture()
        with self.assertRaises(ValueError):
            module.increment(parent, {}, expected_removed=36, expected_identity=36)
        with self.assertRaises(ValueError):
            module.increment(parent, evidence, expected_removed=35, expected_identity=36)
        parent['promotion_allowed'] = True
        with self.assertRaises(ValueError):
            module.increment(parent, evidence, expected_removed=36, expected_identity=36)

    def test_postwrite_source_drift_leaves_failure_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.write_text('original')
            result = {'source_hashes': {str(source): module.sha(source.read_bytes())}}
            output = root / 'output'
            original = module.durable
            def drift(path, raw):
                original(path, raw)
                if path.name == 'inventory.json':
                    source.write_text('changed')
            with patch.object(module, 'OUTPUT', output), patch.object(module, 'build', return_value=result), patch.object(module, 'durable', side_effect=drift):
                with self.assertRaises(ValueError):
                    module.publish()
                self.assertTrue((output / 'failure.json').exists())
                with self.assertRaises(ValueError):
                    module.publish()


if __name__ == '__main__':
    unittest.main()

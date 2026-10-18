"""Independent synthetic/temp-only currency delta review."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_conditional_new_cash_inventory_v2_20260925 import module as m, metadata_fixture, increment_fixture


class Review(unittest.TestCase):
    def test_resigned_currency_or_symbol_cannot_pass_and_quotes_not_required(self):
        for field, value in [('currency', 'EUR'), ('symbol', 'OTHER')]:
            a = metadata_fixture(False)
            payload = m.loads(a[2]); payload['chart']['result'][0]['meta'][field] = value
            a[2] = m.encode(payload); h = m.sha(a[2])
            a[4]['sha256'] = h; a[1].update(raw_sha256=h, decoded_sha256=h)
            a[3]['raw_sha256'] = h; a[-1] = h
            with self.subTest(field=field), self.assertRaises(ValueError): m.inspect_metadata(*a)
        self.assertEqual(m.inspect_metadata(*metadata_fixture())['currency'], 'USD')

    def test_transport_receipt_and_parent_reference_guards(self):
        for attack in ('body', 'receipt_symbol', 'raw_path', 'received', 'metadata_ref'):
            a = metadata_fixture()
            if attack == 'body': a[2] += b'x'
            elif attack == 'receipt_symbol': a[3]['ticker'] = 'OTHER'
            elif attack == 'raw_path': a[1]['raw_path'] = 'synthetic/OTHER.bin'
            elif attack == 'received': a[3]['received_at_utc'] = '2026-09-19T00:00:00Z'
            else: a[1]['metadata_reference'] = dict(a[5], sha256='f'*64)
            with self.subTest(attack=attack), self.assertRaises(ValueError): m.inspect_metadata(*a)

    def test_delta_inversion_restores_every_non_currency_field(self):
        parent, evidence = increment_fixture()
        for row in parent['rows']:
            row['arbitrary_sidecar'] = {'original_risk_failure': False, 'raw_nested': [None, 'TSM', {'SID': 'CLASS_A'}]}
            row['securities'][0]['gaps'].append('KEEP_UNKNOWN_OTHER_REASON')
            row['gaps'].append(dict(security_id='SID_A', reason='KEEP_UNKNOWN_OTHER_REASON'))
        before = deepcopy(parent)
        result = m.increment(parent, evidence, expected_removed=36, expected_identity=36)
        restored = deepcopy(result['rows'])
        for old, row in zip(parent['rows'], restored):
            row['gaps'] = deepcopy(old['gaps'])
            row['securities'][0]['gaps'] = deepcopy(old['securities'][0]['gaps'])
            p = row['securities'][0]['execution_open_observations'][0]
            del p['currency_evidence']; p['currency'] = None
            p['currency_status'] = 'NOT_SAVED_IN_BOUND_MATRIX_UNVERIFIED'
        self.assertTrue(m.exact(restored, before['rows']))
        self.assertTrue(m.exact(parent, before))
        self.assertFalse(result['currency_increment']['identity_gap_resolved'])
        self.assertFalse(result['point_in_time_verified'])

    def test_exact_read_hash_and_after_receipt_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source'; source.write_bytes(b'original')
            reference = m.ref(source, m.sha(source.read_bytes()))
            with self.assertRaises(ValueError): m.read(reference, {str(source): 'f'*64})
            output = root / 'out'; original = m.durable
            def drift(path, raw):
                original(path, raw)
                if path.name == 'publication.json': source.write_bytes(b'changed')
            result = {'source_hashes': {str(source): reference['sha256']}}
            with patch.object(m, 'OUTPUT', output), patch.object(m, 'build', return_value=result) as build, patch.object(m, 'durable', side_effect=drift):
                with self.assertRaises(ValueError): m.publish()
                self.assertTrue((output / 'publication.json').exists())
                self.assertTrue((output / 'failure.json').exists())
                build.reset_mock()
                with self.assertRaises(ValueError): m.publish()
                build.assert_not_called()

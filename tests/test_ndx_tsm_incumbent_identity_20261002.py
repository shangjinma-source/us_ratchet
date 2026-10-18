"""Synthetic HTML/manifest only; never publishes the real TSM source."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('tsm_sidecar_owner', Path(__file__).resolve().parents[1] / 'scripts/ndx_tsm_incumbent_identity_20261002.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    raw = ('<html><p>' + module.COVER + '</p><p>' + module.ITEM9 + '</p><p>' + module.RATIO + '</p></html>').encode()
    filing = {'path': 'synthetic/tsm.htm', 'sha256': module.digest(raw)}
    manifest_ref = {'path': 'synthetic/tsm.manifest.json', 'sha256': 'b' * 64}
    manifest = {'content_sha256': filing['sha256'], 'content_bytes': len(raw), 'cache_path': filing['path'], 'manifest_path': manifest_ref['path'],
                'schema_version': 1, 'dataset_type': 'ndx_incumbent_overlay_sec_annual_filing', 'source': 'sec_edgar_incumbent_overlay',
                'form': '20-F', 'ticker': 'TSM', 'cik': '0001046179', 'overlay_id': 'incumbent_overlay:TSM', 'source_locator': module.URL,
                'dataset_key': 'incumbent_overlay:TSM:0001193125-19-108390', 'report_date': '2018-12-31', 'filed_date': '2019-04-17',
                'evidence_available_date': '2019-04-18', 'fetched_at': '2026-07-14T17:38:21+00:00', 'research_only': True,
                'classification_automatic': False, 'price_data_used': False, 'return_data_read': False, 'backtest_results_used': False}
    return raw, manifest, filing, manifest_ref


def resign(raw, manifest, filing):
    manifest.update(content_sha256=module.digest(raw), content_bytes=len(raw))
    filing['sha256'] = module.digest(raw)


class TsmIdentityTests(unittest.TestCase):
    def test_original_overlay_dates_ratio_and_flags(self):
        args = fixture()
        original = deepcopy(args)
        result = module.extract(*args)
        self.assertEqual(args, original)
        self.assertEqual(result['security_id'], 'security:incumbent_overlay:TSM')
        self.assertEqual(result['cusip'], '874039100')
        self.assertEqual(result['ordinary_shares_per_ads'], 5)
        self.assertEqual(result['original_manifest'], args[1])
        self.assertTrue(all(result[key] is False for key in module.FALSE_FLAGS))
        self.assertIn('2018-12-31', result['ads_ratio_scope'])

    def test_same_item_context_and_ratio_tamper_rejected_even_resigned(self):
        for old, new in [('874039100', '874039101'), ('five common shares', 'four common shares'), ('“TSM”', '“WRONG”'), ('December 31, 2018', 'December 31, 2023')]:
            raw, manifest, filing, receipt = fixture()
            raw = raw.decode().replace(old, new).encode()
            resign(raw, manifest, filing)
            with self.subTest(old=old), self.assertRaises(ValueError):
                module.extract(raw, manifest, filing, receipt)

    def test_duplicate_cusip_and_inline_cik_claim_rejected(self):
        for extra in ['874039100', '0001046179', module.ITEM9]:
            raw, manifest, filing, receipt = fixture()
            raw += ('<p>' + extra + '</p>').encode()
            resign(raw, manifest, filing)
            with self.assertRaises(ValueError):
                module.extract(raw, manifest, filing, receipt)

    def test_manifest_identity_dates_bool_and_bytes_fail(self):
        for key, value in [('cik', '0000000000'), ('evidence_available_date', '2018-01-01'), ('fetched_at', '2019-04-18'), ('schema_version', True), ('content_bytes', 0)]:
            raw, manifest, filing, receipt = fixture()
            manifest[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.extract(raw, manifest, filing, receipt)

    def test_publication_drift_marker_and_existing_directory_early_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            source.write_text('original')
            result = {'source_hashes': {str(source): module.digest(source.read_bytes())}}
            output = root / 'new'
            original = module.durable
            def drift(path, raw):
                original(path, raw)
                if path.name == 'identity.json':
                    source.write_text('changed')
            with patch.object(module, 'OUTPUT', output), patch.object(module, 'build', return_value=result) as build, patch.object(module, 'durable', side_effect=drift):
                with self.assertRaises(ValueError):
                    module.publish()
                self.assertTrue((output / 'failure.json').exists())
                with self.assertRaises(ValueError):
                    module.publish()
                self.assertEqual(build.call_count, 1)


if __name__ == '__main__':
    unittest.main()

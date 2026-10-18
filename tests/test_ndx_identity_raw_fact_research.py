import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_identity_raw_fact_research as facts
from scripts import ndx_identity_raw_fact_probe as cli


class RawFactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(cli.MANIFEST.read_bytes())
        cls.probes = {row['name']: row for row in cls.manifest['probes']}

    def body(self, name):
        return Path(self.probes[name]['response_path']).read_bytes()

    def test_real_bound_facts_keep_time_and_identity_limits(self):
        result = cli.build_report()
        self.assertEqual(result['scope'], 'FACT_EXTRACTION_NOT_BINDING_ADJUDICATION')
        self.assertEqual(len(result['nport']['holdings']), 4)
        for cusip, row in result['nport']['holdings'].items():
            self.assertEqual(row['fact_observation_date'], '2022-12-31')
            self.assertIsNone(row['security_ticker'])
            self.assertIsNone(row['security_issuer_cik'])
            self.assertIsNone(row['published_at_utc'])
            self.assertIsNone(row['filing_date_in_raw_document'])
            self.assertEqual(row['reporting_fund_cik'], '0001067839')
            self.assertFalse(result['current_cusip_references'][cusip]['historical_mapping_verified'])
        event = result['nasdaq_meta_event']
        self.assertEqual(event['publication_date'], '2022-06-03')
        self.assertEqual(event['fact_effective_date'], '2022-06-09')
        self.assertTrue(event['received_at_utc'].startswith('2026-09-11T'))
        self.assertFalse(result['provider_to_historical_security_binding_verified'])
        self.assertFalse(result['point_in_time_verified'])
        self.assertFalse(result['execution_performed'])
        facts.verify(result['source_hashes'])

    def test_all_access_outcomes_retained(self):
        result = cli.build_report()
        rows = {x['name']: x for x in result['probe_outcomes']}
        self.assertEqual(set(rows), facts.PROBE_NAMES)
        self.assertEqual(rows['occ_fiserv_20230605_rename_notice']['http_status'], 403)
        self.assertEqual(rows['eastmoney_amat_nominal_two_sessions']['extraction_access_status'], 'NO_HTTP_RESPONSE')
        self.assertEqual(rows['nasdaq_amat_historical_access']['extraction_access_status'], 'HTTP_200_EMPTY_PRICE_DATA')

    def test_nport_gzip_decodes_exactly_and_rejects_missing_or_wrong_isin(self):
        raw = self.body('sec_qqq_nport_20230228')
        xml = gzip.decompress(raw)
        result = facts.extract_nport(raw, {'038222105'})
        self.assertEqual(result['decoded_sha256'], hashlib.sha256(xml).hexdigest())
        self.assertEqual(result['holdings'], facts.extract_nport(xml, {'038222105'})['holdings'])
        with self.assertRaises(ValueError):
            facts.extract_nport(xml, {'000000000'})
        with self.assertRaises(ValueError):
            facts.extract_nport(xml.replace(b'US0382221051', b'US0382221061'), {'038222105'})

    def test_openfigi_request_denominator_and_ambiguity_rejected(self):
        request = self.probes['openfigi_cusip_mapping']['request']
        raw = self.body('openfigi_cusip_mapping')
        response = json.loads(raw)
        with self.assertRaises(ValueError):
            facts.extract_openfigi(request, json.dumps(response[:-1]))
        duplicate = copy.deepcopy(response)
        duplicate[0]['data'].append(duplicate[0]['data'][0])
        with self.assertRaises(ValueError):
            facts.extract_openfigi(request, json.dumps(duplicate))
        jobs = copy.deepcopy(request)
        jobs['json_payload'][1] = jobs['json_payload'][0]
        with self.assertRaises(ValueError):
            facts.extract_openfigi(jobs, raw)

    def test_notice_rejects_wrong_cusip_date_even_with_outside_decoy(self):
        raw = self.body('nasdaq_meta_20220603_rename_notice')
        for original, replacement in [(b'30303M102', b'30303M103'), (b'June 9, 2022', b'June 8, 2022')]:
            changed = raw.replace(original, replacement) + b'<aside>' + original + b'</aside>'
            with self.assertRaises(ValueError):
                facts.extract_nasdaq_meta_notice(changed)

    def test_raw_tampering_rejected_under_new_manifest_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = copy.deepcopy(self.manifest)
            for row in copied['probes']:
                if row['response_path']:
                    path = Path(directory) / Path(row['response_path']).name
                    path.write_bytes(Path(row['response_path']).read_bytes())
                    row['response_path'] = str(path)
            path.write_bytes(path.read_bytes() + b'changed')
            manifest = Path(directory) / 'manifest.json'
            manifest.write_text(json.dumps(copied), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Raw HTTP body binding differs'):
                facts.extract_bound_probe(manifest_path=manifest, expected_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())

    def test_create_only_and_research_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(cli, 'ROOT', Path(directory)):
                output = Path(directory) / 'data/cache/research/facts.json'
                cli.save_report(output)
                before = output.read_bytes()
                with self.assertRaises(FileExistsError):
                    cli.save_report(output)
                self.assertEqual(output.read_bytes(), before)
                with self.assertRaises(ValueError):
                    cli.save_report(Path(directory) / 'live.json')


if __name__ == '__main__':
    unittest.main()

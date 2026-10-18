"""Synthetic nested-inline annual and gzipped NPORT; no real publication."""
from copy import deepcopy
import gzip
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('asml_sidecar_owner', Path(__file__).resolve().parents[1] / 'scripts/ndx_asml_incumbent_identity_20261002.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    ctx = module.CONTEXT
    fields = ''.join('<ix:nonNumeric name="' + key + '" contextRef="' + ctx + '">' + text + '</ix:nonNumeric>' for key, text in
                     [('dei:EntityCentralIndexKey', '0000937966'), ('dei:TradingSymbol', 'ASML'), ('dei:Security12bTitle', 'Ordinary Shares'),
                      ('dei:DocumentPeriodEndDate', '<ix:nonNumeric name="dei:CurrentFiscalYearEndDate" contextRef="' + ctx + '">December 31</ix:nonNumeric>, 2020')])
    annual = ('<html><xbrli:context id="' + ctx + '"><xbrli:entity><xbrli:identifier>0000937966</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2020-01-01</xbrli:startDate><xbrli:endDate>2020-12-31</xbrli:endDate></xbrli:period></xbrli:context>' + fields + ''.join('<p>' + text + '</p>' for text in module.TEXTS) + '</html>').encode()
    xml = b'<edgarSubmission xmlns="http://www.sec.gov/edgar/nport"><formData><genInfo><repPdDate>2022-12-31</repPdDate><repPdEnd>2023-09-30</repPdEnd><regCik>0001067839</regCik></genInfo><invstOrSecs><invstOrSec><name>ASML Holding N.V.</name><title>ASML Holding N.V., New York Shares</title><cusip>N07059210</cusip><lei>724500Y6DUVHQD6OXN27</lei><curCd>USD</curCd><assetCat>EC</assetCat><identifiers><isin value="USN070592100"/></identifiers></invstOrSec></invstOrSecs></formData></edgarSubmission>'
    raw = gzip.compress(xml)
    refs = {role: {'path': 'synthetic/' + role, 'sha256': 'a' * 64} for role in module.BOUND}
    refs['annual']['sha256'] = module.digest(annual)
    refs['nport_raw']['sha256'] = module.digest(raw)
    am = dict(content_bytes=len(annual), content_sha256=refs['annual']['sha256'], cache_path=refs['annual']['path'], manifest_path=refs['annual_manifest']['path'],
              schema_version=1, cik='0000937966', issuer_id='issuer:0000937966', ticker='ASML', form='20-F', accession_number='0000937966-21-000007',
              source_locator=module.ANNUAL_URL, evidence_available_date='2021-02-11', fetched_at='2026-07-13T15:45:54+00:00',
              dataset_type='ndx_taxonomy_v2_sec_raw_filing', research_only=True, classification_automatic=False)
    nm = {'probes': [dict(name='sec_qqq_nport_20230228', http_status=200, transport_success=True, request={'method': 'GET', 'url': module.NPORT_URL},
                         final_url=module.NPORT_URL, received_at_utc='2026-09-11T18:19:26.610468+00:00', started_at_utc='2026-09-11T18:19:26.177637+00:00',
                         response_path=refs['nport_raw']['path'], response_sha256=refs['nport_raw']['sha256'], response_bytes=len(raw))]}
    return [annual, am, raw, nm, refs, module.digest(xml)]


def resign_annual(args, value):
    args[0] = value
    args[1].update(content_bytes=len(value), content_sha256=module.digest(value))
    args[4]['annual']['sha256'] = module.digest(value)


def resign_xml(args, value):
    args[2] = gzip.compress(value)
    args[-1] = module.digest(value)
    args[4]['nport_raw']['sha256'] = module.digest(args[2])
    args[3]['probes'][0].update(response_bytes=len(args[2]), response_sha256=module.digest(args[2]))


class AsmlTests(unittest.TestCase):
    def test_nested_fields_separate_dates_classes_and_fund(self):
        args = fixture()
        before = deepcopy(args)
        result = module.assemble(*args)
        self.assertEqual(args, before)
        self.assertEqual(result['annual_fact']['report_date'], '2020-12-31')
        self.assertEqual(result['nport_fact']['report_date'], '2022-12-31')
        self.assertEqual(result['nport_fact']['reporting_period_end'], '2023-09-30')
        self.assertEqual(result['issuer_cik'], '0000937966')
        self.assertEqual(result['nport_fact']['reporting_fund_cik'], '0001067839')
        self.assertIsNone(result['ads_conversion_ratio'])
        self.assertTrue(all(result[key] is False for key in module.FALSE_FLAGS))

    def test_context_fields_and_class_mutation_resigned(self):
        for old, new in [('Ordinary Shares', 'American Depositary Shares'), ('2020-01-01', '2021-01-01'), ('0000937966</xbrli:identifier>', '0001067839</xbrli:identifier>')]:
            args = fixture()
            resign_annual(args, args[0].decode().replace(old, new).encode())
            with self.subTest(old=old), self.assertRaises(ValueError):
                module.assemble(*args)

    def test_nport_dates_currency_and_lei_mutations_resigned(self):
        for old, new in [(b'2022-12-31', b'2023-02-28'), (b'USD', b'EUR'), (b'724500Y6DUVHQD6OXN27', b'WRONG')]:
            args = fixture()
            resign_xml(args, gzip.decompress(args[2]).replace(old, new))
            with self.subTest(old=old), self.assertRaises(ValueError):
                module.assemble(*args)

    def test_duplicate_security_and_raw_receipt_tampering(self):
        args = fixture()
        xml = gzip.decompress(args[2])
        security = xml.split(b'<invstOrSec>')[1].split(b'</invstOrSec>')[0]
        resign_xml(args, xml.replace(b'</invstOrSecs>', b'<invstOrSec>' + security + b'</invstOrSec></invstOrSecs>'))
        with self.assertRaises(ValueError):
            module.assemble(*args)
        args = fixture()
        args[3]['probes'][0]['final_url'] = 'wrong'
        with self.assertRaises(ValueError):
            module.assemble(*args)

    def test_source_drift_keeps_failure_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'source'
            source.write_text('sealed')
            result = {'source_hashes': {str(source): module.digest(source.read_bytes())}}
            output = base / 'output'
            original = module.durable
            def drift(path, raw):
                original(path, raw)
                if path.name == 'identity.json':
                    source.write_text('changed')
            with patch.object(module, 'OUTPUT', output), patch.object(module, 'build', return_value=result), patch.object(module, 'durable', side_effect=drift):
                with self.assertRaises(ValueError):
                    module.publish()
                self.assertTrue((output / 'failure.json').exists())
                with self.assertRaises(ValueError):
                    module.publish()


if __name__ == '__main__':
    unittest.main()

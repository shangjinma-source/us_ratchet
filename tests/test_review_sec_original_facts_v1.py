import unittest
from hashlib import sha256

from scripts.review_sec_original_facts_v1 import review, verify_receipt


class OriginalFactReviewTests(unittest.TestCase):
    def fixture(self, extra='', sign='-'):
        filing = f'''<html><xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity><xbrli:period>
        <xbrli:startDate>2022-04-01</xbrli:startDate><xbrli:endDate>2022-06-30</xbrli:endDate>
        </xbrli:period></xbrli:context><xbrli:unit id="u"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
        <ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="c" unitRef="u"
        scale="3" sign="{sign}" format="ixt:num-dot-decimal">21,748</ix:nonFraction>{extra}</html>'''.encode()
        facts = {'cik': 1, 'facts': {'us-gaap': {'NetIncomeLoss': {'units': {'USD': [
            {'accn': 'a', 'start': '2022-04-01', 'end': '2022-06-30', 'val': -21748000},
            {'accn': 'later', 'start': '2022-04-01', 'end': '2022-06-30', 'val': 999},
        ]}}}}}
        return facts, filing

    def test_signed_scaled_original_and_ignore_other_accession(self):
        result = review(*self.fixture(), 'a')
        self.assertEqual(result['counts'], {'MATCH': 1})

    def test_conflicting_original_values_fail(self):
        duplicate = '<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="c" unitRef="u">999</ix:nonFraction>'
        self.assertEqual(review(*self.fixture(duplicate), 'a')['counts'], {'CONFLICT': 1})

    def test_wrong_sign_fails(self):
        self.assertEqual(review(*self.fixture(sign=''), 'a')['counts'], {'CONFLICT': 1})

    def test_segment_does_not_prove_consolidated_value(self):
        facts, filing = self.fixture()
        filing = filing.replace(b'<xbrli:period>', b'<xbrli:segment>business</xbrli:segment><xbrli:period>')
        self.assertEqual(review(facts, filing, 'a')['counts'], {'ORIGINAL_MISSING': 1})

    def test_wrong_issuer_does_not_match(self):
        facts, filing = self.fixture()
        facts['cik'] = 2
        self.assertEqual(review(facts, filing, 'a')['counts'], {'ORIGINAL_MISSING': 1})

    def test_unknown_transformation_cannot_hide_conflict(self):
        extra = '<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="c" unitRef="u" format="ixt:unsupported">999</ix:nonFraction>'
        self.assertEqual(review(*self.fixture(extra), 'a')['counts'], {'UNSUPPORTED_ORIGINAL_VALUE': 1})

    def test_receipt_binds_accession_cik_and_bytes(self):
        _, filing = self.fixture()
        receipts = [dict(status=200, sha256=sha256(filing).hexdigest(),
                         url='https://www.sec.gov/Archives/edgar/data/1/000000000122000001/a.htm')]
        verify_receipt(receipts, filing, '0000000001-22-000001', 1)
        for body, accession, cik in [(filing+b'x', '0000000001-22-000001', 1),
                                     (filing, '0000000001-22-000002', 1),
                                     (filing, '0000000001-22-000001', 2)]:
            with self.assertRaises(ValueError):
                verify_receipt(receipts, body, accession, cik)

    def test_duplicate_context_or_unit_ids_rejected(self):
        for extra in ('<xbrli:context id="c"></xbrli:context>',
                      '<xbrli:unit id="u"></xbrli:unit>'):
            with self.assertRaises(ValueError):
                review(*self.fixture(extra), 'a')


if __name__ == '__main__':
    unittest.main()

import unittest

from scripts.review_sec_original_facts_v1 import review


class OriginalFactReviewTests(unittest.TestCase):
    def fixture(self, extra='', sign='-'):
        filing = f'''<html><xbrli:context id="c"><xbrli:period>
        <xbrli:startDate>2022-04-01</xbrli:startDate><xbrli:endDate>2022-06-30</xbrli:endDate>
        </xbrli:period></xbrli:context><xbrli:unit id="u"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
        <ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="c" unitRef="u"
        scale="3" sign="{sign}" format="ixt:num-dot-decimal">21,748</ix:nonFraction>{extra}</html>'''.encode()
        facts = {'facts': {'us-gaap': {'NetIncomeLoss': {'units': {'USD': [
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


if __name__ == '__main__':
    unittest.main()

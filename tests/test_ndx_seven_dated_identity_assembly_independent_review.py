"""Independent adversarial checks; no publication or execution."""
import copy
import unittest

from scripts import ndx_seven_dated_identity_assembly_20260919 as m


class IndependentIdentityReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = m.build()

    def test_wrong_share_class_rejected_for_each_security(self):
        for ticker in m.COORDINATES:
            with self.subTest(ticker=ticker):
                rows = copy.deepcopy(self.report['rows'])
                row = next(r for r in rows if r['ticker'] == ticker)
                row['security_class'] = 'Class B Common Stock'
                with self.assertRaises(ValueError):
                    m.validate_rows(rows)

    def test_consistent_wrong_issuer_and_cusip_cannot_relabel(self):
        for ticker in m.COORDINATES:
            with self.subTest(ticker=ticker):
                rows = copy.deepcopy(self.report['rows'])
                row = next(r for r in rows if r['ticker'] == ticker)
                row.update(subject_cik='0000000001', issuer_id='issuer:0000000001',
                           cusip='000000000', security_id='security:0000000001:000000000')
                with self.assertRaises(ValueError):
                    m.validate_rows(rows)


if __name__ == '__main__':
    unittest.main()

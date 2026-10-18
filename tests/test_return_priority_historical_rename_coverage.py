import unittest
from scripts.return_priority_historical_rename_coverage import map_dates, validate_rule


class RenameCoverageTests(unittest.TestCase):
    def test_exact_boundary_and_no_fallback(self):
        caches = {'FISV': {'2023-06-06': {}, '2023-06-07': {}}, 'FI': {'2023-06-06': {}, '2023-06-07': {}}}
        rows = map_dates(['2023-06-06', '2023-06-07'], caches)
        self.assertEqual([row['price_ticker'] for row in rows], ['FISV', 'FI'])
        del caches['FI']['2023-06-07']
        self.assertFalse(map_dates(['2023-06-07'], caches)[0]['present'])
        del caches['FI']
        with self.assertRaises(ValueError):
            map_dates(['2023-06-07'], caches)

    def test_identity_conflict_rejected(self):
        rule = dict(rule_id='fiserv_fisv_to_fi_2023', cik='0000798354', cusip='WRONG', recognized_tickers=['FISV','FI'])
        with self.assertRaises(ValueError):
            validate_rule(rule)


if __name__ == '__main__':
    unittest.main()

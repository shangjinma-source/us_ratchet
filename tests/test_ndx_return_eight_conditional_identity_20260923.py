from copy import deepcopy
import json
import unittest

from scripts import ndx_return_eight_conditional_identity_20260923 as module


class ConditionalIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = {role: json.loads((module.BASE / path).read_bytes())
                         for role, (path, _) in module.BOUND.items()}

    def test_eight_securities_seven_issuers_and_no_interval_upgrade(self):
        report = module.assemble(self.documents)
        self.assertEqual((report['security_count'], report['distinct_issuer_count']), (8, 7))
        self.assertEqual(report['conditional_window'], dict(start='2023-03-31', end='2023-09-01'))
        self.assertFalse(report['continuous_identity_interval_verified'])
        self.assertFalse(report['early_evidence_availability_inferred'])
        self.assertFalse(report['source_facts_reparsed'])

    def test_class_c_cannot_replace_class_a(self):
        documents = deepcopy(self.documents)
        row = next(row for row in documents['new']['rows'] if row['ticker'] == 'GOOGL')
        row['facts']['cusip'] = '02079K107'
        with self.assertRaises(ValueError):
            module.assemble(documents)
        row['facts']['cusip'] = '02079K305'
        row['parsed_original_cover']['security_class_title'] = 'Class C Capital Stock'
        with self.assertRaises(ValueError):
            module.assemble(documents)

    def test_two_alphabet_classes_in_one_decision_are_rejected(self):
        documents = deepcopy(self.documents)
        august = documents['schedule']['schedule'][4]['targets']
        september = documents['schedule']['schedule'][5]['targets']
        key = 'security:0001652044:02079K305'
        august[key] = deepcopy(september[key])
        with self.assertRaises(ValueError):
            module.assemble(documents)

    def test_old_window_or_web_original_bytes_cannot_be_upgraded(self):
        for kind in ('window', 'raw', 'pit'):
            documents = deepcopy(self.documents)
            if kind == 'window':
                documents['seven']['conditional_window']['end'] = '2023-09-01'
            elif kind == 'raw':
                documents['new']['raw_http_original_verified_count'] = 2
            else:
                documents['four']['point_in_time_verified'] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                module.assemble(documents)


if __name__ == '__main__':
    unittest.main()

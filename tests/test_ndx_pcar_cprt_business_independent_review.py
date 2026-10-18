import copy
import hashlib
import unittest
from unittest.mock import patch

from scripts import ndx_pcar_cprt_business_facts_20260923 as m
from test_ndx_pcar_cprt_business_facts_20260923 import fixture


class BusinessIndependentTests(unittest.TestCase):
    def test_business_section_not_rescued_by_matching_mda(self):
        raw = fixture('CPRT')
        clause = m.CLAUSES['CPRT'][1].encode()
        outside = raw.replace(b'</html>', b'<p>'+clause+b'</p></html>')
        self.assertEqual(len(m.extract('CPRT', outside)['original_business_clauses']), 3)
        misplaced = outside.replace(clause, b'Business statement omitted', 1)
        with self.assertRaises(ValueError): m.extract('CPRT', misplaced)
        duplicated = raw.replace(clause, clause+b' '+clause)
        with self.assertRaises(ValueError): m.extract('CPRT', duplicated)

    def test_actual_offset_hash_and_unresolved_categories(self):
        report = m.build()
        for row in report['rows']:
            spec = m.identity.CASES[row['ticker']]
            raw = (m.ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec'/spec['cover']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), spec['cover_sha'])
            text = ' '.join(m.BeautifulSoup(raw.decode('utf8'), 'lxml').get_text(' ', strip=True).split())
            for clause in row['original_business_clauses']:
                start = clause['normalized_text_offset']; original = clause['original_text']
                self.assertEqual(text[start:start+len(original)], original)
                self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), clause['text_sha256'])
            self.assertIsNone(row['assigned_risk_chain'])
            self.assertIsNone(row['annual_filing_date'])
            self.assertIsNone(row['annual_receipt_time'])
            self.assertTrue(all(row[key] is False for key in m.FALSE))
        self.assertEqual(report['rows'][1]['candidate_risk_chains'], ['internet_ecommerce','automotive','industrial'])
        self.assertIn('no revenue dominance', report['rows'][0]['rationale'])

    def test_complete_verify_rejects_chosen_class_and_rewritten_dictionary(self):
        value = m.build()
        with patch.object(m, 'build', return_value=value):
            for mode in ['assigned', 'definition', 'source']:
                changed = copy.deepcopy(value)
                if mode == 'assigned': changed['rows'][1]['assigned_risk_chain'] = 'automotive'
                if mode == 'definition': changed['taxonomy_definitions']['automotive']['description'] = 'All companies'
                if mode == 'source': changed['source_hashes'].pop(str(m.TAXONOMY))
                with self.subTest(mode=mode), self.assertRaises(ValueError): m.verify(changed)


if __name__ == '__main__': unittest.main()

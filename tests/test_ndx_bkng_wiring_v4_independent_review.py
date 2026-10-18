"""Read-only saved parent and synthetic declarations; no publication."""
import unittest
import test_ndx_new_cutoff_identity_risk_wiring_v4_20260925 as owner

m = owner.m


class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        owner.Tests.setUpClass()

    def docs(self):
        return owner.Tests().docs()

    def test_cross_document_proof_and_option_terms_cannot_upgrade(self):
        for key in ('direct_single_document_cusip_cik_proof', 'option_contract_terms_used_as_equity_identity', 'provider_binding_verified'):
            docs = self.docs()
            docs['bkng_declaration'][key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.assemble(docs)

    def test_coordinate_and_original_review_are_distinct(self):
        for attack in ('coordinate', 'review_fallback', 'memo_class', 'cik'):
            docs = self.docs()
            d = docs['bkng_declaration']
            if attack == 'coordinate':
                d['coordinate']['security_id'] = 'security:0001075531:current_ticker:BKNG'
            elif attack == 'review_fallback':
                d['saved_review_decision']['allow_fallback'] = True
            elif attack == 'memo_class':
                d['registry_event']['security_class'] = 'OPTION'
            else:
                d['annual_manifest']['cik'] = '0000000001'
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                m.assemble(docs)

    def test_preserved_parent_is_not_rewritten_by_increment(self):
        docs = self.docs()
        before = m.canonical(docs)
        result = m.assemble(docs)
        self.assertEqual(m.canonical(docs), before)
        row = next(r for r in result['rows'] if r['ticker']=='BKNG')
        self.assertTrue(row['new_assumption']['cross_document_identity_connection_is_explicit_assumption'])
        self.assertFalse(row['new_assumption']['source_interval_extended'])
        self.assertFalse(result['point_in_time_verified'])
        self.assertIsNone(result['fit_column_count'])
        self.assertEqual(result['conditional_candidates_with_saved_volume_unit_block'], ['CRWD'])


if __name__ == '__main__':
    unittest.main()

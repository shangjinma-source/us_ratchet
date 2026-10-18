import copy
import unittest
from test_ndx_saved_conditional_evidence_links_research import fixture,module

class IndependentLinksReview(unittest.TestCase):
    def test_exact_context_duplicate_context_and_dimension_separation(self):
        a=fixture(); e=a['extracted_document']['extraction'];e['dei_facts'][0]['context_ref']='stock'
        result=module.link_saved_conditional_evidence(**a)
        self.assertEqual(result['all_cik_links'][0]['relation'],'EXACT_CONTEXT_DECLARED_CIK_LINK')
        e['contexts'].append(copy.deepcopy(e['contexts'][1]))
        result=module.link_saved_conditional_evidence(**a)
        self.assertEqual(result['all_cik_links'][0]['relation'],'UNRESOLVED_CONTEXT_OR_ENTITY_PERIOD_MISMATCH')
        self.assertTrue(all(x['dimensions_merged'] is False and x['identity_certified'] is False for x in result['all_cik_links']))

    def test_underlying_alternative_retained_and_no_implicit_selection(self):
        a=fixture();e=a['extracted_document']['extraction']
        e['same_context_security_groups'][1]['ticker_fact_indexes']=[]
        a['selection_contract']['all_security_groups']=copy.deepcopy(e['same_context_security_groups'])
        original=copy.deepcopy(a)
        result=module.link_saved_conditional_evidence(**a)
        self.assertEqual(len(result['all_security_groups_preserved']),2)
        self.assertEqual(len(result['ticker_matching_groups']),1)
        self.assertEqual(a,original)
        a['selection_contract'].update(selected_group_indexes=[1],selected_title_fact_index=4,exact_title='Senior Notes',context_ref='notes')
        with self.assertRaises(ValueError):module.link_saved_conditional_evidence(**a)

    def test_broken_cik_and_period_do_not_become_identity_proof(self):
        a=fixture();e=a['extracted_document']['extraction'];e['dei_facts'][0]['continuation_complete']=False
        result=module.link_saved_conditional_evidence(**a)
        self.assertTrue(all(x['relation']=='UNRESOLVED_CONTEXT_OR_ENTITY_PERIOD_MISMATCH' for x in result['all_cik_links']))
        self.assertTrue(all(result[k] is False for k in module.FALSE))
        self.assertEqual(result['original_queue_item']['identity_matches'],a['queue_item']['identity_matches'])
        self.assertIn('NOT_SEC_COVER_CUSIP_PROOF',result['cusip_link_scope'])
        self.assertEqual(result['saved_review_date_fields']['selection_date']['value'],'2026-07-13')
        self.assertTrue(result['review_selection_postdates_window_start'])

    def test_cik_value_is_separate_from_exact_context(self):
        for text,expected in [('2',False),('1',True),('１２',None)]:
            a=fixture();e=a['extracted_document']['extraction'];e['dei_facts'][0].update(context_ref='stock',resolved_text=text)
            result=module.link_saved_conditional_evidence(**a)
            link=result['all_cik_links'][0]
            self.assertEqual(link['relation'],'EXACT_CONTEXT_DECLARED_CIK_LINK')
            self.assertIs(link['cik_matches_review_issuer'],expected)
            self.assertFalse(result['provider_binding_verified'])

    def test_source_selection_and_bool_fact_index_rejected(self):
        for mutate in (lambda a:a['selection_contract']['document_reference'].update(sha256='e'*64),
                       lambda a:a['extracted_document']['extraction'].update(cik_fact_indexes=[False]),
                       lambda a:a['selection_contract'].update(selected_title_fact_index=True),
                       lambda a:a['extracted_document']['extraction']['same_context_security_groups'][0].update(title_fact_indexes=[True])):
            a=fixture();a['selection_contract']['document_reference']=copy.deepcopy(a['document_reference']);mutate(a)
            with self.assertRaises(ValueError):module.link_saved_conditional_evidence(**a)

if __name__=='__main__':unittest.main()

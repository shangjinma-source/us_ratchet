import copy
import unittest
from backtest import ndx_saved_conditional_evidence_links_research as module


def fixture():
    raw={'path':'raw.html','sha256':'a'*64};docref={'path':'document.json','sha256':'b'*64}
    review={'raw_sha256':'a'*64,'issuer_id':'issuer:0000000001','risk_chain':'unchanged','selection_date':'2026-07-13','evidence_available_date':'2025-01-01'}
    match={'decision':review,'raw_reference':raw,'reference':{'path':'review.yaml','sha256':'c'*64,'json_pointer':'/decisions/0'}}
    coordinate={'security_id':'security:0000000001:ABC123456','issuer_id':'issuer:0000000001','cusip':'ABC123456'}
    queue={'ticker':'ABC','inventory_row_index':3,'raw_reference':raw,'review_match':match,
        'resolved_identity_coordinates':[coordinate],'identity_matches':[{'row':coordinate,'nport_matches':[{'original':'preserved'}]}]}
    facts=[{'name':'dei:EntityCentralIndexKey','context_ref':'entity','resolved_text':'0000000001','continuation_complete':True},
        {'name':'dei:TradingSymbol','context_ref':'stock','resolved_text':'ABC','continuation_complete':True},
        {'name':'dei:Security12bTitle','context_ref':'stock','resolved_text':'Common stock','continuation_complete':True},
        {'name':'dei:TradingSymbol','context_ref':'notes','resolved_text':'ABC','continuation_complete':True},
        {'name':'dei:Security12bTitle','context_ref':'notes','resolved_text':'Senior Notes','continuation_complete':True}]
    contexts=[{'context_id':key,'identifiers':[{'scheme':'SEC','value':'0000000001'}],
        'periods':[{'kind':'instant','value':'2025-12-31'}],'dimensions':[{'dimension':'class','value':key}]} for key in ('entity','stock','notes')]
    groups=[{'context_ref':'stock','ticker_fact_indexes':[1],'title_fact_indexes':[2]},
            {'context_ref':'notes','ticker_fact_indexes':[3],'title_fact_indexes':[4]}]
    extraction={'schema':'SAVED_SEC_COVER_EVIDENCE_RESEARCH_V1','raw_sha256':'a'*64,'dei_facts':facts,'contexts':contexts,
        'same_context_security_groups':groups,'cik_fact_indexes':[0],**{key:False for key in
        ('point_in_time_verified','promotion_allowed','cover_cusip_identity_verified','claimed_section_hashes_reverified')}}
    doc={'status':'EXTRACTED_SAVED_FACTS_NOT_IDENTITY_ADMISSION','raw_sha256':'a'*64,'raw_references':[raw],
        'original_review_matches':[match],'extraction':extraction}
    contract={'ticker':'ABC','inventory_row_index':3,'raw_sha256':'a'*64,'document_reference':docref,
        'all_security_groups':copy.deepcopy(groups),'selected_group_indexes':[0],'selected_title_fact_index':2,
        'context_ref':'stock','exact_title':'Common stock',
        'reviewed_contract_reference':{'path':'selection.json','sha256':'d'*64,'json_pointer':'/rows/3'},
        'special_class_assumption':{'conversion_performed':False}}
    return dict(queue_item=queue,extracted_document=doc,document_reference=docref,
                selection_contract=contract,assumed_window=copy.deepcopy(module.WINDOW))


class LinksTests(unittest.TestCase):
    def test_all_alternatives_contexts_dates_and_original_evidence(self):
        args=fixture();before=copy.deepcopy(args);result=module.link_saved_conditional_evidence(**args)
        self.assertEqual(args,before)
        self.assertEqual(len(result['ticker_matching_groups']),2)
        self.assertEqual(result['selected_title_fact']['resolved_text'],'Common stock')
        self.assertEqual(result['all_cik_links'][0]['relation'],'CROSS_CONTEXT_EQUAL_IDENTIFIERS_AND_PERIODS_CONDITIONAL_LINK')
        self.assertNotEqual(result['all_cik_links'][0]['cik_contexts'][0]['dimensions'],result['all_cik_links'][0]['security_contexts'][0]['dimensions'])
        self.assertTrue(result['review_selection_postdates_window_start'])
        self.assertIsNone(result['saved_review_date_fields']['fetched_at']['value'])
        self.assertFalse(result['provider_identity_verified']); self.assertEqual(result['saved_risk_chain'],'unchanged')

    def test_period_or_identifier_mismatch_not_linked(self):
        for field in ('periods','identifiers'):
            args=fixture();args['extracted_document']['extraction']['contexts'][0][field]=[]
            result=module.link_saved_conditional_evidence(**args)
            self.assertTrue(all(link['relation']=='UNRESOLVED_CONTEXT_OR_ENTITY_PERIOD_MISMATCH' for link in result['all_cik_links']))

    def test_explicit_selection_source_type_and_title_attacks(self):
        for mutate in (
            lambda a:a['selection_contract'].update(selected_group_indexes=[True]),
            lambda a:a['selection_contract'].update(selected_title_fact_index=4),
            lambda a:a['selection_contract'].update(exact_title='Depositary shares'),
            lambda a:a['selection_contract']['all_security_groups'].pop(),
            lambda a:a['selection_contract'].update(raw_sha256='0'*64),
            lambda a:a['queue_item']['identity_matches'].clear(),
        ):
            args=fixture();mutate(args)
            with self.assertRaises(ValueError): module.link_saved_conditional_evidence(**args)

    def test_unselected_remains_null_and_unknown_date_not_late(self):
        args=fixture();args['selection_contract'].update(selected_group_indexes=[],selected_title_fact_index=None,exact_title=None,context_ref=None)
        args['queue_item']['review_match']['decision'].pop('selection_date')
        result=module.link_saved_conditional_evidence(**args)
        self.assertEqual(result['status'],'NO_EXPLICIT_TITLE_SELECTION')
        self.assertIsNone(result['selected_title_fact']);self.assertIsNone(result['review_selection_postdates_window_start'])

    def test_same_context_wrong_or_invalid_cik_does_not_match_issuer(self):
        for text, expected, status in [('2',False,'MISMATCH'),('not a CIK',None,'UNKNOWN_INVALID_CIK_TEXT'),('1',True,'MATCH')]:
            args=fixture();fact=args['extracted_document']['extraction']['dei_facts'][0]
            fact.update(context_ref='stock',resolved_text=text)
            result=module.link_saved_conditional_evidence(**args)
            link=result['all_cik_links'][0]
            self.assertEqual(link['relation'],'EXACT_CONTEXT_DECLARED_CIK_LINK')
            self.assertIs(link['cik_matches_review_issuer'],expected)
            self.assertEqual(link['cik_review_issuer_match_status'],status)
            self.assertEqual(link['cik_fact']['resolved_text'],text)
            self.assertFalse(result['provider_binding_verified'])


if __name__=='__main__': unittest.main()

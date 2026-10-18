import copy
from datetime import date,timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_bulk_conditional_wiring_20261003 as module


def fixture():
    rows=[]
    for i in range(101):
        issuer=f'{max(0,i-1):010d}' if i<25 else f'{i:010d}'
        coordinate={'ticker':f'T{i}','security_id':f'security:{issuer}:C{i}','issuer_id':'issuer:'+issuer,'cusip':f'C{i}','security_class':'Common'} if i<25 else None
        rows.append({'ticker':f'T{i}','coordinate':coordinate,'risk_chain':'saved' if coordinate else None,
            'gaps':[] if coordinate else ['NO_DATED_COORDINATE_AND_RISK_ASSEMBLED_FROM_SELECTED_SOURCES'],
            'complete_original_evidence':[],'new_assumed_window':copy.deepcopy(module.WINDOW),**module.FLAGS})
    calendar=[];current=date(2026,3,20)
    while current<=date(2026,9,21):
        if current.weekday()<5:calendar.append(current.isoformat())
        current+=timedelta(days=1)
    # The saved observed calendar may omit exchange holidays.
    calendar=calendar[:126]+[calendar[-1]]
    parent={'schema':'NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V6','rows':rows,'calendar':calendar,
        'input_references':{'old':'preserved'},**{key:[{'old':key}] for key in module.SIDECARS},**module.FLAGS}
    links={'schema':'SOURCE_BOUND_SAVED_CONDITIONAL_EVIDENCE_LINKS_V1','assumed_window':module.WINDOW,
        'historical_denominators':[{'original':i} for i in range(15)],'rows':[], 'links':[],**module.FLAGS}
    for i,row in enumerate(rows):
        links['rows'].append({'ticker':row['ticker'],'new_link_index':i-25 if 25<=i<78 else None,
            'original_inventory_row':{'original_wiring_row':copy.deepcopy(row)}})
    for i in range(25,78):
        issuer=f'{i:010d}';coord={'security_id':f'security:{issuer}:C{i}','issuer_id':'issuer:'+issuer,'cusip':f'C{i}'}
        context={'context_id':'c','identifiers':[{'value':issuer}],'periods':[{'value':'2025'}],'dimensions':[]}
        group={'context_ref':'c','title_fact_indexes':[1]}
        contract={'selected_group_indexes':[0],'selected_title_fact_index':1,'all_security_groups':[group], 'exact_title':'Common','context_ref':'c'}
        link={'ticker':f'T{i}','status':'EXPLICIT_CONDITIONAL_RESEARCH_LINKS_ONLY','assumed_window':module.WINDOW,
            'original_resolved_coordinates':[coord],'reviewed_selection_contract_preserved':contract,
            'selected_group_indexes':[0],'all_security_groups_preserved':[group],
            'ticker_matching_groups':[{'group_index':0,'group':group}],
            'selected_title_fact':{'resolved_text':'Common','context_ref':'c','continuation_complete':True},
            'original_queue_item':{'review_match':{'decision':{'issuer_id':'issuer:'+issuer,'status':'accepted','risk_chain':'saved','selection_date':'2026-07-13'}}},
            'saved_risk_chain':'saved','resolved_coordinate_review_issuer_matches':[{'coordinate':coord,'review_issuer_id':'issuer:'+issuer,'issuer_matches':True}],
            'all_cik_links':[{'group_index':0,'cik_matches_review_issuer':True,'cik_review_issuer_match_status':'MATCH',
                'normalized_cik':issuer,'review_issuer_id':'issuer:'+issuer,'cik_fact':{'resolved_text':issuer,'context_ref':'c'},
                'relation':'EXACT_CONTEXT_DECLARED_CIK_LINK','cik_contexts':[context],'security_contexts':[context],
                'dimensions_merged':False,'identity_certified':False}],
            'review_selection_postdates_window_start':True,'saved_review_date_fields':{'selection_date':{'value':'2026-07-13'},'evidence_available_date':{'value':'2025-01-01'}},
            'class_handling_preserved':{'no_conversion':True},**module.FLAGS}
        links['links'].append({'inventory_row_index':i,'ticker':f'T{i}','selection_contract':contract,'link':link})
    return parent,links,{'path':'links.json','sha256':'a'*64}


class BulkTests(unittest.TestCase):
    def test_denominators_original48_sidecars_and_full_provenance(self):
        args=fixture();before=copy.deepcopy(args);value=module.assemble_bulk_conditional_wiring(*args)
        self.assertEqual(args,before)
        self.assertEqual((value['candidate_security_count'],value['candidate_issuer_count'],value['bounded_source_missing_count']),(78,77,23))
        for i in list(range(25))+list(range(78,101)): self.assertEqual(value['rows'][i],args[0]['rows'][i])
        for key in module.SIDECARS:self.assertEqual(value[key],args[0][key])
        self.assertEqual(value['bulk_extended_provenance'][0]['complete_link_row'],args[1]['links'][0])
        self.assertFalse(value['legal_training_input_admitted'])

    def test_wrong_cik_title_or_issuer_cannot_be_used(self):
        for mutate in (
            lambda a:a[1]['links'][0]['link']['all_cik_links'][0]['cik_fact'].update(resolved_text='999'),
            lambda a:a[1]['links'][0]['link']['all_cik_links'][0].update(cik_matches_review_issuer=False),
            lambda a:a[1]['links'][0]['link']['selected_title_fact'].update(resolved_text='Notes'),
            lambda a:a[1]['links'][0]['link']['original_queue_item']['review_match']['decision'].update(issuer_id='issuer:9999999999'),
        ):
            args=fixture();mutate(args)
            with self.assertRaises(ValueError):module.assemble_bulk_conditional_wiring(*args)

    def test_nonmatching_legal_entity_preserved_not_used(self):
        args=fixture();item=copy.deepcopy(args[1]['links'][0]['link']['all_cik_links'][0])
        item.update(cik_matches_review_issuer=False,cik_review_issuer_match_status='MISMATCH')
        item['cik_fact']['resolved_text']='999';args[1]['links'][0]['link']['all_cik_links'].append(item)
        value=module.assemble_bulk_conditional_wiring(*args)
        self.assertEqual(value['nonmatching_cik_link_count_preserved'],1)
        self.assertEqual(len(value['bulk_extended_provenance'][0]['selected_matching_cik_links']),1)
        self.assertEqual(len(value['bulk_extended_provenance'][0]['complete_link_row']['link']['all_cik_links']),2)

    def test_existing_namespace_and_boolean_index_rejected(self):
        args=fixture();args[1]['links'][0]['inventory_row_index']=True
        with self.assertRaises(ValueError):module.assemble_bulk_conditional_wiring(*args)
        with tempfile.TemporaryDirectory() as temporary,patch.object(module,'OUTPUT',Path(temporary)):
            with self.assertRaisesRegex(ValueError,'exists'):module.run()

    def test_old_transition_proofs_nested_not_current_claim(self):
        args=fixture();args[0].update(unchanged_other100_exact=True,unchanged_other100_sha256='b'*64,unchanged_other99_exact=True,capture_queue_count=104)
        value=module.assemble_bulk_conditional_wiring(*args)
        self.assertFalse(any(key.startswith('unchanged_') for key in value))
        self.assertEqual(value['parent_v6_transition_proofs_preserved'],{key:val for key,val in args[0].items() if key.startswith('unchanged_')})
        self.assertTrue(value['old25_and_unlinked23_exact'])
        self.assertEqual(value['capture_queue_count'],104)
        self.assertIn('INHERITED_PARENT',value['capture_queue_count_scope'])

    def test_historical_denominator_and_actual_late_date(self):
        args=fixture();args[1]['historical_denominators'].pop()
        with self.assertRaisesRegex(ValueError,'Full15'):module.assemble_bulk_conditional_wiring(*args)
        args=fixture();link=args[1]['links'][0]['link']
        link['saved_review_date_fields']['selection_date']['value']='2020-01-01'
        link['original_queue_item']['review_match']['decision']['selection_date']='2020-01-01'
        with self.assertRaisesRegex(ValueError,'actually postdate'):module.assemble_bulk_conditional_wiring(*args)


if __name__=='__main__':unittest.main()

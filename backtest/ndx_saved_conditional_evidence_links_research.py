"""Explicit, retrospective saved-evidence links; no parser, I/O or admission."""
from copy import deepcopy
from datetime import date
import json

SCHEMA='SAVED_CONDITIONAL_EVIDENCE_LINKS_RESEARCH_V1'
WINDOW={'first':'2026-03-20','last':'2026-09-21'}
FALSE=dict.fromkeys(('point_in_time_verified','provider_identity_verified','provider_binding_verified','identity_interval_verified',
    'risk_interval_verified','legal_training_input_admitted','promotion_allowed','candidate_seal_allowed',
    'cohort_registration_allowed','execution_authorized','fit_performed','prices_recomputed',
    'source_bytes_authenticated_by_this_module','claimed_section_hashes_reverified',
    'cross_document_identity_certified','holdings_conversion_performed','early_window_review_availability_verified'),False)


def require(ok,message):
    if not ok: raise ValueError(message)


def reference(value, pointer=False):
    require(type(value) is dict and set(value)==({'path','sha256','json_pointer'} if pointer else {'path','sha256'}),'Reference schema')
    require(type(value['path']) is str and bool(value['path'].strip()),'Reference path')
    require(type(value['sha256']) is str and len(value['sha256'])==64 and all(c in '0123456789abcdef' for c in value['sha256']),'Reference SHA')
    if pointer: require(type(value['json_pointer']) is str and value['json_pointer'].startswith('/') and len(value['json_pointer'])>1,'Review contract row pointer')


def pointer(ref,path): return {**deepcopy(ref),'json_pointer':path}


def link_saved_conditional_evidence(*,queue_item,extracted_document,document_reference,
                                    selection_contract,assumed_window):
    require(assumed_window==WINDOW,'Explicit fixed conditional research window required')
    reference(document_reference);reference(selection_contract['reviewed_contract_reference'],True)
    require(type(queue_item) is dict and type(selection_contract) is dict,'Input mappings required')
    ticker=queue_item['ticker']; rawref=queue_item['raw_reference']; reference(rawref)
    review_match=queue_item['review_match'];review=review_match['decision']
    review_issuer=review['issuer_id']
    require(type(review_issuer) is str and review_issuer.startswith('issuer:') and
            len(review_issuer)==17 and review_issuer[7:].isascii() and review_issuer[7:].isdigit(), 'Explicit canonical review issuer required')
    require(review_match['raw_reference']==rawref and review['raw_sha256']==rawref['sha256'],'Review/raw mismatch')
    require(extracted_document['status']=='EXTRACTED_SAVED_FACTS_NOT_IDENTITY_ADMISSION' and
            extracted_document['raw_sha256']==rawref['sha256'] and rawref in extracted_document['raw_references'], 'Saved extracted document mismatch')
    require(review_match in extracted_document['original_review_matches'],'Original review not in document')
    extraction=extracted_document['extraction']
    require(extraction['schema']=='SAVED_SEC_COVER_EVIDENCE_RESEARCH_V1' and extraction['raw_sha256']==rawref['sha256'],'Extraction schema/raw mismatch')
    for key in ('point_in_time_verified','promotion_allowed','cover_cusip_identity_verified','claimed_section_hashes_reverified'):
        require(extraction[key] is False,'Extraction authority changed')
    require(selection_contract['ticker']==ticker and selection_contract['raw_sha256']==rawref['sha256']
        and selection_contract['document_reference']==document_reference,'Selection source mismatch')
    require(type(selection_contract['inventory_row_index']) is int and
        selection_contract['inventory_row_index']==queue_item['inventory_row_index'],'Selection row mismatch')
    groups=extraction['same_context_security_groups'];facts=extraction['dei_facts'];contexts=extraction['contexts']
    require(type(groups) is list and type(facts) is list and type(contexts) is list and len(groups)<=10000 and len(facts)<=10000,'Bounded saved facts')
    require(selection_contract['all_security_groups']==groups,'Selection omitted alternatives')
    candidates=[]; links=[]; cik_indexes=extraction['cik_fact_indexes']
    for index in cik_indexes:
        require(type(index) is int and 0<=index<len(facts) and facts[index]['name'].split(':')[-1].lower()=='entitycentralindexkey','CIK fact index')
    def context_matches(context_ref): return [c for c in contexts if c['context_id']==context_ref]
    def signature(values): return sorted(json.dumps(item,sort_keys=True,ensure_ascii=False) for item in values)
    for group_index,group in enumerate(groups):
        for key in ('ticker_fact_indexes','title_fact_indexes'):
            require(all(type(i) is int and 0<=i<len(facts) and facts[i]['context_ref']==group['context_ref'] for i in group[key]),'Group fact binding')
        if not any(facts[i]['resolved_text']==ticker for i in group['ticker_fact_indexes']): continue
        candidates.append({'group_index':group_index,'group':deepcopy(group),
            'reference':pointer(document_reference,'/extraction/same_context_security_groups/'+str(group_index)),
            'contexts':deepcopy(context_matches(group['context_ref']))})
        targets=context_matches(group['context_ref'])
        for fact_index in cik_indexes:
            fact=facts[fact_index]; origins=context_matches(fact['context_ref'])
            raw_cik=fact['resolved_text']
            normalized_cik=(raw_cik.zfill(10) if type(raw_cik) is str and 1<=len(raw_cik)<=10
                and raw_cik.isascii() and raw_cik.isdigit() else None)
            issuer_matches=None if normalized_cik is None else 'issuer:'+normalized_cik==review_issuer
            relation='UNRESOLVED_CONTEXT_OR_ENTITY_PERIOD_MISMATCH'
            if len(targets)==len(origins)==1 and fact['continuation_complete'] is True:
                if fact['context_ref']==group['context_ref']: relation='EXACT_CONTEXT_DECLARED_CIK_LINK'
                elif targets[0]['identifiers'] and targets[0]['periods'] and origins[0]['identifiers'] and origins[0]['periods'] and signature(targets[0]['identifiers'])==signature(origins[0]['identifiers']) and signature(targets[0]['periods'])==signature(origins[0]['periods']):
                    relation='CROSS_CONTEXT_EQUAL_IDENTIFIERS_AND_PERIODS_CONDITIONAL_LINK'
            links.append({'group_index':group_index,'cik_fact_index':fact_index,'relation':relation,
                'normalized_cik':normalized_cik,'review_issuer_id':review_issuer,
                'cik_matches_review_issuer':issuer_matches,
                'cik_review_issuer_match_status':('UNKNOWN_INVALID_CIK_TEXT' if issuer_matches is None else
                    'MATCH' if issuer_matches else 'MISMATCH'),
                'cik_fact':deepcopy(fact),'cik_contexts':deepcopy(origins),'security_contexts':deepcopy(targets),
                'reference':pointer(document_reference,'/extraction/dei_facts/'+str(fact_index)),
                'dimensions_merged':False,'identity_certified':False})
    selected=selection_contract['selected_group_indexes']
    require(type(selected) is list and all(type(i) is int for i in selected) and selected==sorted(set(selected)) and
            set(selected)<={item['group_index'] for item in candidates},'Explicit matching group selection required')
    title_index=selection_contract.get('selected_title_fact_index')
    selected_title=None
    if selected:
        require(type(title_index) is int and 0<=title_index<len(facts) and any(title_index in groups[i]['title_fact_indexes'] for i in selected),'Explicit title fact required')
        selected_title=facts[title_index]
        require(selected_title['resolved_text']==selection_contract['exact_title'] and selected_title['context_ref']==selection_contract['context_ref']
                and selected_title['continuation_complete'] is True,'Exact selected title/context mismatch')
    else:
        require(title_index is None and selection_contract.get('exact_title') is None and selection_contract.get('context_ref') is None,'Unselected contract must have null title')
    coordinates=deepcopy(queue_item['resolved_identity_coordinates'])
    for coordinate in coordinates:
        require(coordinate['security_id']=='security:'+coordinate['issuer_id'].split(':',1)[1]+':'+coordinate['cusip'],'Saved coordinate inconsistent')
        require(any(item['row'].get('security_id')==coordinate['security_id'] and item['row'].get('issuer_id')==coordinate['issuer_id'] and item['row'].get('cusip')==coordinate['cusip'] for item in queue_item['identity_matches']),'Coordinate missing original identity evidence')
    date_fields={}
    for key in ('effective_from','effective_to','evidence_available_date','selection_date','report_date','filing_date','fetched_at','received_at','actual_extracted_at'):
        value=review.get(key)
        date_fields[key]={'value':value if value not in ('',None) else None,
            'source_reference':deepcopy(review_match['reference']),
            'missing_reason':None if value not in ('',None) else 'FIELD_ABSENT_OR_EMPTY_IN_SAVED_REVIEW_NOT_INFERRED'}
    selection_date=date_fields['selection_date']['value']
    late=None
    if selection_date is not None:
        parsed=date.fromisoformat(selection_date);require(parsed.isoformat()==selection_date,'Canonical review selection date')
        late=selection_date>WINDOW['first']
    return {'schema':SCHEMA,'ticker':ticker,'original_queue_item':deepcopy(queue_item),
        'document_reference':deepcopy(document_reference),'raw_source_reference':deepcopy(rawref),
        'reviewed_selection_contract_preserved':deepcopy(selection_contract),'assumed_window':deepcopy(WINDOW),
        'all_security_groups_preserved':deepcopy(groups),'ticker_matching_groups':candidates,'all_cik_links':links,
        'selected_group_indexes':deepcopy(selected),'selected_title_fact':deepcopy(selected_title),
        'selected_title_reference':pointer(document_reference,'/extraction/dei_facts/'+str(title_index)) if selected else None,
        'original_resolved_coordinates':coordinates,'saved_risk_chain':review.get('risk_chain'),
        'resolved_coordinate_review_issuer_matches':[{'coordinate':deepcopy(coordinate),
            'review_issuer_id':review_issuer,'issuer_matches':coordinate['issuer_id']==review_issuer} for coordinate in coordinates],
        'saved_review_date_fields':date_fields,'review_selection_postdates_window_start':late,
        'status':'EXPLICIT_CONDITIONAL_RESEARCH_LINKS_ONLY' if selected else 'NO_EXPLICIT_TITLE_SELECTION',
        'cusip_link_scope':'SAVED_IDENTITY_AND_NPORT_CROSS_DOCUMENT_ASSUMPTION_NOT_SEC_COVER_CUSIP_PROOF',
        'window_assumption':'RETROSPECTIVE_CONTINUOUS_IDENTITY_AND_SAVED_RISK_REUSE_ASSUMPTION_NOT_EARLY_AVAILABILITY',
        'special_class_assumption_preserved':deepcopy(selection_contract.get('special_class_assumption')),
        'class_handling_preserved':deepcopy(selection_contract.get('class_handling')),
        'supporting_evidence_preserved':deepcopy(selection_contract.get('supporting_evidence')),
        'original_review_risk_reclassified':False,**FALSE}

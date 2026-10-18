"""Append 53 explicit retrospective evidence connections; preserve all old rows."""
import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/bulk_conditional_wiring_20261003_v1'
PINS={
 'parent':('data/cache/research/new_cutoff_identity_risk_wiring_20260925_v6/wiring.json','1252cddfd4274ce8ce1f6a50c7e356fb790f45309bdd7146d71d317a754fd0fd'),
 'links':('data/cache/research/saved_conditional_evidence_links_20261002_v1/links.json','e139415eac84896e71148be9971b316c04970b20ab842995fbb6f4580948e3a7'),
 'publication':('data/cache/research/saved_conditional_evidence_links_20261002_v1/publication.json','d5c3a14a0f95d28e9065ad95f1da1211989bcd4eb154dd30cf3e09502e3a0cf1'),
 'independent_readback':('DYNAMIC_SAVED_CONDITIONAL_EVIDENCE_LINKS_INDEPENDENT_READBACK_20261002.md','0411e984bd2d77b02e71abd8ecc7466ad8221e4896e0d469f3dacdddc0768ada')}
WINDOW={'first':'2026-03-20','last':'2026-09-21'}
SIDECARS=('original19_exact_proof','extended_provenance','v3_extended_provenance','v4_extended_provenance','v5_extended_provenance','v6_extended_provenance')
FLAGS=dict.fromkeys(('identity_interval_verified','provider_binding_verified','risk_interval_verified','point_in_time_verified',
 'historical_membership_verified','complete_corporate_actions_verified','legal_training_input_admitted','promotion_allowed',
 'fit_performed','execution_authorized','http_performed','prices_recomputed','old_build_called','original_windows_extended',
 'full_transitive_source_closure_reverified'),False)


def require(ok,message):
    if not ok: raise ValueError(message)


def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw): return hashlib.sha256(raw).hexdigest()


def assemble_bulk_conditional_wiring(parent_v6,links,links_ref):
    require(parent_v6['schema']=='NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V6' and
            links['schema']=='SOURCE_BOUND_SAVED_CONDITIONAL_EVIDENCE_LINKS_V1','Parent schemas')
    require(set(links_ref)=={'path','sha256'} and type(links_ref['sha256']) is str and len(links_ref['sha256'])==64,'Links reference')
    require(all(parent_v6[key] is False for key in FLAGS),'Parent authority changed')
    for key in ('point_in_time_verified','identity_interval_verified','provider_binding_verified','risk_interval_verified','legal_training_input_admitted','promotion_allowed','fit_performed'):
        require(links[key] is False,'Links authority changed')
    rows=deepcopy(parent_v6['rows']); original=parent_v6['rows']
    require(len(rows)==len({r['ticker'] for r in rows})==101 and len(links['rows'])==101 and len(links['links'])==53,'Complete denominators')
    require(type(links['historical_denominators']) is list and len(links['historical_denominators'])==15,'Full15 historical denominator required')
    require(sum(row['coordinate'] is not None for row in rows)==25,'Old25 denominator')
    require(links['assumed_window']==WINDOW and len(parent_v6['calendar'])==127 and
            parent_v6['calendar'][0]==WINDOW['first'] and parent_v6['calendar'][-1]==WINDOW['last'],'Window differs')
    for index,item in enumerate(links['rows']):
        require(item['ticker']==rows[index]['ticker'] and
            canonical(item['original_inventory_row']['original_wiring_row'])==canonical(rows[index]),'Original101 wiring linkage differs')
    provenance=[];changed=set();mismatch_count=0;late_annual=[]
    for link_index,item in enumerate(links['links']):
        index=item['inventory_row_index'];require(type(index) is int and 0<=index<101 and index not in changed,'Unique linked index')
        changed.add(index);row=rows[index];old=deepcopy(row);link=item['link']
        require(row['ticker']==item['ticker']==link['ticker'] and row['coordinate'] is None and row['risk_chain'] is None,'Only original null row may change')
        require(links['rows'][index]['new_link_index']==link_index,'Link index linkage')
        require(all(row[key] is False for key in FLAGS),'Row authority changed')
        require(link['assumed_window']==WINDOW and link['status']=='EXPLICIT_CONDITIONAL_RESEARCH_LINKS_ONLY','Conditional link status')
        for key in ('point_in_time_verified','provider_binding_verified','identity_interval_verified','risk_interval_verified','legal_training_input_admitted','fit_performed'):
            require(link[key] is False,'Link authority changed')
        coordinates=link['original_resolved_coordinates'];require(len(coordinates)==1,'Unique saved SID coordinate required')
        coordinate=deepcopy(coordinates[0]);issuer=coordinate['issuer_id']
        require(issuer.startswith('issuer:') and len(issuer)==17 and issuer[7:].isascii() and issuer[7:].isdigit() and
            coordinate['security_id']=='security:'+issuer[7:]+':'+coordinate['cusip'],'Exact SID/issuer/CUSIP')
        contract=item['selection_contract'];require(contract==link['reviewed_selection_contract_preserved'],'Selection contract drift')
        selected=link['selected_group_indexes'];require(type(selected) is list and len(selected)==1 and type(selected[0]) is int,'Explicit single selected group')
        group_index=selected[0];groups=link['all_security_groups_preserved']
        require(0<=group_index<len(groups) and contract['selected_group_indexes']==selected and contract['all_security_groups']==groups,'All alternatives preserved')
        title=link['selected_title_fact'];title_index=contract['selected_title_fact_index'];group=groups[group_index]
        require(any(candidate['group_index']==group_index and candidate['group']==group for candidate in link['ticker_matching_groups']), 'Selected group not ticker-matching')
        require(type(title_index) is int and title_index in group['title_fact_indexes'] and
            title['resolved_text']==contract['exact_title'] and title['context_ref']==group['context_ref']==contract['context_ref'] and
            title['continuation_complete'] is True,'Explicit complete selected title')
        queue=link['original_queue_item'];review=queue['review_match']['decision']
        require(review['issuer_id']==issuer and review['status']=='accepted' and review['risk_chain']==link['saved_risk_chain'] and
            type(link['saved_risk_chain']) is str and bool(link['saved_risk_chain']),'Saved issuer/risk review linkage')
        require(link['resolved_coordinate_review_issuer_matches']==[{'coordinate':coordinate,'review_issuer_id':issuer,'issuer_matches':True}],'Coordinate issuer match')
        accepted=[]
        for ciklink in link['all_cik_links']:
            if ciklink['cik_review_issuer_match_status']=='MISMATCH': mismatch_count+=1
            if ciklink['group_index']!=group_index or ciklink['cik_matches_review_issuer'] is not True: continue
            raw=ciklink['cik_fact']['resolved_text']
            require(type(raw) is str and raw.isascii() and raw.isdigit() and 1<=len(raw)<=10 and raw.zfill(10)==issuer[7:]
                and ciklink['normalized_cik']==issuer[7:] and ciklink['review_issuer_id']==issuer and ciklink['cik_review_issuer_match_status']=='MATCH','CIK numeric match differs')
            require(ciklink['relation'] in {'EXACT_CONTEXT_DECLARED_CIK_LINK','CROSS_CONTEXT_EQUAL_IDENTIFIERS_AND_PERIODS_CONDITIONAL_LINK'}
                and ciklink['dimensions_merged'] is False and ciklink['identity_certified'] is False,'CIK relation not approved')
            origins=ciklink['cik_contexts'];targets=ciklink['security_contexts']
            require(len(origins)==len(targets)==1 and targets[0]['context_id']==group['context_ref'] and
                origins[0]['context_id']==ciklink['cik_fact']['context_ref'],'CIK context binding')
            if ciklink['relation']=='EXACT_CONTEXT_DECLARED_CIK_LINK':
                require(origins[0]['context_id']==targets[0]['context_id'],'Exact context differs')
            else:
                require(origins[0]['context_id']!=targets[0]['context_id'] and origins[0]['identifiers'] and origins[0]['periods'] and
                    sorted(canonical(v) for v in origins[0]['identifiers'])==sorted(canonical(v) for v in targets[0]['identifiers']) and
                    sorted(canonical(v) for v in origins[0]['periods'])==sorted(canonical(v) for v in targets[0]['periods']), 'Cross-context entity/period mismatch')
            accepted.append(deepcopy(ciklink))
        require(accepted,'Selected class lacks issuer-matching CIK evidence')
        require(link['review_selection_postdates_window_start'] is True and link['saved_review_date_fields']['selection_date']['value']==review['selection_date'],'Late review evidence')
        require(type(review['selection_date']) is str and date.fromisoformat(review['selection_date']).isoformat()==review['selection_date']
            and review['selection_date']>WINDOW['first'],'Review must actually postdate window start')
        available=link['saved_review_date_fields']['evidence_available_date']['value']
        if available is not None and available>WINDOW['first']: late_annual.append(row['ticker'])
        coordinate.update(ticker=row['ticker'],security_class=title['resolved_text'])
        row.update(coordinate=coordinate,risk_chain=link['saved_risk_chain'],
            identity_risk_state='CONDITIONAL_SAVED_SEC_CLASS_AND_CROSS_DOCUMENT_COORDINATE_RESEARCH_ONLY',
            new_assumption={'scope':'CONDITIONAL_RETROSPECTIVE_RESEARCH_ONLY','window':deepcopy(WINDOW),
                'security_continuity_is_explicit_assumption':True,'risk_label_persistence_is_explicit_assumption':True,
                'cross_document_identity_connection_is_explicit_assumption':True,'interval_certified':False,
                'source_interval_extended':False,'provider_binding_verified':False},
            risk_sources=[{'source':{**links_ref,'json_pointer':f'/links/{link_index}/link'},
                'source_kind':'BULK_SAVED_CONDITIONAL_SEC_EVIDENCE_LINK','risk_chain':link['saved_risk_chain']}],
            bulk_extended_provenance_reference={'json_pointer':f'/bulk_extended_provenance/{link_index}'},
            bulk_class_handling=deepcopy(link['class_handling_preserved']))
        gap='NO_DATED_COORDINATE_AND_RISK_ASSEMBLED_FROM_SELECTED_SOURCES'
        require(row['gaps'].count(gap)==1,'Original null gap missing')
        row['gaps']=[g for g in row['gaps'] if g!=gap]+['SAVED_REVIEW_POSTDATES_WINDOW_START_NO_EARLY_AVAILABILITY_PROOF',
            'CROSS_DOCUMENT_CUSIP_CLASS_CONNECTION_CONDITIONAL_NOT_CERTIFIED','IDENTITY_AND_RISK_WINDOW_PERSISTENCE_ASSUMED_NOT_VERIFIED']
        provenance.append({'ticker':row['ticker'],'original_null_row':old,
            'links_reference':{**links_ref,'json_pointer':f'/links/{link_index}'},'complete_link_row':deepcopy(item),
            'selected_matching_cik_links':accepted,'all_nonmatching_cik_evidence_preserved':True,
            'new_window_assumption':deepcopy(row['new_assumption']),'selected_sec_title':title['resolved_text'],
            'class_handling':deepcopy(link['class_handling_preserved']),'prior_facts_modified':False})
    require(len(changed)==53 and all(canonical(rows[i])==canonical(original[i]) for i in range(101) if i not in changed),'Unchanged48 row invariant')
    candidates=[row for row in rows if row['coordinate'] is not None]
    require(len(candidates)==len({row['coordinate']['security_id'] for row in candidates})==78 and
            len({row['coordinate']['issuer_id'] for row in candidates})==77,'Derived78SID77issuer without collision')
    value=deepcopy(parent_v6);value.pop('source_hashes',None)
    inherited_proofs={key:value.pop(key) for key in list(value) if key.startswith('unchanged_')}
    value.update(schema='BULK_CONDITIONAL_IDENTITY_RISK_WIRING_V1',rows=rows,bulk_extended_provenance=provenance,
        parent_v6_transition_proofs_preserved=inherited_proofs,
        parent_v6_transition_proof_scope='OLD_PARENT_TRANSITIONS_ONLY_NOT_THIS_53_ROW_INCREMENT',
        capture_queue_count_scope='INHERITED_PARENT_CAPTURE_QUEUE_NOT_THIS_53_CONNECTION_BATCH',
        parent_v6_input_references_preserved=deepcopy(parent_v6['input_references']),bulk_links_reference=deepcopy(links_ref),
        historical_denominators_preserved=deepcopy(links['historical_denominators']),candidate_security_count=78,
        candidate_issuer_count=77,bounded_source_missing_count=23,fit_column_count=None,typed_panel_rebuilt=False,
        new_conditional_connection_count=53,old25_and_unlinked23_exact=True,late_review_count=53,
        late_annual_tickers=late_annual,nonmatching_cik_link_count_preserved=mismatch_count)
    require(all(canonical(value[key])==canonical(parent_v6[key]) for key in SIDECARS),'Six old sidecars changed')
    return value


def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source drift')
    for path,digest in sources.items(): require(sha(Path(path).read_bytes())==digest,'Pinned source drift')


def write_new(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream: stream.write(raw);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Output readback differs')
    return {'path':str(path),'sha256':sha(raw)}


def run():
    require(not OUTPUT.exists(),'Fixed namespace exists; no retry')
    sources={str(SOURCE):LOADED_SHA};docs={};refs={}
    for role,(relative,digest) in PINS.items():
        path=ROOT/relative;raw=path.read_bytes();require(sha(raw)==digest,'Hard source mismatch')
        sources[str(path)]=digest;refs[role]={'path':str(path),'sha256':digest}
        if role!='independent_readback': docs[role]=json.loads(raw)
    require(docs['publication']['links_reference']==refs['links'] and docs['publication']['source_hashes']==docs['links']['source_hashes']
        and docs['publication']['status']=='PUBLISHED_CONDITIONAL_LINKS_NO_ADMISSION','Links publication mismatch')
    guard(sources);OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json',{'source_hashes':sources,'retry_allowed':False,**FLAGS})
        value=assemble_bulk_conditional_wiring(docs['parent'],docs['links'],refs['links'])
        value.update(source_hashes=sources,input_references=refs)
        guard(sources);result=write_new(OUTPUT/'wiring.json',value);guard(sources)
        publication=write_new(OUTPUT/'publication.json',{'schema':'BULK_CONDITIONAL_WIRING_PUBLICATION_V1',
            'status':'PUBLISHED_CONDITIONAL_METADATA_ONLY','wiring_reference':result,'source_hashes':sources,**FLAGS})
        guard(sources)
        require(sha(Path(result['path']).read_bytes())==result['sha256'] and sha(Path(publication['path']).read_bytes())==publication['sha256'],'Published readback changed')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','wiring.json','publication.json'},'Unexpected output')
        return {'wiring_reference':result,'publication_reference':publication}
    except Exception as error:
        write_new(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error),'retry_allowed':False});raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute: parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))

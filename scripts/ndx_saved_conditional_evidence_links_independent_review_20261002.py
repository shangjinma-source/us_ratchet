"""Independent saved-JSON linkage readback; no production imports or HTML parsing."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/cache/research/saved_conditional_evidence_links_20261002_v1'
RESULT_SHA='e139415eac84896e71148be9971b316c04970b20ab842995fbb6f4580948e3a7'
PUB_SHA='d5c3a14a0f95d28e9065ad95f1da1211989bcd4eb154dd30cf3e09502e3a0cf1'
def check(ok,label):
 if not ok:raise ValueError(label)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def exact(a,b):return json.dumps(a,sort_keys=True,ensure_ascii=False)==json.dumps(b,sort_keys=True,ensure_ascii=False)
def rawref(r):
 raw=Path(r['path']).read_bytes();check(sha(raw)==r['sha256'],'source '+r['path']);return raw
def read(r):return json.loads(rawref(r))
def ptr(r,p):return dict(r,json_pointer=p)
def signature(v):return sorted(json.dumps(x,sort_keys=True,ensure_ascii=False) for x in v)
def checkflags(d):
 for k,v in d.items():
  if k in {'point_in_time_verified','identity_interval_verified','provider_binding_verified','provider_identity_verified','risk_interval_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','full_universe_coverage_verified','fit_performed','http_performed','old_audit_called','prices_recomputed','filing_raw_bytes_reparsed','parent_wiring_modified','panel_modified','full_transitive_source_closure_reverified','original_review_risk_reclassified','candidate_seal_allowed','cohort_registration_allowed','source_bytes_authenticated_by_this_module','claimed_section_hashes_reverified','cross_document_identity_certified','holdings_conversion_performed','early_window_review_availability_verified'}:check(v is False,'authority '+k)
def verify():
 resultref={'path':str(OUT/'links.json'),'sha256':RESULT_SHA};x=read(resultref);pub=read({'path':str(OUT/'publication.json'),'sha256':PUB_SHA});start=json.loads((OUT/'started.json').read_bytes())
 check(pub['links_reference']==resultref and pub['status']=='PUBLISHED_CONDITIONAL_LINKS_NO_ADMISSION','publication')
 check(exact(x['source_hashes'],pub['source_hashes']) and exact(x['source_hashes'],start['source_hashes']),'source maps')
 refs=x['input_references'];batch=read(refs['batch']);contract=read(refs['selection']);inv=batch['inventory_preserved']
 expected_sources={str(ROOT/'scripts/ndx_saved_conditional_evidence_links_20261002.py'):'48482872e4a362aaa51a88a1ecea5312c4b79043465ec0585cc1fcf3a63878f0'}
 for r in list(refs.values())+list(batch['document_references'].values()):
  check(r['path'] not in expected_sources or expected_sources[r['path']]==r['sha256'],'source conflict');expected_sources[r['path']]=r['sha256']
 check(x['source_hashes']==expected_sources,'complete direct source closure')
 for p,h in expected_sources.items():rawref({'path':p,'sha256':h})
 receipt=read(refs['publication']);check(receipt['batch_reference']==refs['batch'] and receipt['source_hashes']==batch['source_hashes'],'parent receipt')
 asml=read(refs['asml_evidence']);ap=read(refs['asml_publication']);check(ap['identity_reference']==refs['asml_evidence'] and ap['source_hashes']==asml['source_hashes'],'ASML receipt')
 check(exact(x['supplemental_saved_evidence'],{'asml':asml}),'ASML complete payload')
 check(exact(x['selection_contract_preserved'],contract) and contract['batch_reference']==refs['batch'],'contract complete')
 check(exact(x['historical_denominators'],inv['historical_denominators']) and len(x['historical_denominators'])==15,'historical15')
 check(exact(x['inventory_summary_preserved'],inv['summary']),'inventory summary')
 check(x['saved_parent_inventory_reference']==ptr(refs['batch'],'/inventory_preserved'),'inventory reference')
 check(x['assumed_window']==contract['assumed_window']=={'first':'2026-03-20','last':'2026-09-21'},'window')
 queue=inv['extraction_queue'];check(len(queue)==len(x['links'])==len(contract['rows'])==53,'53 links')
 check(len(x['rows'])==len(inv['rows'])==101,'101 rows')
 index_map={q['inventory_row_index']:i for i,q in enumerate(queue)};relations={};matches={'MATCH':0,'MISMATCH':0,'UNKNOWN':0};dates=0
 for i,(q,wrapper,choice) in enumerate(zip(queue,x['links'],contract['rows'])):
  digest=q['raw_reference']['sha256'];dref=batch['document_references'][digest];doc=read(dref);e=doc['extraction'];f=e['dei_facts'];groups=e['same_context_security_groups'];contexts=e['contexts'];link=wrapper['link']
  check(wrapper['inventory_row_index']==q['inventory_row_index'] and wrapper['ticker']==q['ticker'],'wrapper identity')
  check(wrapper['queue_reference']==ptr(refs['batch'],'/inventory_preserved/extraction_queue/'+str(i)) and wrapper['document_reference']==dref,'queue/doc refs')
  chosen=dict(choice,reviewed_contract_reference=ptr(refs['selection'],'/rows/'+str(i)))
  check(exact(wrapper['selection_contract'],chosen) and exact(link['reviewed_selection_contract_preserved'],chosen),'selection copy')
  check(exact(link['original_queue_item'],q) and exact(link['original_resolved_coordinates'],q['resolved_identity_coordinates']),'queue/nport/fullcoordinates preserved')
  check(link['document_reference']==dref and link['raw_source_reference']==q['raw_reference'] and link['ticker']==q['ticker'],'link raw/doc refs')
  check(exact(link['all_security_groups_preserved'],groups) and exact(choice['all_security_groups'],groups),'all alternatives')
  selected=choice['selected_group_indexes'];j=choice['selected_title_fact_index'];check(selected==link['selected_group_indexes'] and len(selected)==1,'explicit selection')
  check(j in groups[selected[0]]['title_fact_indexes'] and f[j]['resolved_text']==choice['exact_title'] and f[j]['context_ref']==choice['context_ref'],'selected title/context')
  check(exact(link['selected_title_fact'],f[j]) and link['selected_title_reference']==ptr(dref,'/extraction/dei_facts/'+str(j)),'title evidence')
  expected_candidates=[];expected_links=[];review=q['review_match']['decision'];issuer=review['issuer_id']
  for gi,g in enumerate(groups):
   if not any(f[t]['resolved_text']==q['ticker'] for t in g['ticker_fact_indexes']):continue
   targets=[c for c in contexts if c['context_id']==g['context_ref']]
   expected_candidates.append({'group_index':gi,'group':g,'reference':ptr(dref,'/extraction/same_context_security_groups/'+str(gi)),'contexts':targets})
   for ci in e['cik_fact_indexes']:
    fact=f[ci];origins=[c for c in contexts if c['context_id']==fact['context_ref']];relation='UNRESOLVED_CONTEXT_OR_ENTITY_PERIOD_MISMATCH'
    if len(targets)==len(origins)==1 and fact['continuation_complete'] is True:
     if fact['context_ref']==g['context_ref']:relation='EXACT_CONTEXT_DECLARED_CIK_LINK'
     elif targets[0]['identifiers'] and targets[0]['periods'] and origins[0]['identifiers'] and origins[0]['periods'] and signature(targets[0]['identifiers'])==signature(origins[0]['identifiers']) and signature(targets[0]['periods'])==signature(origins[0]['periods']):relation='CROSS_CONTEXT_EQUAL_IDENTIFIERS_AND_PERIODS_CONDITIONAL_LINK'
    text=fact['resolved_text'];normal=text.zfill(10) if isinstance(text,str) and 1<=len(text)<=10 and text.isascii() and text.isdigit() else None;match=None if normal is None else 'issuer:'+normal==issuer
    expected_links.append((gi,ci,relation,fact,origins,targets,normal,match));relations[relation]=relations.get(relation,0)+1;matches['UNKNOWN' if match is None else 'MATCH' if match else 'MISMATCH']+=1
  check(exact(link['ticker_matching_groups'],expected_candidates),'complete ticker candidates')
  check(len(link['all_cik_links'])==len(expected_links),'all CIK links')
  for actual,expected in zip(link['all_cik_links'],expected_links):
   gi,ci,relation,fact,origins,targets,normal,match=expected
   check(actual['group_index']==gi and actual['cik_fact_index']==ci and actual['relation']==relation,'relation independent')
   check(exact(actual['cik_fact'],fact) and exact(actual['cik_contexts'],origins) and exact(actual['security_contexts'],targets),'context/dimensions copies')
   check(actual['reference']==ptr(dref,'/extraction/dei_facts/'+str(ci)) and actual['dimensions_merged'] is False and actual['identity_certified'] is False,'CIK scope')
   check(actual['normalized_cik']==normal and actual['cik_matches_review_issuer'] is match and actual['review_issuer_id']==issuer,'CIK value match')
  check(exact(link['resolved_coordinate_review_issuer_matches'],[{'coordinate':c,'review_issuer_id':issuer,'issuer_matches':c['issuer_id']==issuer} for c in q['resolved_identity_coordinates']]),'coordinate issuer')
  for key in ('effective_from','effective_to','evidence_available_date','selection_date','report_date','filing_date','fetched_at','received_at','actual_extracted_at'):
   value=review.get(key);expected={'value':None if value in ('',None) else value,'source_reference':q['review_match']['reference'],'missing_reason':'FIELD_ABSENT_OR_EMPTY_IN_SAVED_REVIEW_NOT_INFERRED' if value in ('',None) else None}
   check(exact(link['saved_review_date_fields'][key],expected),'review date '+key)
  late=None if not review.get('selection_date') else review['selection_date']>'2026-03-20';check(link['review_selection_postdates_window_start'] is late,'late review');dates+=late is True
  check(link['saved_risk_chain']==review.get('risk_chain'),'risk unchanged')
  for output,source in [('class_handling_preserved','class_handling'),('supporting_evidence_preserved','supporting_evidence'),('special_class_assumption_preserved','special_class_assumption')]:check(exact(link[output],choice.get(source)),source)
  if q['ticker']=='ASML':check(choice['class_handling']['source_references']=={'identity.json':refs['asml_evidence'],'publication.json':refs['asml_publication']} and choice['class_handling']['new_window_class_identity_verified'] is False,'ASML')
  if q['ticker']=='PDD':check(choice['class_handling']['ordinary_shares_per_ads']==4 and choice['class_handling']['holdings_conversion_performed'] is False and choice['class_handling']['price_conversion_performed'] is False,'PDD ADS')
  checkflags(wrapper);checkflags(link)
 for i,(row,original) in enumerate(zip(x['rows'],inv['rows'])):
  check(exact(row['original_inventory_row'],original) and row['ticker']==original['ticker'],'old row unchanged')
  check(row['parent_reference']==ptr(refs['batch'],'/inventory_preserved/rows/'+str(i)) and row['new_link_index']==index_map.get(i),'row links')
  status='NEW_SAVED_CONDITIONAL_EVIDENCE_LINK' if i in index_map else 'REUSE_EXISTING_CONDITIONAL_COORDINATE' if original['already_wired_conditional_coordinate'] else 'UNRESOLVED_SOURCE_LEADS_PRESERVED';check(row['status']==status,'row status');checkflags(row)
 expected_summary={'current_row_count':101,'historical_coordinate_count':15,'new_evidence_link_count':53,'preserved_existing_coordinate_count':25,'unlinked_source_lead_count':23,'new_typed_panel_column_count':0,'verified_pit_eligible_count':None}
 check(exact(x['summary'],expected_summary),'summary')
 for value in (x,pub,start):checkflags(value)
 check({p.name for p in OUT.iterdir()}=={'links.json','publication.json','started.json'},'namespace')
 return dict(status='PASS',**expected_summary,direct_sources=len(expected_sources),late_review_link_count=dates,cik_relations=relations,cik_matches=matches,result_sha256=RESULT_SHA,publication_sha256=PUB_SHA)
if __name__=='__main__':print(json.dumps(verify(),indent=2))

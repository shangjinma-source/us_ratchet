"""Independent bulk wiring metadata readback; no producer imports."""
import json,hashlib
from pathlib import Path
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'data/cache/research/bulk_conditional_wiring_20261003_v1'
SHA='e4f4328043254667ff334ebc7aaf0fe530d451339f5b9d4b1ba0a20c37b9b8a5';PUB='7f9ba6d89271fded96727e4dbfdd08ccc58ff249d352fddf5f97a8366f345e12'
def check(v,m):
 if not v:raise ValueError(m)
def raw(r):
 b=Path(r['path']).read_bytes();check(hashlib.sha256(b).hexdigest()==r['sha256'],'SHA '+r['path']);return b
def read(r):return json.loads(raw(r))
def exact(a,b):return json.dumps(a,sort_keys=True)==json.dumps(b,sort_keys=True)
def flags(x):
 for k in ('identity_interval_verified','provider_binding_verified','risk_interval_verified','point_in_time_verified','historical_membership_verified','complete_corporate_actions_verified','legal_training_input_admitted','promotion_allowed','fit_performed','execution_authorized','http_performed','prices_recomputed','old_build_called','original_windows_extended','full_transitive_source_closure_reverified'):check(x[k] is False,'authority '+k)
def verify():
 ref={'path':str(D/'wiring.json'),'sha256':SHA};v=read(ref);p=read({'path':str(D/'publication.json'),'sha256':PUB});s=json.loads((D/'started.json').read_bytes());refs=v['input_references']
 expected={str(ROOT/'scripts/ndx_bulk_conditional_wiring_20261003.py'):'9af5171c4e5d6c6d38ee2721a42b1e46da7b1de1195df6843c396387295322e3',**{r['path']:r['sha256'] for r in refs.values()}}
 check(len(expected)==5 and v['source_hashes']==p['source_hashes']==s['source_hashes']==expected,'complete5sources')
 for path,h in expected.items():raw({'path':path,'sha256':h})
 check(p['wiring_reference']==ref and p['status']=='PUBLISHED_CONDITIONAL_METADATA_ONLY','publication')
 parent=read(refs['parent']);links=read(refs['links']);lp=read(refs['publication']);check(lp['links_reference']==refs['links'] and lp['source_hashes']==links['source_hashes'],'links receipt')
 check(len(v['rows'])==len(parent['rows'])==101 and len(v['bulk_extended_provenance'])==53,'101/53')
 check(v['calendar']==parent['calendar'] and len(v['calendar'])==127,'calendar')
 check(exact(v['historical_denominators_preserved'],links['historical_denominators']) and len(v['historical_denominators_preserved'])==15,'15history')
 for key in ('original19_exact_proof','extended_provenance','v3_extended_provenance','v4_extended_provenance','v5_extended_provenance','v6_extended_provenance'):check(exact(v[key],parent[key]),'sixsidecar '+key)
 check(exact(v['parent_v6_transition_proofs_preserved'],{k:x for k,x in parent.items() if k.startswith('unchanged_')}) and not any(k.startswith('unchanged_') for k in v),'oldproof scopes')
 check(exact(v['parent_v6_input_references_preserved'],parent['input_references']),'old inputrefs')
 changed=set();relations={};late=[];mismatches=0;selected_count=0
 for i,(item,prov) in enumerate(zip(links['links'],v['bulk_extended_provenance'])):
  idx=item['inventory_row_index'];changed.add(idx);old=parent['rows'][idx];row=v['rows'][idx];link=item['link'];selected=link['selected_group_indexes'][0];issuer=link['original_resolved_coordinates'][0]['issuer_id'];review=link['original_queue_item']['review_match']['decision']
  check(exact(prov['original_null_row'],old) and exact(prov['complete_link_row'],item),'fulloriginal links/nonmatch')
  check(prov['links_reference']==dict(refs['links'],json_pointer='/links/'+str(i)),'linkpointer')
  check(old['coordinate'] is None and old['risk_chain'] is None,'oldnull')
  accepted=[]
  for c in link['all_cik_links']:
   if c['cik_review_issuer_match_status']=='MISMATCH':mismatches+=1
   if c['group_index']!=selected or c['cik_matches_review_issuer'] is not True:continue
   text=c['cik_fact']['resolved_text'];check(text.isascii() and text.isdigit() and text.zfill(10)==issuer[7:] and c['normalized_cik']==issuer[7:],'issuer value')
   origins=c['cik_contexts'];targets=c['security_contexts'];check(len(origins)==len(targets)==1,'unique contexts')
   relation='EXACT_CONTEXT_DECLARED_CIK_LINK' if origins[0]['context_id']==targets[0]['context_id'] else 'CROSS_CONTEXT_EQUAL_IDENTIFIERS_AND_PERIODS_CONDITIONAL_LINK'
   if relation.startswith('CROSS'):
    for field in ('identifiers','periods'):check(origins[0][field] and sorted(json.dumps(z,sort_keys=True) for z in origins[0][field])==sorted(json.dumps(z,sort_keys=True) for z in targets[0][field]),'crossentityperiod')
   check(c['relation']==relation and c['dimensions_merged'] is False and c['identity_certified'] is False,'conditional relation')
   accepted.append(c);relations[relation]=relations.get(relation,0)+1
  check(accepted and exact(prov['selected_matching_cik_links'],accepted),'matching selected only');selected_count+=len(accepted)
  check(prov['all_nonmatching_cik_evidence_preserved'] is True and prov['prior_facts_modified'] is False,'preserve flags')
  coord=deepcopy(link['original_resolved_coordinates'][0]);coord.update(ticker=old['ticker'],security_class=link['selected_title_fact']['resolved_text'])
  check(exact(row['coordinate'],coord) and row['risk_chain']==review['risk_chain']==link['saved_risk_chain'] and issuer==review['issuer_id'],'coordinate/risk')
  check(exact(row['bulk_class_handling'],link['class_handling_preserved']) and exact(prov['class_handling'],link['class_handling_preserved']),'ASML/PDD class unchanged')
  check(review['selection_date']>'2026-03-20' and link['review_selection_postdates_window_start'] is True,'late selection')
  date=link['saved_review_date_fields']['evidence_available_date']['value']
  if date and date>'2026-03-20':late.append(row['ticker'])
  missing='NO_DATED_COORDINATE_AND_RISK_ASSEMBLED_FROM_SELECTED_SOURCES'
  gap=[g for g in old['gaps'] if g!=missing]+['SAVED_REVIEW_POSTDATES_WINDOW_START_NO_EARLY_AVAILABILITY_PROOF','CROSS_DOCUMENT_CUSIP_CLASS_CONNECTION_CONDITIONAL_NOT_CERTIFIED','IDENTITY_AND_RISK_WINDOW_PERSISTENCE_ASSUMED_NOT_VERIFIED']
  check(row['gaps']==gap,'gap exact')
  allowed={'coordinate','risk_chain','identity_risk_state','new_assumption','risk_sources','bulk_extended_provenance_reference','bulk_class_handling','gaps'}
  check({k:x for k,x in row.items() if k not in allowed}=={k:x for k,x in old.items() if k not in allowed},'all other old fields')
  check(row['bulk_extended_provenance_reference']=={'json_pointer':'/bulk_extended_provenance/'+str(i)},'sidecar pointer')
  check(row['risk_sources']==[{'source':dict(refs['links'],json_pointer='/links/'+str(i)+'/link'),'source_kind':'BULK_SAVED_CONDITIONAL_SEC_EVIDENCE_LINK','risk_chain':link['saved_risk_chain']}],'risk pointer')
  check(exact(prov['new_window_assumption'],row['new_assumption']) and row['new_assumption']['window']=={'first':'2026-03-20','last':'2026-09-21'},'assumption window')
  for key in ('interval_certified','source_interval_extended','provider_binding_verified'):check(row['new_assumption'][key] is False,'assumption authority')
 for idx,row in enumerate(v['rows']):
  flags(row)
  if idx not in changed:check(exact(row,parent['rows'][idx]),'48oldrows')
 candidates=[r['coordinate'] for r in v['rows'] if r['coordinate'] is not None]
 check(len(changed)==53 and len(candidates)==len({c['security_id'] for c in candidates})==v['candidate_security_count']==78 and len({c['issuer_id'] for c in candidates})==v['candidate_issuer_count']==77,'derived candidate counts')
 check(v['nonmatching_cik_link_count_preserved']==mismatches==8 and v['late_review_count']==53 and v['late_annual_tickers']==late and len(late)==4,'mismatch/late counts')
 check(v['fit_column_count'] is None and v['typed_panel_rebuilt'] is False and v['bounded_source_missing_count']==23,'no panel upgrade')
 for value in (v,p,s):flags(value)
 check({p.name for p in D.iterdir()}=={'wiring.json','publication.json','started.json'},'namespace')
 return {'status':'PASS','rows':101,'new_rows':53,'old_rows_exact':48,'candidate_sid':78,'candidate_issuer':77,'historical':15,'old_sidecars_exact':6,'direct_sources':5,'selected_cik_links':selected_count,'relations':relations,'nonmatching_cik_preserved':mismatches,'late_review_count':53,'late_annual_tickers':late,'wiring_sha256':SHA,'publication_sha256':PUB}
if __name__=='__main__':print(json.dumps(verify(),indent=2))

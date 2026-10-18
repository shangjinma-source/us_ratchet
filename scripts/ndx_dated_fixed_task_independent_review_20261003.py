"""Independent actual dated input audit; no producer, optimizer or raw audit imports."""
from pathlib import Path
from collections import Counter
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/dated_fixed_task_preparation_20261003_v1'
SHA='ff24a6b732bc55ea6dbb7b453a41ff58d0f2ee316e3f2120aa4006f3b82d3d0e'
PUB='805fa9852e599448aa01461098f094f2d21344cc7d26053b208de342361383fe'
PARAMETERS=dict(fit_days=126,max_single_weight=.45,min_single_weight=.05,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55,shrinkage_intensity=.35,top_weight_cap=.8,turnover_anchor_strength=.25)
SPECS=['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor']
FULL=6222659648236112670
def check(v,m):
 if not v:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return sha(enc(v))
def exact(a,b,m):check(enc(a)==enc(b),m)
def read(p,h):
 b=Path(p).read_bytes();check(sha(b)==h,'SHA '+str(p));return b

def verify():
 document=json.loads(read(BASE/'preparation.json',SHA));pub=json.loads(read(BASE/'publication.json',PUB));started=json.loads((BASE/'started.json').read_bytes())
 check({p.name for p in BASE.iterdir()}=={'started.json','preparation.json','publication.json'},'Successful namespace')
 refs=document['input_references'];docs={};sources={}
 for role,r in refs.items():docs[role]=json.loads(read(r['path'],r['sha256']));sources[r['path']]=r['sha256']
 check(len(refs)==7,'Seven parents')
 for rel,h in [('backtest/ndx_dated_fixed_task_preparation_research.py','eb081835d37825688fdf2eb0cb8b90b36d693d15b8f9cc6f6b8659258a8e87e6'),('scripts/ndx_dated_fixed_task_preparation_20261003.py','0b9f1d6c4be6781ad153e9d107ecbff53cbb608df07c84f8ab2636f40daaa5c0')]:read(ROOT/rel,h);sources[str(ROOT/rel)]=h
 plan=docs['original_plan']['plan'];fingerprint=plan['fitter_source_hashes'];check(len(fingerprint)==25,'Frozen25 closure')
 for p,h in fingerprint.items():read(p,h);check(p not in sources or sources[p]==h,'Source collision');sources[p]=h
 check(len(sources)==34,'34 direct sources');exact(document['source_hashes'],sources,'Full sources');exact(pub['source_hashes'],sources,'Publication sources');exact(started['source_hashes'],sources,'Started sources')
 exact(pub['preparation_reference'],dict(path=str(BASE/'preparation.json'),sha256=SHA),'Publication output')
 exact(document['runtime'],pub['runtime'],'Runtime');exact(document['runtime'],started['runtime'],'Started runtime')
 check(pub['status']=='PUBLISHED_NEW_DATED_TASK_INPUTS_NOT_FITTED' and started['retry_allowed'] is False,'Not fitted/single publication')
 typed=docs['training']['panel'];old=docs['prior_preparation'];oldcombos=old['materialized']['combinations'];new=document['materialized'];audit=docs['training_readback']
 check(audit['status']=='PASS' and audit['panel_sha256']==refs['training']['sha256'] and audit['publication_sha256']==refs['training_publication']['sha256'],'Training audit reference only')
 exact(docs['training_publication']['panel_reference'],refs['training'],'Training publication');exact(docs['training_publication']['source_hashes'],docs['training']['source_hashes'],'Training sources')
 exact(docs['prior_publication']['preparation_reference'],refs['prior_preparation'],'Old composition publication');exact(docs['prior_publication']['source_hashes'],old['source_hashes'],'Old source map')
 check(docs['prior_audit']['status']=='PASS' and docs['prior_audit']['preparation_sha256']==refs['prior_preparation']['sha256'] and docs['prior_audit']['publication_sha256']==refs['prior_publication']['sha256'],'Old preparation audit reference only')
 exact(document['training_fit_payload'],typed['fit_payload'],'Full training payload');exact(document['complete_observed_provenance_and_missing'],typed['original_provenance_and_missing'],'101 rows');exact(document['preserved_evidence_sidecars'],typed['preserved_evidence_sidecars'],'Seven sidecars');exact(document['original_coordinate_evidence'],typed['original_coordinate_evidence'],'Late coordinates unchanged');exact(document['evaluation_references'],typed['evaluation_references'],'Evaluation references only')
 check(len(document['complete_observed_provenance_and_missing'])==101 and len(document['preserved_evidence_sidecars'])==7,'Evidence counts')
 payload=typed['fit_payload'];frame=payload['returns'];mapping=payload['selected_by_security'];dates=[v[:10] for v in frame['index']]
 check(len(dates)==126 and dates[0]=='2025-09-19' and dates[-1]=='2026-03-20' and all(x==x[:10]+'T00:00:00' for x in frame['index']),'Exact train dates')
 check(len(frame['columns'])==77 and len(mapping)==77 and len({x['issuer_id'] for x in mapping.values()})==76,'77/76')
 column={t:i for i,t in enumerate(frame['columns'])};ctx=plan['context']
 exact(ctx['parameters'],PARAMETERS,'Original8 params');exact(ctx['weight_specs'],SPECS,'Three specs');check(ctx['previous_target_weights'] is None and digest(fingerprint)==ctx['fitter_source_fingerprint'],'None prior/fingerprint')
 expectedcontext=dict(cutoff='2026-03-20',training_reference=refs['training'],training_readback_reference=refs['training_readback'],prior_preparation_reference=refs['prior_preparation'],original_plan_reference=refs['original_plan'],training_frame_sha256=digest(frame),parameters=PARAMETERS,weight_specs=SPECS,requested_previous_target_weights=None,fitter_source_fingerprint=digest(fingerprint))
 exact(new['context'],expectedcontext,'Dated context');check(new['context_id']==digest(expectedcontext),'Context id')
 exact(new['fitter_source_hashes'],fingerprint,'25sources preserved');exact(new['original_all_k_cardinalities_preserved'],plan['cardinalities'],'All76 cards retained');exact(new['original_selection_schedule_preserved'],old['schedule'],'Late selected composition schedule unchanged')
 check(len(new['combinations'])==len(oldcombos)==544,'544 compositions')
 oldids=[];newids=[];locations=[];counts=Counter();cells=0
 for ci,(combo,previous) in enumerate(zip(new['combinations'],oldcombos)):
  k=previous['k'];rank=previous['rank'];sids=previous['fitter_sorted_security_ids'];prefix=previous['prefix_security_ids'];counts[k]+=1
  check(type(k) is int and 4<=k<=20 and type(rank) is int and rank>=0 and len(sids)==k and sids==sorted(set(sids)),'Canonical composition')
  check(prefix==sorted(sids,key=lambda s:(mapping[s]['issuer_id'],s)) and len({mapping[s]['issuer_id'] for s in sids})==k,'One class per issuer')
  for field in ('k','rank','prefix_security_ids','fitter_sorted_security_ids','selection_position'):exact(combo[field],previous[field],'Frozen composition '+field)
  chosen={s:mapping[s] for s in sids};tickers=[chosen[s]['ticker'] for s in sids]
  matrix=dict(dates=dates,tickers=tickers,returns=[[row[column[t]] for t in tickers] for row in frame['data']]);mh=digest(matrix);cells+=126*k
  exact(combo['fit_matrix'],matrix,'Every training matrix cell and order');check(combo['fit_data_sha256']==mh and mh!=previous['fit_data_sha256'],'New training matrix digest')
  check(len(combo['tasks'])==len(previous['tasks'])==3,'3spec each')
  for si,(task,prior) in enumerate(zip(combo['tasks'],previous['tasks'])):
   spec=SPECS[si];oldidentity=prior['numerical_identity'];check(digest(oldidentity)==prior['numerical_task_id'],'Old numeric reference identity')
   identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff='2026-03-20',holding_count=k,selected=chosen,weight_spec=spec,parameters=PARAMETERS,requested_previous_target_weights=None,fit_data_sha256=mh,fitter_source_fingerprint=digest(fingerprint))
   exact(task['numerical_identity'],identity,'Complete new numeric contract');check(task['numerical_task_id']==digest(identity),'New numerical id')
   changed={key for key in set(identity)|set(oldidentity) if enc(identity.get(key))!=enc(oldidentity.get(key))};check(changed=={'cutoff','fit_data_sha256'},'Only dated numerical changes')
   pr=dict(refs['prior_preparation'],json_pointer=f'/materialized/combinations/{ci}/tasks/{si}')
   location=dict(schema='DATED_FIXED_CONSTITUENT_TASK_LOCATION_V1',dated_context_id=digest(expectedcontext),training_reference=refs['training'],prior_task_reference=pr,prior_location_id=prior['location_id'],original_plan_reference=refs['original_plan'],combination_index=ci,k=k,rank=rank,spec_index=si,weight_spec=spec)
   exact(task['location_identity'],location,'New location independently reconstructed');check(task['location_id']==digest(location) and task['location_id']!=prior['location_id'],'New location id')
   exact(task['complete_prior_different_cutoff_task'],prior,'Full original task unchanged');exact(task['prior_different_cutoff_task_reference'],pr,'Original task pointer')
   check(task['expected_fitter_previous_target_weights']=={} and task['completed_reference'] is None and task['status']=='MATERIALIZED_NOT_ATTEMPTED' and type(task['wrapper_call_attempt_count']) is int and task['wrapper_call_attempt_count']==0 and task['fit_performed'] is False,'No inherited completion/attempt')
   oldids.append(prior['numerical_task_id']);newids.append(task['numerical_task_id']);locations.append(task['location_id'])
 check(counts==Counter({k:32 for k in range(4,21)}),'32 per k')
 check(len(set(newids))==len(set(oldids))==len(set(locations))==1632 and not(set(newids)&set(oldids)),'1632 distinct new tasks no reuse')
 exact(new['new_unattempted_numerical_task_ids'],newids,'New ID list');exact(new['prior_different_cutoff_numerical_task_ids'],oldids,'Old ID list')
 for key,value in dict(combination_count=544,materialized_task_count=1632,new_unattempted_task_count=1632,new_wrapper_call_attempt_count=0,new_fit_count=0,new_cutoff_completed_task_count=0,full_plan_task_denominator=FULL,remaining_new_cutoff_uncompleted_task_count=FULL).items():check(type(new[key]) is int and new[key]==value,'Exact denominator '+key)
 check(new['content_sha256']==digest({k:v for k,v in new.items() if k!='content_sha256'}),'Full materialized content checksum')
 for item in (document,new,pub,started):
  for k in ('fit_performed','point_in_time_verified','legal_training_input_admitted','execution_authorized','promotion_allowed','old_fit_results_reused','old_weights_reused','old_raw_reaudited','all_plan_tasks_completed','future_independent_oos','untouched_holdout'):check(item[k] is False,'No authority '+k)
 for k in ('old_task_completion_applies_to_new_cutoff','evaluation_values_used_for_fit','historical_pool_eligibility_verified','historical_selection_timeliness_verified','global_optimum_proven','source_bytes_authenticated'):check(new[k] is False,'Limits '+k)
 check(new['late_pool_and_composition_selection'] is True and document['late_pool_and_composition_selection'] is True and new['historical_retrospective_only'] is True,'Late composition selection')
 for p,h in sources.items():read(p,h)
 return dict(schema='DATED_FIXED_TASK_PREPARATION_INDEPENDENT_READBACK_V1',status='PASS',preparation_sha256=SHA,publication_sha256=PUB,reader_sha256=sha(Path(__file__).read_bytes()),direct_source_count=34,fitter_source_count=25,combination_count=544,materialized_task_count=1632,training_matrix_cells=cells,new_numerical_ids=1632,new_location_ids=1632,old_id_intersection=0,original_provenance_count=101,preserved_sidecar_count=7,per_k_combinations=dict(counts),full_new_cutoff_task_denominator=FULL,new_cutoff_completed_task_count=0,remaining_new_cutoff_uncompleted_task_count=FULL,late_pool_and_composition_selection=True,fit_performed=False,old_raw_reaudited=False,point_in_time_verified=False,legal_training_input_admitted=False)

if __name__=='__main__':
 r=verify()
 with (ROOT/'DYNAMIC_DATED_FIXED_TASK_PREPARATION_INDEPENDENT_READBACK_20261003.json').open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
 print(json.dumps(r,indent=2))

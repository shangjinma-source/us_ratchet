"""Independent saved-report status aggregation; never read task raw or refit."""
from collections import Counter
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/bulk_budgeted_status_summary_20261003_v1'
SHA='b8ff7da891089ec197cfbd4f9433993f3e7c53e649eadd62a1c4dcd27a4eaebb'
PUB='1a7ad9c10e87a4908b3be8c03ac330aa78ecc47f56fef398aa69c4867650b9f9'
BOUND={'preparation':('data/cache/research/bulk_budgeted_search_prepare_20261003_v1/preparation.json','03d60c666e06a00fa44b19b16cda9609b4e2a75d411dff7ac6cd0e0c08915da1'),'rebinding':('data/cache/research/bulk_completed_task_rebinding_20261003_v1/rebinding.json','e2a3cb619a2cd46a2f7d557be91f362342676089756de6baf9ac4c9692daf29d'),'initial':('research_contracts/bulk_budgeted_first_two_completed_20261003_v1.json','6007612374872316d61cded15a9e654f16a72f1899743266221acfdb20b64b9b'),'batch':('data/cache/research/bulk_budgeted_batch_20261003_v1/result.json','0bbc85b1768cb45e846fe5706bdd873de77be1faa9023497ecbffeaf09074d2d')}
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
STATES=('RISK_PASSED','RISK_FAILED','NUMERICAL_EXCEPTION','VALIDATION_FAILURE','UNDISPATCHED','UNRESOLVED_DISPATCH')
FALSE=('promotion_allowed','execution_authorized','point_in_time_verified','legal_training_input_admitted','all_plan_tasks_completed','economic_comparison_performed','retry_allowed')
def check(v,m):
 if not v:raise ValueError(m)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def exact(a,b,m):check(enc(a)==enc(b),m)
def read(path,h):
 b=Path(path).read_bytes();check(sha(b)==h,'SHA '+str(path));return json.loads(b)
def verify():
 summary=read(BASE/'summary.json',SHA);pub=read(BASE/'publication.json',PUB);started=json.loads((BASE/'started.json').read_bytes())
 check({p.name for p in BASE.iterdir()}=={'started.json','summary.json','publication.json'},'Exact successful namespace')
 docs={k:read(ROOT/p,h) for k,(p,h) in BOUND.items()};refs={k:dict(path=str(ROOT/p),sha256=h) for k,(p,h) in BOUND.items()}
 source=ROOT/'scripts/ndx_bulk_budgeted_status_summary_20261003.py';sourcehash='5783fbc20821c4481f084cee35fd38e2498023833048630fa4068c0cbe4b52b9';check(sha(source.read_bytes())==sourcehash,'Frozen summarizer bytes')
 sources={str(source):sourcehash,**{r['path']:r['sha256'] for r in refs.values()}}
 material=docs['preparation']['materialized'];full=material['full_plan_task_denominator'];check(type(full) is int and full==6222659648236112670,'Whole plan denominator')
 tasks=[];byid={}
 for ci,combo in enumerate(material['combinations']):
  check(type(combo['k']) is int and combo['k']==4+ci//32,'All k ordered')
  for si,task in enumerate(combo['tasks']):
   tid=task['numerical_task_id'];identity=task['numerical_identity'];check(sha(enc(identity))==tid and tid not in byid,'Numeric ID')
   check(identity['weight_spec']==SPECS[si] and identity['holding_count']==combo['k'],'Spec/k')
   item=dict(k=combo['k'],weight_spec=SPECS[si],task_reference=dict(refs['preparation'],json_pointer=f'/materialized/combinations/{ci}/tasks/{si}'));byid[tid]=item;tasks.append(tid)
 check(len(tasks)==1632 and len(material['combinations'])==544,'All new tasks');exact(tasks,material['new_unattempted_numerical_task_ids'],'Saved ID sequence')
 tables={str(k):{spec:{s:0 for s in ('EXTERNAL_RISK_PASSED',)+STATES} for spec in SPECS} for k in range(4,21)}
 oldrows=[];oldids=set()
 for i,row in enumerate(docs['rebinding']['rows']):
  old=row['old_completed_row'];task=old['full_task'];identity=task['numerical_identity'];tid=row['numerical_task_id'];k=identity['holding_count'];spec=identity['weight_spec']
  check(tid==task['numerical_task_id']==sha(enc(identity)) and tid not in oldids and tid not in byid,'Old disjoint IDs');oldids.add(tid)
  check(row['status']=='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND' and old['status'] in ('FITTED_FIVE_RISKS_PASSED','COMPLETED_EXTERNALLY_AUDITED_ORIGINAL_FIVE_RISKS_PASSED'),'Old saved pass classification')
  check(type(row['new_wrapper_call_attempt_count']) is int and row['new_wrapper_call_attempt_count']==0,'No new rebinding attempt')
  tables[str(k)][spec]['EXTERNAL_RISK_PASSED']+=1
  oldrows.append(dict(numerical_task_id=tid,k=k,weight_spec=spec,state='EXTERNAL_RISK_PASSED',reference=dict(refs['rebinding'],json_pointer=f'/rows/{i}'),old_completed_reference=row['old_completed_row_reference']))
 check(len(oldids)==504,'Old complete504')
 initial=docs['initial']['rows'];batch=docs['batch'];accepted=initial+batch['newly_readback_rows']
 exact(batch['initial_completed_rows'],initial,'Preserved first two');exact(batch['batch_context']['first_two_reference'],refs['initial'],'Initial reference')
 check(batch['batch_context']['ordered_task_ids_sha256']==sha(json.dumps(tasks,separators=(',',':')).encode()),'Batch full queue')
 check(batch['status']=='BUDGETED_QUEUE_FINISHED' and batch['failure'] is None and batch['undispatched_task_ids']==[] and batch['unresolved_dispatched_task_ids']==[],'Actual completed batch')
 check(type(batch['new_readback_count']) is int and batch['new_readback_count']==1630 and len(accepted)==1632,'Batch accepted counts')
 exact([r['numerical_task_id'] for r in accepted],tasks,'No skips/double dispatch')
 rows=[];reportrefs=[];counts=Counter();newcounts=Counter()
 for i,row in enumerate(accepted):
  tid=row['numerical_task_id'];r=row['independent_readback_reference'];check(r['path'] not in sources,'Unique report reference');report=read(r['path'],r['sha256']);sources[r['path']]=r['sha256'];reportrefs.append(r)
  check(report['schema']=='BULK_BUDGETED_SINGLE_TASK_INDEPENDENT_READBACK_V1' and report['status']=='PASSED','External report status')
  check(report['numerical_task_id']==tid and report['postcheck_reference']==row['postcheck_reference'],'Saved report/task/post linkage');exact(report['task_reference'],byid[tid]['task_reference'],'Queue pointer')
  exact(report['input_references']['preparation'],refs['preparation'],'Report preparation authority')
  check(report['materialized_task_denominator']==1632 and report['externally_completed_task_count']==504 and report['full_plan_task_denominator']==full and report['other_new_tasks_not_inferred']==1631,'Report scope')
  check(report['independent_readback_performed'] is True and report['runner_called'] is False and report['fitter_called'] is False,'Readback scope')
  for flag in ('promotion_allowed','execution_authorized','point_in_time_verified','legal_training_input_admitted','all_plan_tasks_completed','retry_allowed','optimization_repeated','risk_projection_metadata_independently_recomputed','optimizer_optimality_proved','runtime_binary_closure_verified','full_transitive_source_closure_reverified'):check(report[flag] is False,'Report false '+flag)
  outcome=report['attempt_outcome'];status=report['detail']['status'];match={'RISK_PASSED':'FITTED_FIVE_RISKS_PASSED','RISK_FAILED':'FITTED_FIVE_RISKS_FAILED','NUMERICAL_EXCEPTION':'NUMERICAL_EXCEPTION_NO_RETURNED_FIT'}
  check(outcome in STATES[:4] and (status==match[outcome] if outcome in match else status in match.values()),'Outcome/detail classification')
  if i>=2:
   check(type(row['ordinal']) is int and row['ordinal']==i-2 and row['attempt_outcome']==outcome,'Batch accepted ordering');newcounts[outcome]+=1
  counts[outcome]+=1;tables[str(byid[tid]['k'])][byid[tid]['weight_spec']][outcome]+=1
  rows.append(dict(numerical_task_id=tid,**byid[tid],state=outcome,independent_readback_reference=r,postcheck_reference=row['postcheck_reference'],successful_reusable_evidence=outcome=='RISK_PASSED'))
 exact(batch['new_outcome_counts'],{s:newcounts[s] for s in STATES[:4]},'Batch counts independently derived')
 passed=counts['RISK_PASSED'];expected=dict(schema='BULK_BUDGETED_SAVED_STATUS_SUMMARY_V1',status='SUMMARY_OF_SAVED_EVIDENCE_ONLY',input_references=refs,old_task_denominator=504,new_task_denominator=1632,combined_task_denominator=2136,new_state_counts={s:counts[s] for s in STATES},per_cardinality_and_spec=tables,old_external_rows=oldrows,new_rows=rows,accepted_new_readback_count=len(accepted),saved_independent_report_count=len(reportrefs),unresolved_dispatch_invocation_count=0,dispatch_invocation_count=len(accepted),dispatch_invocation_is_proven_optimizer_call_count=False,new_returned_fit_with_accepted_risk_readback_count=counts['RISK_PASSED']+counts['RISK_FAILED'],successful_new_risk_pass_evidence_count=passed,successful_reusable_evidence_count=504+passed,full_plan_task_denominator=full,remaining_without_accepted_terminal_readback=full-504-len(accepted),remaining_without_successful_risk_pass=full-504-passed,bounded_queue_fully_classified=True,bounded_queue_all_dispatched=True,bounded_queue_all_readbacks_accepted=True,report_references=reportrefs,numerical_exception_proves_economic_infeasibility=False,risk_failure_proves_global_infeasibility=False,report_source_closures_reaudited=False,old_raw_read=False,new_raw_read=False,risk_checks_recomputed=False,fit_performed=False,optimizer_call_count=None,parent_bytes_authenticated_by_this_pure_function=False,source_hashes=sources,**dict.fromkeys(FALSE,False))
 exact(summary,expected,'Entire saved summary independently reconstructed')
 exact(started,dict(source_hashes=sources,**dict.fromkeys(FALSE,False)),'Started source map')
 exact(pub,dict(schema='BULK_BUDGETED_STATUS_SUMMARY_PUBLICATION_V1',summary_reference=dict(path=str(BASE/'summary.json'),sha256=SHA),source_hashes=sources,**dict.fromkeys(FALSE,False)),'Publication')
 return dict(status='PASS',summary_sha256=SHA,publication_sha256=PUB,reader_sha256=sha(Path(__file__).read_bytes()),direct_source_count=len(sources),saved_new_report_count=len(reportrefs),old_external_count=len(oldrows),unique_total=len(set(tasks)|oldids),new_state_counts=dict(counts),per_cardinality_and_spec=tables,remaining_without_accepted_terminal_readback=full-504-len(accepted),remaining_without_successful_risk_pass=full-504-passed,new_raw_read=False,old_raw_read=False,risk_checks_recomputed=False,fit_performed=False,optimizer_call_count=None,all_plan_tasks_completed=False,economic_comparison_performed=False,point_in_time_verified=False)
if __name__=='__main__':
 result=verify();out=ROOT/'DYNAMIC_BULK_BUDGETED_STATUS_INDEPENDENT_READBACK_20261003.json'
 with out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps({k:v for k,v in result.items() if k!='per_cardinality_and_spec'},indent=2))

"""Select saved cash plans; no financial evaluation, IO, or historical returns."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json

POLICY = 'OLD_ORIGINAL_INDEX_THEN_NEW_FROZEN_SCENARIO_ORDINAL_V1'
FIRST_ID = '8b5320eb5ac613ddf6a69478f7e2360811688d1951b38c9e1d7b4ff34678febd'
FLAGS = dict.fromkeys(('source_bytes_authenticated','point_in_time_verified','promotion_allowed','orders_executed','account_executed','risk_recomputed','fees_recomputed','l1_recomputed','time_series_return_evaluated','global_optimality_claimed','fresh_oos_claimed'), False)

def require(ok, message):
    if not ok: raise ValueError(message)

def encode(x): return json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def digest(x): return hashlib.sha256(encode(x)).hexdigest()
def exact(a,b): require(encode(a)==encode(b), 'Saved evidence differs')
def integer(x): require(type(x) is int and x>=0, 'Nonnegative exact integer'); return x

def reference(r):
    require(type(r) is dict and set(r) in ({'path','sha256'},{'path','sha256','json_pointer'}), 'Explicit reference')
    require(type(r['path']) is str and bool(r['path']), 'Reference path')
    h=r['sha256']; require(type(h) is str and len(h)==64 and all(c in '0123456789abcdef' for c in h), 'Reference SHA')
    if 'json_pointer' in r: require(type(r['json_pointer']) is str and r['json_pointer'].startswith('/'), 'Pointer')
    return r

def ratio(r):
    require(type(r) is dict and set(r)=={'numerator','denominator'}, 'Saved exact ratio')
    integer(r['numerator']); integer(r['denominator']); require(r['denominator']>0,'Positive denominator')
    return Fraction(r['numerator'],r['denominator'])

def audit_gate(envelope):
    reference(envelope['reference']); d=envelope['document']
    require(d['schema']=='CASH_NEIGHBOR_FULL_BATCH_INDEPENDENT_READBACK_V1' and d['status']=='PASS','Complete independent audit required')
    c=d['counts']
    for k,n in {'task_count':301657,'new_arithmetic_checked_total_including_previously_audited_first':301656,'external_original_single_task_count':1,'ordered_shard_count':324}.items():
        require(integer(c[k])==n,'Complete declared denominator')
    o=c['outcome_counts']; require(set(o)=={'FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','EXTERNALLY_REFERENCED'},'Outcome categories')
    for n in o.values(): integer(n)
    require(o['EVALUATION_EXCEPTION']==o['VALIDATION_FAILURE']==0 and o['EXTERNALLY_REFERENCED']==1 and sum(o.values())==301657,'No technical or missing results')
    refs=d['shard_audit_references']; require(len(refs)==324 and len({encode(reference(r)) for r in refs})==324,'Complete distinct shard audit refs')
    return d

def score(saved, plan):
    require(type(plan['feasible']) is bool,'Exact feasibility')
    if not plan['feasible']: require(saved is None,'Infeasible has no score'); return None
    require(type(saved) is dict and set(saved)=={'distance','fees_usd'},'Feasible score required')
    distance,fee=ratio(saved['distance']),ratio(saved['fees_usd'])
    require(type(plan['fees_usd']) is str and Fraction(plan['fees_usd'])==fee,'Saved fee agreement')
    return distance,fee

def select_scenario(*,prepared,previous_row,new_records,expected_new_count,old_selected_path,full_audit,tie_policy):
    """Consume one complete scenario; references are declarations, not authentication."""
    require(tie_policy==POLICY,'Registered cross-batch policy'); integer(expected_new_count)
    audit=audit_gate(full_audit); c=prepared['contract']; exact(digest(c),prepared['contract_sha256'])
    require(c['schema']=='CONDITIONAL_TOPUP_NEIGHBOR_SCENARIO_CONTRACT_V1','Prepared schema')
    sid=c['scenario_id']; exact(previous_row['scenario_id'],sid); exact(previous_row['input_row'],c['original_input_row'])
    exact(previous_row['input_reference'],c['input_reference'])
    ids=c['conditional_research_buy_ids']; require(ids==sorted(set(ids)) and ids,'Canonical buy domain')
    caps=c['saved_buy_limits']; require(set(caps)==set(ids),'Full caps')
    for v in caps.values(): integer(v)
    branches=previous_row['evaluation']['branches']; require(len(branches)==1 and branches[0]['branch_id']==sid,'One original scenario')
    old=branches[0]['evaluated_plans']; require(integer(branches[0]['evaluated_count'])==len(old),'Complete old evaluated domain')
    require(integer(previous_row['evaluation']['unevaluated_supplied_plan_count'])==0,'Old evaluation complete')
    require(len(c['old_evaluated_points'])==len(old),'Old contract count')
    scores={}
    for row in previous_row['feasible_scores']:
        i=integer(row['candidate_index']); require(i<len(old) and i not in scores,'Unique old score index')
        scores[i]={k:row[k] for k in ('distance','fees_usd')}
    ledger=[]; seen=set(); taskids=set(); ranked=[]
    def append(plan,saved,origin,refs,identity):
        buy=plan['buy_shares']; require(type(buy) is dict and set(buy)==set(ids),'Full buy coordinates')
        vector=tuple(integer(buy[s]) for s in ids); require(all(q<=caps[s] for s,q in zip(ids,vector)),'Saved cap')
        require(vector not in seen,'Duplicate buy vector across declared union'); seen.add(vector)
        value=score(saved,plan); index=len(ledger)
        row=dict(merged_candidate_index=index,origin=origin,identity=deepcopy(identity),buy_shares=deepcopy(buy),feasible=plan['feasible'],saved_score=deepcopy(saved),references=deepcopy(refs),saved_plan=deepcopy(plan))
        ledger.append(row)
        if value is not None: ranked.append((*value,index))
    for i,plan in enumerate(old):
        require(integer(plan['supplied_plan_index'])==i,'Old original order')
        point=c['old_evaluated_points'][i]; require(integer(point['candidate_index'])==i,'Old contract index')
        exact(point['buy_shares'],plan['buy_shares']); exact(point['saved_feasible'],plan['feasible']); reference(point['reference'])
        append(plan,scores.get(i),'OLD',{'plan':point['reference']},{'old_candidate_index':i})
    require(set(scores)=={i for i,p in enumerate(old) if p['feasible']},'All and only feasible old scores')
    oldbest=min(ranked)[2] if ranked else None
    exact(oldbest,previous_row['selected_candidate_index']); exact(oldbest,c['original_selected_candidate_index'])
    if oldbest is None: require(old_selected_path is None,'No invented old path')
    else:
        reference(old_selected_path['reference']); exact(old_selected_path['scenario_id'],sid)
        exact(old_selected_path['selected_candidate_index'],oldbest); exact(old_selected_path['buy_shares'],old[oldbest]['buy_shares'])
    count=0
    for record in new_records:
        require(count<expected_new_count,'Excess new points'); task=record['task']; tid=task['task_id']; identity=task['identity']
        require(integer(task['scenario_candidate_ordinal'])==count and task['scenario_id']==sid,'Frozen new order')
        exact(identity,dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_TASK_IDENTITY_V1',rule=c['rule'],scenario_contract_sha256=prepared['contract_sha256'],buy_shares=identity['buy_shares']))
        exact(tid,digest(identity)); require(tid not in taskids,'Duplicate new task'); taskids.add(tid)
        refs=record['references']; require(set(refs)=={'task','raw','postcheck'},'Three prepared/journal references')
        for r in refs.values(): reference(r)
        envelope=record['shard_audit']; reference(envelope['reference'])
        require(envelope['reference'] in audit['shard_audit_references'],'Audit must belong to final full audit')
        d=envelope['document']; require(d['status']=='PASS','Shard audited')
        require(d['schema'] in ('CASH_NEIGHBOR_FULL_AUDIT_SHARD_V1','CASH_NEIGHBOR_SHARD_INDEPENDENT_READBACK_V1'),'Shard audit schema')
        detail=d.get('detail',d); pos=integer(record['audit_task_index']); checked=detail['task_results'][pos]
        exact(checked['task_id'],tid)
        if tid==FIRST_ID:
            require(checked['outcome']=='EXTERNALLY_REFERENCED' and checked['new_arithmetic_checked'] is False,'First only external')
            single=record['single_audit']; reference(single['reference']); checked=single['document']
            for linked in (single['reference'],refs['raw'],refs['postcheck']):
                require(audit['source_hashes'].get(linked['path'])==linked['sha256'],'First evidence belongs to full audited source closure')
            require(checked['schema']=='CASH_TOPUP_SINGLE_EVALUATION_INDEPENDENT_READBACK_V1' and checked['status']=='PASS' and checked['task_id']==tid,'Original single audit')
            require(checked['returned_arithmetic_independently_verified'] is True and checked['technical_failure_preserved'] is False,'Original arithmetic verified')
            outcome=checked['attempt_outcome']
            exact(checked['raw_reference'],refs['raw']); exact(checked['postcheck_reference'],refs['postcheck'])
        else:
            require(checked['new_arithmetic_checked'] is True,'New arithmetic independently checked'); outcome=checked['outcome']
        raw,post=record['raw'],record['postcheck']
        require(raw['error'] is None and type(raw['explicit_evaluator_call_attempt_count']) is int and raw['explicit_evaluator_call_attempt_count']==1 and type(raw['returned_evaluation_count']) is int and raw['returned_evaluation_count']==1,'One returned evaluation')
        require(post['evaluation_error'] is None and post['validation_error'] is None,'Technical failure cannot compete')
        require(outcome in ('FEASIBLE','INFEASIBLE') and post['outcome']==outcome,'Audited economic outcome')
        result=raw['result']; b=result['branches']; require(len(b)==1 and b[0]['branch_id']==sid and len(b[0]['evaluated_plans'])==1,'One new plan')
        plan=b[0]['evaluated_plans'][0]; exact(plan['buy_shares'],identity['buy_shares']); require(integer(plan['supplied_plan_index'])==0,'Single evaluator index')
        exact(plan['feasible'],outcome=='FEASIBLE'); saved=post['original_target_stock_weight_l1']; exact(saved,checked['original_target_stock_weight_l1'])
        append(plan,saved,'NEW',dict(refs,shard_audit=envelope['reference'],single_audit=record.get('single_audit',{}).get('reference')),task)
        count+=1
    require(count==expected_new_count,'Missing new candidates')
    winner=deepcopy(ledger[min(ranked)[2]]) if ranked else None
    reuse=winner is not None and oldbest is not None and winner['buy_shares']==old[oldbest]['buy_shares']
    status='NO_FEASIBLE_IN_DECLARED_UNION' if winner is None else ('REUSE_EXISTING_PAIRED_PATH' if reuse else 'NEW_PATH_REQUIRED')
    return dict(schema='CASH_NEIGHBOR_SCENARIO_SELECTION_V1',scenario_id=sid,tie_policy=POLICY,contract_sha256=prepared['contract_sha256'],full_audit_reference=deepcopy(full_audit['reference']),old_candidate_count=len(old),new_candidate_count=count,total_candidate_count=len(ledger),feasible_candidate_count=len(ranked),candidate_ledger=ledger,selected=winner,status=status,old_selected_path=deepcopy(old_selected_path),reused_path_reference=deepcopy(old_selected_path['reference']) if reuse else None,scope='BEST_IN_COMPLETE_DECLARED_UNION_NOT_GLOBAL_OPTIMUM',selection_performed=True,**FLAGS)

def collect_selections(*,scenario_results,expected_scenario_ids,full_audit):
    audit_gate(full_audit); require(type(expected_scenario_ids) is list and len(expected_scenario_ids)==40 and len(set(expected_scenario_ids))==40,'Original forty cases')
    rows=list(scenario_results); require([r['scenario_id'] for r in rows]==expected_scenario_ids,'Complete original scenario order')
    for row in rows:
        require(row['schema']=='CASH_NEIGHBOR_SCENARIO_SELECTION_V1' and row['tie_policy']==POLICY,'Selection schema/policy')
        exact(row['full_audit_reference'],full_audit['reference'])
        for key in FLAGS: require(row[key] is False,'No authority promotion')
        oldn=integer(row['old_candidate_count']); newn=integer(row['new_candidate_count'])
        ledger=row['candidate_ledger']; require(type(ledger) is list and len(ledger)==oldn+newn and integer(row['total_candidate_count'])==len(ledger),'Complete ledger length')
        ranked=[]; vectors=set(); task_ids=set()
        for i,item in enumerate(ledger):
            require(integer(item['merged_candidate_index'])==i and item['origin']==('OLD' if i<oldn else 'NEW'),'Stable complete ledger partition')
            exact(item['buy_shares'],item['saved_plan']['buy_shares']); exact(item['feasible'],item['saved_plan']['feasible'])
            vector=encode(item['buy_shares']); require(vector not in vectors,'Unique union quantities'); vectors.add(vector)
            value=score(item['saved_score'],item['saved_plan'])
            if value is not None: ranked.append((*value,i))
            if i<oldn: require(integer(item['identity']['old_candidate_index'])==i,'Old index')
            else:
                identity=item['identity']; require(identity['scenario_id']==row['scenario_id'] and integer(identity['scenario_candidate_ordinal'])==i-oldn,'New scenario ordinal')
                exact(identity['task_id'],digest(identity['identity'])); require(identity['task_id'] not in task_ids,'Unique task'); task_ids.add(identity['task_id'])
        require(integer(row['feasible_candidate_count'])==len(ranked),'Feasible count')
        expected=ledger[min(ranked)[2]] if ranked else None; exact(row['selected'],expected)
        oldpath=row['old_selected_path']; oldrank=[x for x in ranked if x[2]<oldn]
        if oldrank:
            oldwinner=ledger[min(oldrank)[2]]; require(oldpath is not None,'Old winner path required')
            reference(oldpath['reference']); exact(oldpath['scenario_id'],row['scenario_id']); exact(oldpath['buy_shares'],oldwinner['buy_shares']); exact(oldpath['selected_candidate_index'],oldwinner['merged_candidate_index'])
        else: require(oldpath is None,'No invented old path')
        reuse=expected is not None and oldpath is not None and expected['buy_shares']==oldpath['buy_shares']
        status='NO_FEASIBLE_IN_DECLARED_UNION' if expected is None else ('REUSE_EXISTING_PAIRED_PATH' if reuse else 'NEW_PATH_REQUIRED')
        exact(row['status'],status); exact(row['reused_path_reference'],oldpath['reference'] if reuse else None)
    require(sum(integer(r['new_candidate_count']) for r in rows)==301657,'Complete new candidate denominator')
    statuses=('REUSE_EXISTING_PAIRED_PATH','NEW_PATH_REQUIRED','NO_FEASIBLE_IN_DECLARED_UNION')
    require(all(r['status'] in statuses for r in rows),'Known selection partition')
    return dict(schema='CASH_NEIGHBOR_COMPLETE_SELECTIONS_V1',rows=deepcopy(rows),scenario_count=40,new_candidate_count=301657,status_counts={s:sum(r['status']==s for r in rows) for s in statuses},full_audit_reference=deepcopy(full_audit['reference']),selection_performed=True,**FLAGS)

"""Single-pass selection over an entire independently inspected replacement domain.

No IO, evaluation, future returns or cross-family ranking. References and audit
objects are structural declarations here; authentication belongs to the caller.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json

RANKING='NOT_SELECTED_FUTURE_ORIGINAL_TARGET_L1_THEN_TOTAL_BILATERAL_FEE_THEN_STABLE_PAIR_Q'
RULE='SELL_ALL_ONE_POSITIVE_OLD_BUY_ONE_NEW_INTEGER_V1'
FLAGS=dict.fromkeys(('source_bytes_authenticated','evaluation_reperformed','account_executed','fit_executed',
 'future_returns_used','cross_family_winner_selected','global_optimality_claimed','point_in_time_verified',
 'full_ndx_certified','promotion_allowed','execution_authorized'),False)
TASK_FALSE=('source_bytes_authenticated','point_in_time_verified','formal_eligibility_verified','identity_gaps_resolved',
 'risk_evaluated','financial_feasibility_evaluated','economic_winner_selected','global_optimality_claimed','orders_executed',
 'account_executed','fit_executed','old_evaluations_repeated','target_weights_changed','future_returns_used','repair_performed','domain_registered_for_execution')
CHECKS={'MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT'}


def require(ok,message):
    if not ok:raise ValueError(message)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(encode(v)).hexdigest()
def exact(a,b,message):require(encode(a)==encode(b),message)
def integer(n):
    require(type(n) is int and n>=0,'Exact nonnegative integer');return n
def reference(r):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'],'Exact file reference')
    h=r['sha256'];require(type(h) is str and len(h)==64 and set(h)<=set('0123456789abcdef'),'SHA256');return deepcopy(r)
def rational(v):
    require(type(v) is str and 0<len(v)<=1000,'Saved exact rational string')
    f=Fraction(v);require(str(f)==v and f>=0,'Canonical nonnegative exact score');return f


def inspect_prepared(prepared):
    require(type(prepared) is dict and set(prepared)=={'document','content_sha256'} and digest(prepared['document'])==prepared['content_sha256'],'Prepared envelope/hash')
    d=prepared['document'];require(d['schema']=='SINGLE_REPLACEMENT_DOMAIN_PREPARATION_V1','Prepared schema')
    require(all(d[k] is False for k in TASK_FALSE),'Prepared conditional permissions')
    contract=d['action_contract'];require(contract['rule']==RULE and contract['ranking_policy']==RANKING and contract['cross_family_ranking_registered'] is False,'Original registered selection order')
    require(contract['order']=='ORIGINAL_SCENARIO_ORDER_THEN_OUT_SID_IN_SID_Q_ASCENDING','Original stable stream order')
    require(type(d['cases']) is list and len(d['cases'])==integer(d['scenario_count'])==40,'All40 original scenarios')
    exact([c['scenario_id'] for c in d['cases']],contract['expected_scenario_ids'],'Original scenario order')
    require(len(set(contract['expected_scenario_ids']))==40,'Unique original scenario IDs')
    cursor=financial=excluded=pairs=0;rows=[]
    for i,c in enumerate(d['cases']):
        require(type(c['scenario_index']) is int and c['scenario_index']==i and integer(c['first_global_ordinal'])==cursor,'Contiguous original case')
        require(digest(c['identity'])==c['identity_sha256'],'Scenario identity hash');exact(c['identity']['action_contract'],contract,'Original case contract')
        require(c['identity']['original_input_row']['scenario_id']==c['scenario_id'],'Original row identity')
        cf=ce=0;start=cursor;original=c['identity']['original_input_row'];old=sorted(s for s,q in original['holdings'].items() if q>0);incoming=sorted(set(original['target_weights'])-set(old))
        expected=[(o,n) for o in old for n in incoming];require(len(c['pairs'])==integer(c['pair_count'])==len(expected),'Full ordered pair domain')
        for j,(p,(o,n)) in enumerate(zip(c['pairs'],expected)):
            require(type(p['pair_index']) is int and p['pair_index']==j and (p['outgoing_security_id'],p['incoming_security_id'])==(o,n),'Original pair order')
            require(integer(p['first_global_ordinal'])==cursor and integer(p['sell_quantity'])==original['holdings'][o],'Pair original position/sale')
            count=integer(p['enumerable_quantity_count']);cap=integer(p['financial_quantity_count']);conflicts=p['issuer_exclusion_certificate']['conflicts']
            require(count==(0 if conflicts else cap) and integer(p['quantity_max'])==cap and type(p['quantity_min']) is int and p['quantity_min']==1,'Full quantities and excluded partition')
            cursor+=count;cf+=cap;ce+=cap-count;pairs+=1
        require(integer(c['integer_count'])==cursor-start and integer(c['financial_integer_count_before_issuer'])==cf and integer(c['structurally_excluded_integer_count'])==ce,'Original case denominator')
        rows.append(dict(scenario_index=i,scenario_id=c['scenario_id'],scenario_identity_sha256=c['identity_sha256'],pair_count=len(c['pairs']),integer_count=cursor-start,financial_integer_count_before_issuer=cf,structurally_excluded_integer_count=ce,feasible_count=0,infeasible_count=0,status='NO_FEASIBLE',selected=None))
        financial+=cf;excluded+=ce
    require(integer(d['integer_count'])==cursor and integer(d['pair_count'])==pairs and integer(d['financial_integer_count_before_issuer'])==financial and integer(d['structurally_excluded_integer_count'])==excluded and cursor+excluded==financial,'Full whole-domain counts')
    return d,rows


def audited_rows(readback,readback_reference,total):
    """Yield one audited terminal with its exact RAW_RETURNED byte locator."""
    cursor=0
    for si,saved in enumerate(readback['shards']):
        r=reference(saved['shard_result_reference']);report=saved['inspection']
        require(report['schema']=='SINGLE_REPLACEMENT_SHARD_INDEPENDENT_ARITHMETIC_V1' and report['status']=='PASS_SAVED_PREFIX' and report['complete'] is True,'Complete saved shard arithmetic audit')
        require(report['unresolved_ordinal'] is None and report['partial_tail_present'] is False and report['undispatched_ordinals']==[],'No unknown/unprocessed prefix selection')
        begin=integer(report['shard_start']);stop=integer(report['shard_stop']);require(begin==cursor<stop<=total,'Contiguous audited shard range')
        require(integer(report['arithmetic_checked_count'])==stop-begin==len(report['terminal_rows']),'Every terminal arithmetic audited')
        require(integer(report['full_integer_count'])==total,'Audit full denominator')
        records=report['records'];require(len(records)==3*(stop-begin),'Three complete durable records per task')
        require(r['path'].endswith(('/result.json','\\result.json')),'Shard result filename')
        journal=reference(dict(path=r['path'][:-len('result.json')]+'journal.jsonl',sha256=report['journal_sha256']))
        for j,terminal in enumerate(report['terminal_rows']):
            require(type(terminal['global_ordinal']) is int and terminal['global_ordinal']==cursor and terminal['outcome'] in ('FEASIBLE','INFEASIBLE'),'Only accepted complete economics')
            three=records[j*3:j*3+3]
            for index,(record,stage) in enumerate(zip(three,('START','RAW_RETURNED','POSTCHECK'))):
                require(record['stage']==stage and type(record['sequence']) is int and record['sequence']==j*3+index and type(record['global_ordinal']) is int and record['global_ordinal']==cursor,'Original audited record order')
                require(integer(record['byte_start'])<integer(record['byte_stop']),'Nonempty record bytes')
                if j*3+index:require(record['byte_start']==records[j*3+index-1]['byte_stop'],'Contiguous audit byte offsets')
                else:require(record['byte_start']==0,'Journal starts at zero')
            evidence=dict(reference=deepcopy(readback_reference),json_pointer=f'/shards/{si}/inspection/terminal_rows/{j}')
            source=dict(journal_reference=journal,record_locator=deepcopy(three[1]),json_pointer='/body/payload/result')
            yield terminal,source,evidence
            cursor+=1
    require(cursor==total,'All audited shards required before any selection result')


def select_complete_single_replacements(*,prepared,preparation_reference,readback,readback_reference,records):
    # Audit metadata is already supplied as a complete document. Snapshot it and
    # the small domain before entering caller-controlled iteration; never retain
    # the full evaluation stream, only one candidate per original scenario.
    prepared=deepcopy(prepared);readback=deepcopy(readback)
    prepref=reference(preparation_reference);auditref=reference(readback_reference);d,rows=inspect_prepared(prepared);total=d['integer_count']
    require(readback['schema']=='SINGLE_REPLACEMENT_EXECUTION_INDEPENDENT_READBACK_V1' and readback['status']=='PASS_SAVED_PREFIX' and readback['full_domain_evaluated'] is True,'Full independently inspected domain only')
    exact(readback['input_references']['preparation'],prepref,'Prepared and audit same source role')
    for k in ('producer_called','evaluator_called','old_account_reopened','point_in_time_verified','full_ndx_certified','economic_winner_selected','account_executed','fit_executed','orders_executed','automatic_retry_allowed'):require(readback[k] is False,'Original readback permissions')
    p=readback['partition'];require(integer(p['full_integer_count'])==total and integer(p['terminal_count'])==total and p['unresolved_ordinal'] is None and integer(p['undispatched_count'])==0 and integer(p['undispatched_start'])==integer(p['undispatched_stop'])==total,'No prefix ranking')
    counts=p['outcome_counts'];require(set(counts)=={'FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE'},'All terminal classes')
    require(integer(counts['EVALUATION_EXCEPTION'])==integer(counts['VALIDATION_FAILURE'])==0 and integer(counts['FEASIBLE'])+integer(counts['INFEASIBLE'])==total,'No technical failure ranking')
    stream=iter(records);audit_stream=iter(audited_rows(readback,auditref,total));seen=0;retained=0;keys={}
    for ci,c in enumerate(d['cases']):
        original=c['identity']['original_input_row'];result=rows[ci]
        for pair in c['pairs']:
            for q in range(1,pair['enumerable_quantity_count']+1):
                try:record=next(stream);terminal,source,evidence=next(audit_stream)
                except StopIteration:raise ValueError('Missing registered domain point; no prefix winner') from None
                require(type(record) is dict and set(record)=={'global_ordinal','task','evaluation','source_reference','inspection_reference'},'Exact streamed evaluation projection')
                require(type(record['global_ordinal']) is int and record['global_ordinal']==seen,'Each ordinal exactly once in original order')
                exact(record['source_reference'],source,'Actual audited RAW byte locator');exact(record['inspection_reference'],evidence,'Actual audited terminal pointer')
                identity=dict(schema='SINGLE_REPLACEMENT_INTEGER_TASK_IDENTITY_V1',scenario_identity_sha256=c['identity_sha256'],rule=RULE,outgoing_security_id=pair['outgoing_security_id'],incoming_security_id=pair['incoming_security_id'],sell_quantity=pair['sell_quantity'],buy_quantity=q)
                sid_out=pair['outgoing_security_id'];sid_in=pair['incoming_security_id'];holdings={s:original['holdings'].get(s,0) for s in sorted(set(original['holdings'])|set(original['execution_prices']))};holdings[sid_out]=0;holdings[sid_in]=q
                signed={s:0 for s in holdings};signed[sid_out]=-pair['sell_quantity'];signed[sid_in]=q
                task=dict(task_id=digest(identity),identity=identity,scenario_index=ci,pair_index=pair['pair_index'],global_ordinal=seen,signed_trade_quantities=signed,proposed_holdings=holdings,evaluation_status='NOT_EVALUATED',**dict.fromkeys(TASK_FALSE,False))
                exact(record['task'],task,'Original signed task and unchanged zero keys');require(terminal['task_id']==task['task_id'],'Task identity bound to audit')
                value=record['evaluation'];outcome=terminal['outcome'];require(type(value) is dict and value['status']==outcome and value['feasible'] is (outcome=='FEASIBLE'),'Audited result outcome')
                checks=value['risk']['checks'];financial=value['financial_checks'];require(set(checks)==CHECKS and all(type(v) is bool for v in checks.values()) and set(financial)=={'NONNEGATIVE_CASH','CASH_BUFFER'} and all(type(v) is bool for v in financial.values()),'Saved five risk and financial gates')
                require(value['risk']['all_passed'] is all(checks.values()) and value['feasible'] is (all(checks.values()) and all(financial.values()) and not value['issuer_conflicts']),'Saved eligibility conjunction')
                l1=rational(value['original_target_stock_l1']);fee=rational(value['total_fee_usd']);require(fee==rational(value['sell_fee_usd'])+rational(value['buy_fee_usd']),'Saved bilateral fee total')
                result['feasible_count' if outcome=='FEASIBLE' else 'infeasible_count']+=1
                if outcome=='FEASIBLE':
                    key=(l1,fee,sid_out,sid_in,q)
                    if ci not in keys or key<keys[ci]:
                        keys[ci]=key;result['selected']=deepcopy(record);result['status']='SELECTED_REQUIRES_NEW_SIGNED_PATH'
                seen+=1
        require(result['feasible_count']+result['infeasible_count']==result['integer_count'],'Case all terminal denominator')
        retained+=int(result['selected'] is not None)
    sentinel=object();require(next(stream,sentinel) is sentinel,'Extra unregistered evaluation');require(next(audit_stream,sentinel) is sentinel,'Extra audited terminal')
    require(seen==total and sum(r['feasible_count'] for r in rows)==counts['FEASIBLE'] and sum(r['infeasible_count'] for r in rows)==counts['INFEASIBLE'],'Entire original domain consumed')
    body=dict(schema='SINGLE_REPLACEMENT_COMPLETE_DOMAIN_SELECTION_V1',status='COMPLETE_WITHIN_FAMILY_SELECTION_NOT_ACCOUNT_OR_CROSS_FAMILY_WINNER',preparation_reference=prepref,prepared_content_sha256=prepared['content_sha256'],readback_reference=auditref,action_contract=deepcopy(d['action_contract']),scope=d['scope'],scenario_count=40,pair_count=d['pair_count'],integer_count=total,financial_integer_count_before_issuer=d['financial_integer_count_before_issuer'],structurally_excluded_integer_count=d['structurally_excluded_integer_count'],feasible_count=counts['FEASIBLE'],infeasible_count=counts['INFEASIBLE'],selected_case_count=retained,no_feasible_case_count=40-retained,rows=rows,ranking=RANKING,stream_consumed_once=True,all_registered_points_consumed=True,selection_basis='SAVED_INDEPENDENTLY_INSPECTED_ORIGINAL_TARGET_STOCK_L1_AND_BILATERAL_FEE',**FLAGS)
    return dict(document=body,content_sha256=digest(body))

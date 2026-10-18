"""Independent saved single-replacement arithmetic and journal inspection.

No production evaluator, rank helper, journal module, IO or account execution.
The source wrapper must authenticate the prepared domain and original bytes.
"""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import hashlib
import json

TASK_FALSE = ('source_bytes_authenticated','point_in_time_verified','formal_eligibility_verified',
 'identity_gaps_resolved','risk_evaluated','financial_feasibility_evaluated','economic_winner_selected',
 'global_optimality_claimed','orders_executed','account_executed','fit_executed','old_evaluations_repeated',
 'target_weights_changed','future_returns_used','repair_performed','domain_registered_for_execution')
CHECKS = ('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
FLAGS = dict.fromkeys(('source_bytes_authenticated','producer_called','evaluator_called','account_executed',
                      'point_in_time_verified','full_ndx_certified','economic_winner_selected','automatic_retry_allowed'),False)


def require(ok,message):
    if not ok:raise ValueError(message)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def digest(value):return hashlib.sha256(encode(value)).hexdigest()
def exact(a,b,message):require(encode(a)==encode(b),message)
def integer(n):
    require(type(n) is int and n>=0,'Exact nonnegative integer');return n
def error(value):
    require(type(value) is dict and set(value)=={'type','message'} and type(value['type']) is str and bool(value['type']) and type(value['message']) is str,'Exact original error strings')
def number(value):
    require(type(value) is str and 0<len(value)<=80 and value.strip()==value,'Saved decimal literal')
    d=Decimal(value);require(d.is_finite() and len(d.as_tuple().digits)<=40 and abs(d.as_tuple().exponent)<=40,'Bounded finite decimal')
    return Fraction(d)


def catalogue(prepared):
    require(type(prepared) is dict and set(prepared)=={'document','content_sha256'},'Prepared envelope')
    d=prepared['document'];require(digest(d)==prepared['content_sha256'] and d['schema']=='SINGLE_REPLACEMENT_DOMAIN_PREPARATION_V1','Prepared content')
    require(all(d[k] is False for k in TASK_FALSE),'Conditional domain flags')
    require(integer(d['scenario_count'])==len(d['cases']) and [c['scenario_id'] for c in d['cases']]==d['action_contract']['expected_scenario_ids'],'Full scenario order')
    intervals=[];cursor=financial=excluded=pairs=0
    for ci,c in enumerate(d['cases']):
        require(type(c['scenario_index']) is int and c['scenario_index']==ci and integer(c['first_global_ordinal'])==cursor,'Case coordinate')
        require(digest(c['identity'])==c['identity_sha256'],'Original scenario identity')
        row=c['identity']['original_input_row'];exact(c['identity']['action_contract'],d['action_contract'],'Original action contract')
        require(row['scenario_id']==c['scenario_id'],'Original row scenario')
        holdings=row['holdings'];require(all(type(q) is int and q>=0 for q in holdings.values()),'Whole original holdings')
        old=sorted(s for s,q in holdings.items() if q>0);incoming=sorted(set(row['target_weights'])-set(old))
        expected_pairs=[(o,n) for o in old for n in incoming]
        require(len(c['pairs'])==integer(c['pair_count'])==len(expected_pairs),'All ordered pairs retained')
        start=cursor;cf=ce=0
        for pi,((out,new),p) in enumerate(zip(expected_pairs,c['pairs'])):
            require(type(p['pair_index']) is int and p['pair_index']==pi and p['outgoing_security_id']==out and p['incoming_security_id']==new,'Pair identity/order')
            require(integer(p['sell_quantity'])==holdings[out] and integer(p['first_global_ordinal'])==cursor,'Pair origin')
            price_out=number(row['execution_prices'][out]);price_in=number(row['execution_prices'][new]);rate=number(row['transaction_cost_bps'])/10000
            require(price_out>0 and price_in>0 and rate>=0,'Valid nominal prices/fee')
            available=number(row['starting_cash_usd'])+number(row['cash_event']['amount_usd'])+holdings[out]*price_out*(1-rate)-number(row['minimum_cash_buffer_usd'])
            quotient=available/(price_in*(1+rate));floor=quotient.numerator//quotient.denominator;cap=max(0,floor)
            groups={}
            for sid in sorted((set(old)-{out})|{new}):groups.setdefault(row['securities'][sid]['issuer_id'],[]).append(sid)
            conflicts={issuer:ids for issuer,ids in groups.items() if len(ids)>1};count=0 if conflicts else cap
            exact(p['issuer_exclusion_certificate'],dict(remaining_positive_security_ids=sorted(set(old)-{out}),incoming_security_id=new,issuer_groups=groups,conflicts=conflicts,applies_to_all_positive_integer_buys=True),'Issuer exclusion scope')
            require(type(p['financial_cap_floor']) is int and p['financial_cap_floor']==floor and integer(p['financial_quantity_count'])==cap
                    and type(p['quantity_min']) is int and p['quantity_min']==1 and integer(p['quantity_max'])==cap and integer(p['enumerable_quantity_count'])==count,'Independent exact qcap')
            if count:intervals.append((cursor,cursor+count,c,p))
            cursor+=count;cf+=cap;ce+=cap-count;pairs+=1
        require(integer(c['integer_count'])==cursor-start and integer(c['financial_integer_count_before_issuer'])==cf and integer(c['structurally_excluded_integer_count'])==ce,'Case full partition')
        financial+=cf;excluded+=ce
    require(integer(d['integer_count'])==cursor and integer(d['pair_count'])==pairs and integer(d['financial_integer_count_before_issuer'])==financial
            and integer(d['structurally_excluded_integer_count'])==excluded and cursor+excluded==financial,'Full registered domain')
    return intervals


def reconstruct_task(intervals,ordinal):
    integer(ordinal)
    for begin,end,c,p in intervals:
        if begin<=ordinal<end:
            row=c['identity']['original_input_row'];out=p['outgoing_security_id'];new=p['incoming_security_id'];q=ordinal-begin+1
            identity=dict(schema='SINGLE_REPLACEMENT_INTEGER_TASK_IDENTITY_V1',scenario_identity_sha256=c['identity_sha256'],rule='SELL_ALL_ONE_POSITIVE_OLD_BUY_ONE_NEW_INTEGER_V1',outgoing_security_id=out,incoming_security_id=new,sell_quantity=p['sell_quantity'],buy_quantity=q)
            slots=sorted(set(row['holdings'])|set(row['execution_prices']));holdings={s:row['holdings'].get(s,0) for s in slots};holdings[out]=0;holdings[new]=q
            signed={s:0 for s in slots};signed[out]=-p['sell_quantity'];signed[new]=q
            task=dict(task_id=digest(identity),identity=identity,scenario_index=c['scenario_index'],pair_index=p['pair_index'],global_ordinal=ordinal,signed_trade_quantities=signed,proposed_holdings=holdings,evaluation_status='NOT_EVALUATED',**dict.fromkeys(TASK_FALSE,False))
            return row,task
    raise ValueError('Ordinal outside complete domain')


def arithmetic(row,task):
    """Independent oracle from original saved decimals, not production outputs."""
    marks={s:number(v) for s,v in row['execution_prices'].items()};after=task['proposed_holdings'];trades=task['signed_trade_quantities']
    sale=sum((marks[s]*(-q) for s,q in trades.items() if q<0),Fraction(0));purchase=sum((marks[s]*q for s,q in trades.items() if q>0),Fraction(0))
    rate=number(row['transaction_cost_bps'])/10000;sellfee=sale*rate;buyfee=purchase*rate
    cash=number(row['starting_cash_usd'])+number(row['cash_event']['amount_usd'])+sale-purchase-sellfee-buyfee
    positive={s:marks[s]*q for s,q in sorted(after.items()) if q>0};stock=sum(positive.values(),Fraction(0));require(stock>0,'Positive stock denominator')
    weights={s:value/stock for s,value in positive.items()};ordered=sorted(weights.values(),reverse=True)
    effective=stock*stock/sum((v*v for v in positive.values()),Fraction(0));chains={};issuers={}
    for sid,w in weights.items():
        chain=row['securities'][sid]['risk_chain'];chains[chain]=chains.get(chain,Fraction(0))+w
        issuers.setdefault(row['securities'][sid]['issuer_id'],[]).append(sid)
    conflicts={issuer:ids for issuer,ids in issuers.items() if len(ids)>1};r={k:number(v) for k,v in row['risk_parameters'].items()};slack=Fraction(1,1000000000)
    values=[max(weights.values())<=r['max_single_weight']+slack,min(weights.values())>=r['min_single_weight']-slack,
            sum(ordered[:3])<=r['top_weight_cap']+slack,effective>=r['minimum_effective_n_ratio']*len(weights)-slack,
            max(chains.values())<=r['risk_chain_top1_cap']+slack]
    checks=dict(zip(CHECKS,values));financial=dict(NONNEGATIVE_CASH=cash>=0,CASH_BUFFER=cash>=number(row['minimum_cash_buffer_usd']))
    targets={s:number(v) for s,v in row['target_weights'].items()};l1=sum((abs(weights.get(s,Fraction(0))-targets.get(s,Fraction(0))) for s in set(weights)|set(targets)),Fraction(0))
    initial=sum((marks[s]*q for s,q in row['holdings'].items() if q),Fraction(0))+number(row['starting_cash_usd'])
    pnl=stock+cash-initial-number(row['cash_event']['amount_usd']);require(pnl==-(sellfee+buyfee),'Independent self-financing identity')
    feasible=all(values) and all(financial.values()) and not conflicts
    return dict(status='FEASIBLE' if feasible else 'INFEASIBLE',feasible=feasible,gross_sell_usd=str(sale),gross_buy_usd=str(purchase),sell_fee_usd=str(sellfee),buy_fee_usd=str(buyfee),total_fee_usd=str(sellfee+buyfee),cash_after_usd=str(cash),invested_stock_usd=str(stock),equity_after_usd=str(stock+cash),cash_flow_adjusted_pnl_usd=str(pnl),financial_checks=financial,
                risk=dict(checks=checks,all_passed=all(values),weights={s:str(w) for s,w in weights.items()},effective_n=str(effective),positive_holding_count=len(weights),risk_chain_weights={s:str(w) for s,w in sorted(chains.items())}),issuer_conflicts=conflicts,original_target_stock_l1=str(l1))


def inspect_saved_evaluation(*,prepared,global_ordinal,task,saved_result):
    row,expected=reconstruct_task(catalogue(prepared),global_ordinal);exact(task,expected,'Signed full replacement identity/zero slots')
    exact(saved_result,arithmetic(row,expected),'Independent complete Fraction evaluation')
    return dict(schema='SINGLE_REPLACEMENT_SAVED_EVALUATION_INSPECTION_V1',status='PASS',task_id=expected['task_id'],global_ordinal=global_ordinal,outcome=saved_result['status'],**FLAGS)


def inspect_saved_journal(*,prepared,journal_bytes,descriptor,context_sha256):
    intervals=catalogue(prepared);identity=descriptor['identity']
    require(identity['schema']=='SINGLE_REPLACEMENT_SHARD_V1' and identity['preparation_sha256']==prepared['content_sha256'] and digest(identity)==descriptor['shard_id'],'Shard identity')
    start=integer(identity['start']);stop=integer(identity['stop']);integer(identity['ordinal']);require(start<stop<=prepared['document']['integer_count'],'Shard interval')
    require(type(journal_bytes) is bytes,'Original journal bytes')
    parts=journal_bytes.split(b'\n');tail=parts.pop();previous='0'*64;cursor=start;state=None;offset=0;terminals=[];record_index=[];arithmetic_count=0
    def pairs(items):
        result={}
        for key,value in items:require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    for sequence,part in enumerate(parts):
        value=json.loads(part.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda s:(_ for _ in ()).throw(ValueError('Nonfinite token')))
        require(type(value) is dict and set(value)=={'body','record_sha256'},'Record envelope');body=value['body']
        require(set(body)=={'schema','context_sha256','sequence','previous_sha256','global_ordinal','task_id','stage','payload'} and value['record_sha256']==digest(body),'Record complete hash')
        require(body['schema']=='SINGLE_REPLACEMENT_JOURNAL_RECORD_V1' and type(body['sequence']) is int and body['sequence']==sequence and body['previous_sha256']==previous and body['context_sha256']==context_sha256,'Hashchain')
        require(cursor<stop and type(body['global_ordinal']) is int and body['global_ordinal']==cursor,'Original contiguous task sequence')
        row,task=reconstruct_task(intervals,cursor);require(body['task_id']==task['task_id'],'Independent task identity')
        stage=body['stage'];p=body['payload']
        if stage=='START':
            require(state is None and (not terminals or terminals[-1]['outcome'] in ('FEASIBLE','INFEASIBLE')),'No retry after terminal/unknown')
            exact(p,dict(task=task,dispatch_may_have_occurred=True),'Original complete START')
            state=dict(stage=stage,raw=None)
        elif stage in ('RAW_RETURNED','RAW_EXCEPTION'):
            require(state is not None and state['stage']=='START','Exactly one raw after START')
            require(p['call_invoked'] is True and type(p['call_count']) is int and p['call_count']==1 and p['returned'] is (stage=='RAW_RETURNED'),'Saved call facts')
            require(type(p['result_preserved_as_json']) is bool,'Raw serialization declaration')
            if stage=='RAW_EXCEPTION':
                require(p['result'] is None,'Original exception retained');error(p['error'])
            else:require(p['error'] is None,'Return cannot be exception')
            state=dict(stage=stage,raw=p)
        elif stage=='POSTCHECK':
            require(state is not None and state['stage'] in ('RAW_RETURNED','RAW_EXCEPTION'),'Raw before postcheck')
            require(set(p)=={'outcome','validation_error'},'Complete postcheck');outcome=p['outcome']
            require(outcome in ('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE'),'Terminal category')
            if state['stage']=='RAW_EXCEPTION':require(outcome=='EVALUATION_EXCEPTION' and p['validation_error'] is None,'Exception stays technical')
            else:require(outcome!='EVALUATION_EXCEPTION','Returned result is not invocation exception')
            if outcome in ('FEASIBLE','INFEASIBLE'):
                require(p['validation_error'] is None and state['raw']['result_preserved_as_json'] is True,'Accepted JSON return')
                exact(state['raw']['result'],arithmetic(row,task),'Independent entire saved result')
                require(state['raw']['result']['status']==outcome,'Matched economic status');arithmetic_count+=1
            if outcome=='VALIDATION_FAILURE':error(p['validation_error'])
            terminals.append(dict(global_ordinal=cursor,task_id=task['task_id'],outcome=outcome));cursor+=1;state=None
        else:raise ValueError('Unknown journal stage')
        record_index.append(dict(sequence=sequence,byte_start=offset,byte_stop=offset+len(part)+1,record_sha256=value['record_sha256'],stage=stage,global_ordinal=task['global_ordinal']))
        offset+=len(part)+1;previous=value['record_sha256']
    require(not tail or cursor<stop,'Trailing bytes after all tasks')
    unresolved=cursor if cursor<stop and (state is not None or bool(tail)) else None
    undispatched_start=cursor+int(unresolved is not None)
    return dict(schema='SINGLE_REPLACEMENT_SHARD_INDEPENDENT_ARITHMETIC_V1',status='PASS_SAVED_PREFIX',full_scenario_count=prepared['document']['scenario_count'],full_pair_count=prepared['document']['pair_count'],full_integer_count=prepared['document']['integer_count'],financial_integer_count_before_issuer=prepared['document']['financial_integer_count_before_issuer'],structurally_excluded_integer_count=prepared['document']['structurally_excluded_integer_count'],
                shard_start=start,shard_stop=stop,complete=cursor==stop and not tail and state is None,terminal_rows=terminals,arithmetic_checked_count=arithmetic_count,unresolved_ordinal=unresolved,undispatched_ordinals=list(range(undispatched_start,stop)),partial_tail_present=bool(tail),records=record_index,journal_sha256=hashlib.sha256(journal_bytes).hexdigest(),terminal_record_sha256=previous,
                scope='INDEPENDENT_SAVED_FRACTION_EVALUATION_AND_JOURNAL_PREFIX_NOT_SOURCE_AUTHENTICATION_OR_FULL_NDX',**FLAGS)

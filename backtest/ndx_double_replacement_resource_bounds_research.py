"""Normal-return structural byte bounds only; no evaluator, IO or authorization."""
import json
from fractions import Fraction as F
from math import lcm

def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digits(value):return len(str(abs(value)))
def rational_length(numerator,denominator):
    assert type(numerator)is int and numerator>=0 and type(denominator)is int and denominator>=1
    return 1+digits(numerator)+1+digits(denominator) # optional minus, slash; reduction only shortens

def pair_bound(case,pair,*,rule,flags,checks,full_count):
    row=case['identity']['original_input_row'];prices={s:F(v) for s,v in row['execution_prices'].items()}
    budget=F(pair['financial_bound']['joint_budget_usd']);costs=list(map(F,pair['financial_bound']['incoming_unit_costs_with_buy_fee_usd']))
    assert budget>0 and all(v>0 for v in costs)
    quantities=[int((budget-costs[1-i])//costs[i]) for i in range(2)];assert min(quantities)>=1
    outgoing=pair['outgoing_security_ids'];incoming=pair['incoming_security_ids'];holdings=row['holdings']
    after={s:holdings.get(s,0) for s in sorted(set(holdings)|set(prices))};signed={s:0 for s in after}
    for s in outgoing:after[s]=0;signed[s]=-holdings[s]
    for s,q in zip(incoming,quantities):after[s]=q;signed[s]=q
    identity=dict(schema='DOUBLE_REPLACEMENT_INTEGER_TASK_IDENTITY_V1',scenario_identity_sha256=case['identity_sha256'],rule=rule,outgoing_security_ids=outgoing,incoming_security_ids=incoming,sell_quantities=pair['sell_quantities'],buy_quantities=quantities)
    task=dict(task_id='f'*64,identity=identity,scenario_index=case['scenario_index'],pair_index=pair['pair_index'],global_ordinal=full_count-1,signed_trade_quantities=signed,proposed_holdings=after,evaluation_status='NOT_EVALUATED',**flags)
    denominator=lcm(*(v.denominator for v in prices.values()))
    amounts={s:int(prices[s]*denominator)*q for s,q in after.items() if q>0};stock=sum(amounts.values());assert stock>0
    # Every real point lies below this rectangle; integer stock S is in [1, stock].
    weight_length=rational_length(stock,stock)
    effective_length=rational_length(stock*stock,stock*stock)
    targets={s:F(v) for s,v in row['target_weights'].items()};target_den=lcm(*(v.denominator for v in targets.values()))
    l1_den=stock*target_den;l1_num=int((1+sum(map(abs,targets.values()),F()))*l1_den)
    # Common denominator for all monetary fields, including cash/flow and fees.
    rate=F(row['transaction_cost_bps'])/10000;cash=F(row['starting_cash_usd']);flow=F(row['cash_event']['amount_usd'])
    money_den=lcm(denominator*rate.denominator,cash.denominator,flow.denominator)
    sell=sum((prices[s]*holdings[s] for s in outgoing),F());buy=sum((prices[s]*q for s,q in zip(incoming,quantities)),F())
    fees=(sell+buy)*abs(rate);remaining=abs(cash)+abs(flow)+sell+buy+fees
    magnitude=remaining+F(stock,denominator)+fees
    money_num=(magnitude*money_den).__ceil__();money_length=rational_length(money_num,money_den)
    risk=dict(checks=dict.fromkeys(checks,False),all_passed=False,weights={s:'9'*weight_length for s in amounts},effective_n='9'*effective_length,positive_holding_count=len(amounts),risk_chain_weights={row['securities'][s]['risk_chain']:'9'*weight_length for s in amounts})
    value=dict(status='INFEASIBLE',feasible=False,financial_checks=dict(NONNEGATIVE_CASH=False,CASH_BUFFER=False),risk=risk,issuer_conflicts={},original_target_stock_l1='9'*rational_length(l1_num,l1_den))
    for key in ('gross_sell_usd','gross_buy_usd','sell_fee_usd','buy_fee_usd','total_fee_usd','cash_after_usd','invested_stock_usd','equity_after_usd','cash_flow_adjusted_pnl_usd'):value[key]='9'*money_length
    result=dict(supplied_index=9999,plan=dict(global_ordinal=full_count-1,task=task),status='INFEASIBLE',evaluation=value)
    return dict(row_bytes=len(encode(result)),count=pair['enumerable_integer_count'],quantity_max=max(quantities),money_chars=money_length,weight_chars=weight_length,effective_chars=effective_length,l1_chars=rational_length(l1_num,l1_den),task_bytes=len(encode(task)))

def gzip_default_zlib_bound(size):
    # zlib compressBound default window/memlevel formula, plus full gzip framing.
    # Conditional on frozen zlib algorithm; 13 includes zlib wrapper, so +18 overcounts.
    assert type(size)is int and size>=0
    return size+(size>>12)+(size>>14)+(size>>25)+13+18

def aggregate(rows,header_bytes,batch_size):
    assert type(batch_size)is int and 1<=batch_size<=10000 and rows
    count=sum(r['count'] for r in rows);batches=(count+batch_size-1)//batch_size
    maximum=max(r['row_bytes'] for r in rows)
    raw_total=sum(r['count']*(r['row_bytes']+1) for r in rows)+batches*header_bytes
    # Sum floor(x/k)<=floor(sum(x)/k); per-stream constants remain per batch.
    compressed_total=raw_total+(raw_total>>12)+(raw_total>>14)+(raw_total>>25)+31*batches
    maximum_raw=header_bytes+batch_size*(maximum+1)
    return dict(point_count=count,batch_size=batch_size,batch_count=batches,max_normal_raw_bytes=maximum_raw,max_normal_gzip_bytes=gzip_default_zlib_bound(maximum_raw),full_normal_raw_bytes_upper=raw_total,full_normal_gzip_bytes_upper=compressed_total,metadata_disk_bytes_proved=False,memory_bytes_proved=False,dispatch_authorized=False)

"""Normal-return structural byte bounds only; no evaluator, IO or authorization."""
import json
from fractions import Fraction as F
from math import lcm,gcd
from backtest import ndx_two_positive_integer_budget_domain_research as budget_math

def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digits(value):return len(str(abs(value)))
def rational_length(numerator,denominator):
    assert type(numerator)is int and numerator>=0 and type(denominator)is int and denominator>=1
    return 1+digits(numerator)+1+digits(denominator) # optional minus, slash; reduction only shortens

def positive_length(numerator,denominator):
    assert numerator>=0 and denominator>=1
    return digits(numerator)+(0 if denominator==1 else 1+digits(denominator))

def bounded_fraction_text(maximum,denominator,negative=False):
    numerator=(maximum*denominator).__floor__()
    return '9'*(positive_length(numerator,denominator)+int(negative))

def pair_bound(case,pair,*,rule,flags,checks,full_count):
    row=case['identity']['original_input_row'];prices={s:F(v) for s,v in row['execution_prices'].items()}
    budget=F(pair['financial_bound']['joint_budget_usd']);costs=list(map(F,pair['financial_bound']['incoming_unit_costs_with_buy_fee_usd']))
    quantities=[int((budget-costs[1-i])//costs[i]) for i in range(2)];assert min(quantities)>=1
    outgoing=pair['outgoing_security_ids'];incoming=pair['incoming_security_ids'];holdings=row['holdings']
    after={s:holdings.get(s,0) for s in sorted(set(holdings)|set(prices))};signed={s:0 for s in after}
    for s in outgoing:after[s]=0;signed[s]=-holdings[s]
    for s,q in zip(incoming,quantities):after[s]=q;signed[s]=q
    identity=dict(schema='DOUBLE_REPLACEMENT_INTEGER_TASK_IDENTITY_V1',scenario_identity_sha256=case['identity_sha256'],rule=rule,outgoing_security_ids=outgoing,incoming_security_ids=incoming,sell_quantities=pair['sell_quantities'],buy_quantities=quantities)
    last=pair['first_global_ordinal']+pair['enumerable_integer_count']-1
    task=dict(task_id='f'*64,identity=identity,scenario_index=case['scenario_index'],pair_index=pair['pair_index'],global_ordinal=last,signed_trade_quantities=signed,proposed_holdings=after,evaluation_status='NOT_EVALUATED',**flags)
    rate=F(row['transaction_cost_bps'])/10000;assert rate>=0
    cash=F(row['starting_cash_usd']);flow=F(row['cash_event']['amount_usd']);buffer=F(row['minimum_cash_buffer_usd']);assert cash>=0 and flow>=0 and buffer>=0
    sale=sum((prices[s]*holdings[s] for s in outgoing),F());sell_fee=sale*rate
    retained={s:prices[s]*q for s,q in holdings.items() if q>0 and s not in outgoing}
    buy_max=budget/(1+rate);buy_min=sum((prices[s] for s in incoming),F())
    amount_max={**retained,**{s:prices[s]*q for s,q in zip(incoming,quantities)}}
    price_den=lcm(*(v.denominator for v in amount_max.values()),*(prices[s].denominator for s in incoming))
    lattice=gcd(*(int(v*price_den) for v in retained.values()),*(int(prices[s]*price_den) for s in incoming))
    assert lattice>0
    stock_max=sum(retained.values(),F())+buy_max
    stock_integer=(stock_max*price_den/lattice).__floor__()
    weight_limits={s:positive_length((v*price_den/lattice).__floor__(),stock_integer) for s,v in amount_max.items()}
    chain_amounts={}
    for s,v in amount_max.items():
        chain=row['securities'][s]['risk_chain'];chain_amounts[chain]=chain_amounts.get(chain,F())+v
    chain_limits={s:positive_length((min(v,stock_max)*price_den/lattice).__floor__(),stock_integer) for s,v in chain_amounts.items()}
    square_max=sum(((v*price_den/lattice).__floor__()**2 for v in amount_max.values()))
    effective_length=positive_length(stock_integer**2,min(square_max,stock_integer**2))
    targets={s:F(v) for s,v in row['target_weights'].items()};target_den=lcm(*(v.denominator for v in targets.values()))
    l1_den=stock_integer*target_den;l1_num=((1+sum(map(abs,targets.values()),F()))*l1_den).__floor__()
    risk=dict(checks=dict.fromkeys(checks,False),all_passed=False,weights={s:'9'*n for s,n in weight_limits.items()},effective_n='9'*effective_length,positive_holding_count=len(amount_max),risk_chain_weights={s:'9'*n for s,n in chain_limits.items()})
    buy_den=lcm(*(prices[s].denominator for s in incoming));buy_fee_den=buy_den*rate.denominator
    fees_den=lcm(sell_fee.denominator,buy_fee_den);fees_max=sell_fee+buy_max*rate
    cash_den=lcm(cash.denominator,flow.denominator,sale.denominator,buy_den,fees_den)
    cash_max=cash+flow+sale-sell_fee-buy_min*(1+rate)
    before=sum((prices[s]*q for s,q in holdings.items()),F())
    equity_max=cash+flow+before # fees nonnegative; no price changes between sale/buy
    equity_den=lcm(cash.denominator,flow.denominator,before.denominator,fees_den)
    value=dict(status='INFEASIBLE',feasible=False,gross_sell_usd=str(sale),gross_buy_usd=bounded_fraction_text(buy_max,buy_den),sell_fee_usd=str(sell_fee),buy_fee_usd=bounded_fraction_text(buy_max*rate,buy_fee_den),total_fee_usd=bounded_fraction_text(fees_max,fees_den),cash_after_usd=bounded_fraction_text(cash_max,cash_den),invested_stock_usd=bounded_fraction_text(stock_max,price_den),equity_after_usd=bounded_fraction_text(equity_max,equity_den),cash_flow_adjusted_pnl_usd=bounded_fraction_text(fees_max,fees_den,True),financial_checks=dict(NONNEGATIVE_CASH=True,CASH_BUFFER=True),risk=risk,issuer_conflicts={},original_target_stock_l1='9'*positive_length(l1_num,l1_den))
    result=dict(supplied_index=9999,plan=dict(global_ordinal=last,task=task),status='INFEASIBLE',evaluation=value)
    savings=0
    for i,qmax in enumerate(quantities):
        for width in range(1,digits(qmax)):
            savings+=3*budget_math.prefix_count(a=costs[i],b=costs[1-i],budget=budget,max_q1=10**width-1)
    for width in range(1,digits(last)):
        savings+=2*max(0,min(pair['enumerable_integer_count'],10**width-pair['first_global_ordinal']))
    return dict(field_char_bounds={k:len(v) for k,v in value.items() if type(v)is str},weight_char_bounds=weight_limits,chain_char_bounds=chain_limits,integer_digit_savings=savings,row_bytes=len(encode(result)),count=pair['enumerable_integer_count'],quantity_max=max(quantities),money_chars=max(len(value[k]) for k in value if k.endswith('_usd')),weight_chars=max(weight_limits.values()),effective_chars=effective_length,l1_chars=positive_length(l1_num,l1_den),task_bytes=len(encode(task)),lattice_gcd=lattice)

def gzip_default_zlib_bound(size):
    # zlib compressBound default window/memlevel formula, plus full gzip framing.
    # Conditional on frozen zlib algorithm; 13 includes zlib wrapper, so +18 overcounts.
    assert type(size)is int and size>=0
    return size+(size>>12)+(size>>14)+(size>>25)+13+18

def aggregate(rows,header_bytes,batch_size):
    assert type(batch_size)is int and 1<=batch_size<=10000 and rows
    count=sum(r['count'] for r in rows);batches=(count+batch_size-1)//batch_size
    maximum=max(r['row_bytes'] for r in rows)
    raw_total=sum(r['count']*(r['row_bytes']+1)-r.get('integer_digit_savings',0) for r in rows)+batches*header_bytes
    # Sum floor(x/k)<=floor(sum(x)/k); per-stream constants remain per batch.
    compressed_total=raw_total+(raw_total>>12)+(raw_total>>14)+(raw_total>>25)+31*batches
    maximum_raw=header_bytes+batch_size*(maximum+1)
    return dict(point_count=count,batch_size=batch_size,batch_count=batches,max_normal_raw_bytes=maximum_raw,max_normal_gzip_bytes=gzip_default_zlib_bound(maximum_raw),full_normal_raw_bytes_upper=raw_total,full_normal_gzip_bytes_upper=compressed_total,metadata_disk_bytes_proved=False,memory_bytes_proved=False,dispatch_authorized=False)

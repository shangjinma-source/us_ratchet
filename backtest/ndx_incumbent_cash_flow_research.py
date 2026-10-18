"""Exact conditional incumbent Close-plan/Open-fill signed-flow research kernel.

No external data, producer imports, weight normalization, Open replanning or risk
optimization. Original risk constraints are observations, not order gates.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from fractions import Fraction

SCHEMA='SIGNED_FLOW_FROZEN_INCUMBENT_OPEN_ACCOUNT_V1'
CASH_TOLERANCE=Fraction(1,10**8)
RISK_TOLERANCE=Fraction(1,10**9)
RISK_KEYS=('max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap')
CHECKS=('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')


def require(ok,message):
    if not ok: raise ValueError(message)


def number(value):
    require(type(value) in (str,int,Decimal),'Explicit decimal literal required, not bool/float')
    if type(value) is str: require(0<len(value)<=80 and value.strip()==value,'Bounded decimal literal required')
    if type(value) is int: require(abs(value)<=10**40,'Numeric bound exceeded')
    parsed=Decimal(value)
    require(parsed.is_finite() and len(parsed.as_tuple().digits)<=40 and abs(parsed.as_tuple().exponent)<=40,'Finite bounded decimal required')
    result=Fraction(parsed); require(0<=result<=10**40,'Nonnegative bounded value required')
    return result


def day(value):
    require(type(value) is str and date.fromisoformat(value).isoformat()==value,'Canonical session required')
    return value


def ratio(value):
    require(max(abs(value.numerator).bit_length(),value.denominator.bit_length())<=12000,'Exact ratio resource bound exceeded')
    return {'numerator':str(value.numerator),'denominator':str(value.denominator)}


def money(value):
    denominator=value.denominator; twos=fives=0
    while denominator%2==0: denominator//=2; twos+=1
    while denominator%5==0: denominator//=5; fives+=1
    require(denominator==1,'Nonterminating monetary value')
    places=max(twos,fives); integer=value.numerator*2**(places-twos)*5**(places-fives)
    sign='-' if integer<0 else ''; digits=str(abs(integer)).zfill(places+1)
    return sign+digits if not places else sign+(digits[:-places]+'.'+digits[-places:]).rstrip('0').rstrip('.')


def shares(values):
    require(type(values) is dict and len(values)<=256,'Bounded holdings map required')
    require(all(type(sid) is str and sid and sid.strip()==sid and type(q) is int and 0<=q<=10**12 for sid,q in values.items()),'Canonical SID whole shares required')
    return dict(sorted(values.items()))


def marks(values,universe):
    require(type(values) is dict and set(values)==universe,'Exact complete old-and-target price domain required')
    result={sid:number(values[sid]) for sid in sorted(universe)}
    require(all(value>0 for value in result.values()),'Positive marks required')
    return result


def equity(cash,holdings,prices):
    return cash+sum((q*prices[sid] for sid,q in holdings.items()),Fraction(0))


def observed_risk(holdings,prices,securities,parameters):
    values={sid:q*prices[sid] for sid,q in sorted(holdings.items()) if q>0}
    total=sum(values.values(),Fraction(0))
    common={'risk_is_order_gate':False,'target_slot_count':len(holdings),
            'zero_share_security_ids':sorted(sid for sid,q in holdings.items() if q==0),'positive_holding_count':len(values)}
    if not total: return dict(common,checks={'ALL_CASH':False},all_passed=False,weights={},effective_n=None,risk_chain_weights={})
    weights={sid:value/total for sid,value in values.items()}; ordered=sorted(weights.values(),reverse=True)
    neff=1/sum((value*value for value in weights.values()),Fraction(0)); chains={}
    for sid,value in weights.items():
        chain=securities[sid]['risk_chain']; chains[chain]=chains.get(chain,Fraction(0))+value
    passed=(ordered[0]<=parameters['max_single_weight']+RISK_TOLERANCE,
        ordered[-1]>=parameters['min_single_weight']-RISK_TOLERANCE,
        sum(ordered[:3])<=parameters['top_weight_cap']+RISK_TOLERANCE,
        neff>=parameters['minimum_effective_n_ratio']*len(values)-RISK_TOLERANCE,
        max(chains.values())<=parameters['risk_chain_top1_cap']+RISK_TOLERANCE)
    return dict(common,checks=dict(zip(CHECKS,passed)),all_passed=all(passed),
        weights={sid:ratio(w) for sid,w in weights.items()},effective_n=ratio(neff),
        risk_chain_weights={chain:ratio(w) for chain,w in chains.items()})


def simulate_incumbent_cash_flow(*,initial,sessions,fixed_weights,schedule,securities,risk_parameters,
        transaction_cost_bps,minimum_cash_buffer_usd,max_projection_reductions=100000):
    require(type(initial) is dict and set(initial)=={'session','cash_usd','holdings','close_prices'},'Exact initial contract required')
    require(type(sessions) is list and 1<=len(sessions)<=512,'Bounded daily path required')
    require(type(fixed_weights) is dict and fixed_weights,'Explicit fixed original weights required')
    before=shares(initial['holdings']); targets=set(fixed_weights); universe=set(before)|targets
    require(len(universe)<=256 and all(type(sid) is str and sid and sid.strip()==sid for sid in universe),'Bounded SID domain required')
    require(type(securities) is dict and set(securities)==universe,'Full risk and identity metadata required')
    for item in securities.values():
        require(type(item) is dict and set(item)=={'issuer_id','ticker','risk_chain'}
                and all(type(v) is str and v and v.strip()==v for v in item.values()),'Explicit metadata fields required')
    require(len({securities[sid]['issuer_id'] for sid in targets})==len(targets),'Fixed target issuer uniqueness required')
    require(len({item['ticker'] for item in securities.values()})==len(universe),'Ticker collision unsupported')
    weights={sid:number(fixed_weights[sid]) for sid in sorted(targets)}
    require(all(value>0 for value in weights.values()) and abs(sum(weights.values(),Fraction(0))-1)<=Fraction(1,10**12),'Original positive weights must sum to one within 1e-12; no normalization')
    require(type(risk_parameters) is dict and set(risk_parameters)==set(RISK_KEYS),'Original five risk parameters required')
    risk_args={key:number(value) for key,value in risk_parameters.items()}
    require(all(0<value<=1 for value in risk_args.values()) and risk_args['min_single_weight']<=risk_args['max_single_weight'],'Risk parameter range')
    fee_bps,buffer=number(transaction_cost_bps),number(minimum_cash_buffer_usd)
    require(fee_bps<=10000,'Fee rate range'); rate=fee_bps/10000
    require(type(max_projection_reductions) is int and 0<=max_projection_reductions<=1000000,'Bounded integer reduction budget required')
    initial_day=day(initial['session']); initial_prices=marks(initial['close_prices'],universe)
    cash=number(initial['cash_usd']); previous_equity=equity(cash,before,initial_prices)
    require(previous_equity>0,'Positive initial equity required')
    parsed=[]; calendar=[initial_day]
    for item in sessions:
        require(type(item) is dict and set(item)=={'session','open_prices','close_prices','cash_injection_usd'},'Exact daily schema required')
        session=day(item['session']); calendar.append(session)
        parsed.append((session,marks(item['open_prices'],universe),marks(item['close_prices'],universe),number(item['cash_injection_usd'])))
    require(calendar==sorted(set(calendar)),'Strictly increasing complete observed sessions required')
    require(type(schedule) is list and 1<=len(schedule)<=len(sessions),'Explicit bounded decision schedule required')
    by_decision={}
    for item in schedule:
        require(type(item) is dict and set(item)=={'decision_date','execution_date'},'Exact decision/execution schedule required')
        decision,execution=day(item['decision_date']),day(item['execution_date'])
        require(decision in calendar[:-1] and calendar[calendar.index(decision)+1]==execution
                and decision not in by_decision,'Next observed Open required; duplicate/missing decision')
        by_decision[decision]=execution
    require(list(by_decision)==sorted(by_decision) and next(iter(by_decision))==initial_day,'Initial and ordered original schedule required')
    decisions=[]; executions=[]; trades=[]; daily=[]; reduction_count=0

    def project(current_cash,current,wanted,prices):
        delta={sid:wanted.get(sid,0)-current.get(sid,0) for sid in sorted(set(current)|set(wanted))}
        buy=sum((q*prices[sid] for sid,q in delta.items() if q>0),Fraction(0))
        sell=sum((-q*prices[sid] for sid,q in delta.items() if q<0),Fraction(0))
        fees=(buy+sell)*rate
        return current_cash-buy+sell-fees,buy,sell,fees,delta

    def financially_valid(value): return value>=0 and value>=buffer-CASH_TOLERANCE

    def freeze(session,current_cash,current,prices):
        nonlocal reduction_count
        investable=equity(current_cash,current,prices)-buffer
        require(investable>0,'No positive investable capital at decision Close')
        original_floor={sid:(investable*weights[sid]/prices[sid]).numerator//(investable*weights[sid]/prices[sid]).denominator for sid in weights}
        require(all(q<=10**12 for q in original_floor.values()),'Desired share engineering cap')
        wanted=dict(original_floor); reductions=[]
        def reduce_one(stage,eligible):
            nonlocal reduction_count
            require(reduction_count<max_projection_reductions,'ENGINEERING_REDUCTION_BUDGET_EXHAUSTED_NOT_ECONOMIC_INFEASIBILITY')
            sid=max(eligible,key=lambda key:(prices[key],key)); before_q=wanted[sid]; wanted[sid]-=1; reduction_count+=1
            reductions.append({'stage':stage,'security_id':sid,'before_shares':before_q,'after_shares':wanted[sid]})
        # Actual frozen dynamic first stage protects each positive one-share slot.
        while all(q>=1 for q in wanted.values()) and not financially_valid(project(current_cash,current,wanted,prices)[0]):
            eligible=[sid for sid,q in wanted.items() if q>1]
            if not eligible: break
            reduce_one('DYNAMIC_FIRST_STAGE_KEEP_ONE',eligible)
        projection_used=False
        if not financially_valid(project(current_cash,current,wanted,prices)[0]):
            projection_used=True; wanted=dict(original_floor)
            # Financial fallback restarts from floor, allows every target slot to zero.
            while not financially_valid(project(current_cash,current,wanted,prices)[0]):
                eligible=[sid for sid,q in wanted.items() if q>0]
                if not eligible:
                    decisions.append({'decision_date':session,'execution_date':by_decision[session],'status':'NO_PLAN',
                        'shares_before':dict(current),'cash_before_usd':money(current_cash),'prices':{sid:money(value) for sid,value in prices.items()},
                        'original_floor_shares':original_floor,'reductions':reductions,'projection_used':True,
                        'reason':'NO_FINANCIALLY_FEASIBLE_FLOOR_REDUCTION','risk_is_order_gate':False})
                    return None
                reduce_one('CONTROL_FINANCIAL_PROJECTION_ALLOW_ZERO',eligible)
        after,buy,sell,fees,delta=project(current_cash,current,wanted,prices)
        record={'decision_date':session,'execution_date':by_decision[session],'status':'FROZEN',
            'shares_before':dict(current),'cash_before_usd':money(current_cash),'prices':{sid:money(value) for sid,value in prices.items()},
            'original_fixed_weights':{sid:str(fixed_weights[sid]) for sid in weights},'investable_before_future_flow_usd':money(investable),
            'original_floor_shares':original_floor,'desired_shares':dict(wanted),'delta':delta,
            'projected_cash_usd':money(after),'projected_buy_usd':money(buy),'projected_sell_usd':money(sell),'projected_fees_usd':money(fees),
            'reductions':reductions,'projection_used':projection_used,'risk':observed_risk(wanted,prices,securities,risk_args),
            'risk_is_order_gate':False,'future_open_flow_included_in_plan':False}
        decisions.append(record); return deepcopy(record)

    pending=freeze(initial_day,cash,before,initial_prices)
    initial_equity=previous_equity; cumulative=Fraction(1); total_flow=total_fees=Fraction(0); previous_day=initial_day
    initial_risk=observed_risk(before,initial_prices,securities,risk_args)
    for session,opens,closes,injection in parsed:
        old_cash=cash; old_holdings=dict(before); open_before=equity(cash,before,opens)
        open_after=open_before+injection
        require(previous_equity>0 and open_before>0 and open_after>0,'Undefined zero-equity TWR boundary')
        cash+=injection; paid_fee=Fraction(0); actual_delta={}; status='NO_FROZEN_ORDER'
        if pending is not None:
            require(pending['execution_date']==session,'Frozen order execution clock mismatch')
            wanted=pending['desired_shares']; after,buy,sell,fees,delta=project(cash,before,wanted,opens)
            require(delta==pending['delta'],'Frozen signed delta changed; no automatic replan')
            failures=[]
            if after<0: failures.append('NONNEGATIVE_CASH')
            if after<buffer-CASH_TOLERANCE: failures.append('CASH_BUFFER')
            status='REJECTED' if failures else 'FILLED'
            record={'session':session,'decision_date':pending['decision_date'],'status':status,'failure_reasons':failures,
                'frozen_delta':dict(delta),'desired_shares':dict(wanted),'shares_before':dict(before),
                'cash_before_flow_usd':money(old_cash),'cash_injection_usd':money(injection),'cash_before_trade_usd':money(cash),
                'prices':{sid:money(value) for sid,value in opens.items()},'projected_cash_usd':money(after),
                'projected_buy_usd':money(buy),'projected_sell_usd':money(sell),'projected_fees_usd':money(fees),
                'desired_risk':observed_risk(wanted,opens,securities,risk_args),'risk_is_order_gate':False}
            if not failures:
                require(equity(after,wanted,opens)==open_after-fees,'Signed self-financing mismatch')
                cash=after; before=dict(wanted); paid_fee=fees; actual_delta=dict(delta)
                for sid,q in delta.items():
                    if q:
                        trades.append({'session':session,'security_id':sid,'signed_share_delta':q,'price_usd':money(opens[sid]),
                            'fee_usd':money(abs(q)*opens[sid]*rate),'external_cash_flow':False})
            record.update(cash_after_usd=money(cash),shares_after=dict(before),actual_fees_usd=money(paid_fee),
                actual_risk=observed_risk(before,opens,securities,risk_args))
            executions.append(record); pending=None
        closing=equity(cash,before,closes); overnight=open_before/previous_equity; post_flow=closing/open_after
        cumulative*=overnight*post_flow; total_flow+=injection; total_fees+=paid_fee
        daily.append({'session':session,'previous_close_session':previous_day,'previous_close_equity_usd':money(previous_equity),
            'pre_flow_open_equity_usd':money(open_before),'post_flow_pre_fee_open_equity_usd':money(open_after),
            'cash_injection_usd':money(injection),'cash_before_usd':money(old_cash),'cash_after_usd':money(cash),
            'holdings_before':old_holdings,'holdings_after':dict(before),'signed_share_delta':actual_delta,'execution_status':status,
            'fees_usd':money(paid_fee),'close_equity_usd':money(closing),
            'overnight_return':ratio(overnight-1),'after_flow_return':ratio(post_flow-1),'session_twr':ratio(overnight*post_flow-1),
            'cumulative_twr':ratio(cumulative-1),'overnight_pnl_usd':money(open_before-previous_equity),
            'cash_flow_adjusted_pnl_usd':money(closing-previous_equity-injection),
            'risk':observed_risk(before,closes,securities,risk_args)})
        if session in by_decision: pending=freeze(session,cash,before,closes)
        previous_equity=closing; previous_day=session
    require(pending is None,'Unexecuted frozen plan outside supplied path')
    return {'schema':SCHEMA,'initial':deepcopy(initial),'sessions':deepcopy(sessions),'schedule':deepcopy(schedule),
        'original_fixed_weights':deepcopy(fixed_weights),'original_weight_sum':ratio(sum(weights.values(),Fraction(0))),
        'weights_normalized':False,'securities':deepcopy(securities),'risk_parameters':deepcopy(risk_parameters),
        'transaction_cost_bps':str(transaction_cost_bps),'minimum_cash_buffer_usd':str(minimum_cash_buffer_usd),
        'cash_buffer_tolerance':ratio(CASH_TOLERANCE),'negative_cash_allowed':False,'risk_tolerance':ratio(RISK_TOLERANCE),
        'initial_risk':initial_risk,'decisions':decisions,'executions':executions,'trades':trades,'daily':daily,
        'initial_equity_usd':money(initial_equity),'terminal_equity_usd':money(previous_equity),
        'total_cash_injection_usd':money(total_flow),'total_fees_usd':money(total_fees),'chained_twr':ratio(cumulative-1),
        'net_dollar_pnl_excluding_injections_usd':money(previous_equity-initial_equity-total_flow),
        'flow_policy':'FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN','execution_policy':'DECISION_CLOSE_FROZEN_SIGNED_DELTA_NEXT_OPEN_ATOMIC',
        'cash_event_timing':'AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES',
        'reduction_count':reduction_count,'max_projection_reductions':max_projection_reductions,
        'risk_metadata_policy':'CALLER_SUPPLIED_STATIC_LABELS_NOT_HISTORICAL_AVAILABILITY_CERTIFICATE',
        'risk_is_order_gate':False,'open_replan_performed':False,'candidate_eligibility_claimed':False,
        'dividends_modelled':False,'corporate_actions_modelled':False,'fx_modelled':False,'cash_interest_modelled':False,
        'withdrawals_supported':False,'orders_executed':False,'point_in_time_verified':False,'promotion_allowed':False,
        'old_experiments_executed':False,'arithmetic':'EXACT_FRACTION_NOT_LEGACY_FLOAT_BITWISE',
        'parameter_authority':'CALLER_SUPPLIED_RESEARCH_CONTRACT_NOT_SOURCE_BOUND'}

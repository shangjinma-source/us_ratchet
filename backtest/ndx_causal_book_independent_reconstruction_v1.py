"""Independent, IO-free reconstruction of complete whole-share V2 saved paths.

No producer import, validator, replay callback, source reader or supplied risk
boolean is used. Matching an explicit synthetic path does not authenticate its
prices, identity, clock or investment policy. Continuous quantities are excluded.
"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import math
import re

TARGET_SCHEMA = 'CAUSAL_RESEARCH_BOOK_MECHANICS_V2'
STATE_SCHEMA = 'CAUSAL_RESEARCH_BOOK_STATE_V2'
TARGET_SOURCE_SHA256 = 'b8ad5d0a03f775d53a3767f9fc6678c513de303595d5bfd9216551eacaad5f94'
CONTRACT_SHA256 = '1b5aa8e2d48dc33adf089dc3f291c5c09cd7b01cf3ac45710e60c8ca6d6a6ee1'
RISK_REFERENCE = dict(path='backtest/ndx_dynamic_whole_lot_repair_path.py',sha256='e614be1a2fe461e483e17413af03153f9a2fe99c31e0412b5daa8954c53d3f34',json_pointer='/_risk_snapshot')
FLAGS = dict.fromkeys(('source_authenticity_verified','point_in_time_verified','current_account_verified','objective_registered','action_policy_registered','fit_called','solver_called','execution_authorized','promotion_allowed','future_oos'),False)
COVERAGE = ('prices','identity_risk','corporate_events','calendar','cashflow')
ROLES = ('open_prices','close_prices','decision_prices','identity_risk','corporate_events','calendar')
LIMITS = dict(frames=512,sids=256,shares=10**12,ids=4096,ratio_bits=12000,json_depth=64,json_nodes=200000)


def insist(condition, message):
    if not condition: raise ValueError(message)


def serialize(value):
    pending=[(value,0)]; count=0
    while pending:
        obj,depth=pending.pop(); count+=1
        insist(depth<=64 and count<=200000,'JSON resource domain')
        insist(type(obj) in (dict,list,str,int,bool,type(None)),'Closed JSON types')
        if type(obj) is dict:
            insist(all(type(k) is str for k in obj),'String JSON keys')
            pending.extend((v,depth+1) for v in obj.values())
        elif type(obj) is list: pending.extend((v,depth+1) for v in obj)
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def fingerprint(value): return hashlib.sha256(serialize(value)).hexdigest()


def equal(left,right,label): insist(serialize(left)==serialize(right),label)


def fields(obj,names,label):
    insist(type(obj) is dict and set(obj)==set(names.split()),label+' fields')


def name(value):
    insist(type(value) is str and re.fullmatch('[A-Za-z0-9_.:/-]{1,128}',value) is not None,'Identifier domain')


def hash_text(value):
    insist(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None,'SHA syntax')


def ref(value):
    fields(value,'path sha256 json_pointer','Reference')
    insist(type(value['path']) is str and 0<len(value['path'])<=4096 and value['path'].strip()==value['path'],'Path declaration')
    hash_text(value['sha256']); p=value['json_pointer']
    insist(type(p) is str and len(p)<=4096 and (not p or p.startswith('/')),'Pointer declaration')


def session(value):
    insist(type(value) is str and date.fromisoformat(value).isoformat()==value,'Canonical date')


def clock(value):
    insist(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?Z',value) is not None and '.000000Z' not in value,'Canonical UTC')
    return datetime.fromisoformat(value[:-1]+'+00:00')


def amount(value):
    insist(type(value) is str and len(value)<=82 and re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?',value) is not None,'Canonical money')
    decimal=Decimal(value); parts=decimal.as_tuple()
    insist(decimal.is_finite() and len(parts.digits)<=40 and abs(parts.exponent)<=40,'Money resource domain')
    return Fraction(decimal)


def decimal_text(value):
    insist(value>=0,'Negative cash')
    n,d=value.numerator,value.denominator; power=0
    while d!=1 and power<=80:
        common=math.gcd(d,10)
        insist(common>1,'Nonterminating money')
        n*=10//common; d//=common; power+=1
    insist(d==1,'Money scale bound')
    digits=str(n).zfill(power+1)
    out=digits if power==0 else (digits[:-power]+'.'+digits[-power:]).rstrip('0').rstrip('.')
    return out


def rational(value):
    insist(max(abs(value.numerator).bit_length(),value.denominator.bit_length())<=12000,'Ratio resource domain')
    return dict(numerator=str(value.numerator),denominator=str(value.denominator))


def shares(value):
    insist(type(value) is dict and len(value)<=256,'SID resource domain')
    for sid,q in value.items():
        name(sid); insist(type(q) is int and 0<=q<=10**12,'Whole-share domain')
    return dict(sorted(value.items()))


def reasons(value):
    insist(type(value) is list and len(value)<=256,'Blocker domain')
    for item in value: name(item)
    insist(value==sorted(set(value)),'Canonical blockers')


def seal(obj):
    obj['content_sha256']=fingerprint(obj)
    return obj


def read_context(context):
    fields(context,'input_scope numeric_coverage source_references_by_role full_inventory_reference eligibility_blockers authority','Context')
    insist(context['input_scope'] in ('SYNTHETIC_EXPLICIT','CONDITIONAL_SOURCE_BOUND'),'Context scope')
    fields(context['numeric_coverage'],' '.join(COVERAGE),'Coverage')
    gaps=[]
    for key,status in context['numeric_coverage'].items():
        insist(status in ('DECLARED_COMPLETE','MISSING'),'Coverage status')
        if status=='MISSING': gaps.append('MISSING_'+key.upper())
    fields(context['source_references_by_role'],' '.join(ROLES),'Source roles')
    for role,value in context['source_references_by_role'].items():
        if value is None: gaps.append('MISSING_REFERENCE_'+role.upper())
        else: ref(value)
    ref(context['full_inventory_reference']); reasons(context['eligibility_blockers'])
    equal(context['authority'],FLAGS,'Context authority')
    return gaps


def read_scenario(value):
    fields(value,'schema scenario_id currency quantity_domain book_lineage_id bootstrap_policy cashflow_schedule calendar lane_coordinate risk_policy_reference action_policy_reference source_requirements','Scenario')
    insist(value['schema']=='CAUSAL_RESEARCH_SCENARIO_V1' and value['currency']=='USD' and value['quantity_domain']=='WHOLE_SHARES','Scenario family')
    insist(value['bootstrap_policy']=='EXPLICIT_POSITIVE_PRIOR_CLOSE_RESEARCH','Bootstrap policy')
    for key in ('scenario_id','book_lineage_id'): name(value[key])
    fields(value['lane_coordinate'],'lane fx_mode lineage_kind','Lane')
    for item in value['lane_coordinate'].values(): name(item)
    for key in ('risk_policy_reference','action_policy_reference'): ref(value[key])
    equal(value['source_requirements'],list(COVERAGE),'Source obligations')
    cal=value['calendar']; insist(type(cal) is list and 2<=len(cal)<=513,'Calendar bound')
    previous=None
    for mark in cal:
        fields(mark,'session open_at_utc close_at_utc','Calendar mark'); session(mark['session'])
        op,cl=clock(mark['open_at_utc']),clock(mark['close_at_utc'])
        insist(op<cl and op.date().isoformat()==mark['session']==cl.date().isoformat(),'Session clocks')
        if previous: insist(previous['session']<mark['session'] and clock(previous['close_at_utc'])<op,'Calendar ordering')
        previous=mark
    flows=value['cashflow_schedule']; insist(type(flows) is list and len(flows)<=4096,'Flow limit')
    seen=set(); dates={row['session'] for row in cal[1:]}
    for flow in flows:
        fields(flow,'event_id session amount_usd available_at_utc','Scheduled flow'); name(flow['event_id']); session(flow['session']); amount(flow['amount_usd']); clock(flow['available_at_utc'])
        insist(flow['event_id'] not in seen and flow['session'] in dates,'Unique scheduled flow')
        seen.add(flow['event_id'])
    equal(flows,sorted(flows,key=lambda row:(row['session'],row['event_id'])),'Flow order')


def observe_risk(quantities,prices,identities):
    # Independent transcription of the frozen five float/tau algebra; the
    # sorted SID evaluation order is part of the whole-share mechanics format.
    exposure={sid:q*float(prices[sid]) for sid,q in sorted(quantities.items()) if q>0}
    if not exposure: return dict(status='NO_POSITIVE_STOCK_EXPOSURE_NOT_EVALUATED',all_passed=None,checks={},metrics={})
    total=sum(exposure.values()); insist(math.isfinite(total) and total>0,'Finite risk total')
    weights={sid:v/total for sid,v in exposure.items()}; ranked=sorted(weights.values(),reverse=True)
    effective=1/sum(w*w for w in ranked); buckets={}
    for sid,weight in weights.items():
        chain=identities[sid]['risk_chain']; buckets[chain]=buckets.get(chain,0.0)+weight
    tests=dict(MAX_SINGLE_WEIGHT=ranked[0]<=0.45+1e-9,MIN_SINGLE_WEIGHT=ranked[-1]>=0.05-1e-9,SECURITY_TOP3_WEIGHT=sum(ranked[:3])<=0.8+1e-9,MINIMUM_EFFECTIVE_N=effective>=0.7*len(ranked)-1e-9,RISK_CHAIN_TOP1_WEIGHT=max(buckets.values())<=0.55+1e-9)
    return dict(status='ORIGINAL_FLOAT_TAU_1E_MINUS9_OBSERVATION',all_passed=all(tests.values()),checks=tests,metrics=dict(actual_weights={sid:repr(weight) for sid,weight in weights.items()},top1_weight=repr(ranked[0]),minimum_single_weight=repr(ranked[-1]),top3_weight=repr(sum(ranked[:3])),effective_n=repr(effective),risk_chain_top1_weight=repr(max(buckets.values()))))


def make_state(scenario,index,quantities,cash,equity,cumulative,event_ids,action_ids,previous,input_hash,blockers):
    insist(equity>0 and cumulative>-1,'Positive close/factor')
    mark=scenario['calendar'][index]
    # Source/state decimal bounds do not cap derived intra-session notionals:
    # an old position can have a large Open and a small supplied Close.
    amount(decimal_text(cash)); amount(decimal_text(equity))
    return seal(dict(schema=STATE_SCHEMA,scenario_content_sha256=fingerprint(scenario),book_lineage_id=scenario['book_lineage_id'],sequence=index,session=mark['session'],phase='CLOSE',holdings_by_sid=shares(quantities),cash_usd=decimal_text(cash),close_equity_usd=decimal_text(equity),cumulative_twr=rational(cumulative),applied_event_ids=sorted(event_ids),applied_action_ids=sorted(action_ids),previous_state_sha256=previous,transition_input_sha256=input_hash,blockers=blockers,authority=dict(FLAGS),numeric_status='COMPUTED',readiness='SOURCE_BLOCKED',eligibility_blockers=list(blockers),close_at_utc=mark['close_at_utc']))


def genesis(scenario,initial,marks,context):
    gaps=read_context(context); fields(initial,'session close_at_utc holdings_by_sid cash_usd','Genesis inputs')
    cal=scenario['calendar'][0]
    insist(initial['session']==cal['session'] and initial['close_at_utc']==cal['close_at_utc'],'Genesis calendar')
    quantities=shares(initial['holdings_by_sid']); cash=amount(initial['cash_usd'])
    insist(type(marks) is dict,'Initial marks')
    for price in marks.values(): insist(amount(price)>0,'Positive initial price')
    if set(marks)!=set(quantities): gaps.append('MISSING_INITIAL_PRICE_COVERAGE')
    if gaps: return dict(schema=TARGET_SCHEMA,status='BLOCKED_INPUT',numeric_status='BLOCKED',readiness='SOURCE_BLOCKED',next_state=None,blockers=sorted(set(gaps)),authority=dict(FLAGS))
    equity=cash+sum((q*amount(marks[sid]) for sid,q in quantities.items()),Fraction())
    insist(equity>0,'UNSUPPORTED_ZERO_CAPITAL_INCEPTION')
    inherited=list(context['eligibility_blockers'])
    state=make_state(scenario,0,quantities,cash,equity,Fraction(),[],[],None,fingerprint(dict(initial_state=initial,initial_marks=marks,source_context=context)),inherited)
    return dict(schema=TARGET_SCHEMA,status='BOOTSTRAPPED_RESEARCH_ONLY',numeric_status='COMPUTED',readiness='SOURCE_BLOCKED',next_state=state,blockers=inherited,authority=dict(FLAGS))


def transition(scenario,prior,frame,action):
    fields(frame,'schema session previous_state_sha256 identity_risk_by_sid open_prices_usd close_prices_usd cashflow_events corporate_events source_context session_open_at_utc session_close_at_utc','Frame')
    index=prior['sequence']+1; insist(index<len(scenario['calendar']),'Calendar exhausted')
    cal=scenario['calendar'][index]
    insist(frame['schema']=='CAUSAL_RESEARCH_FRAME_V1' and frame['previous_state_sha256']==prior['content_sha256'],'Frame lineage')
    equal([frame['session'],frame['session_open_at_utc'],frame['session_close_at_utc']],[cal['session'],cal['open_at_utc'],cal['close_at_utc']],'Frame coordinate')
    context=frame['source_context']; gaps=read_context(context)
    insist(type(action) is dict and type(action.get('status')) is str,'Action union')
    pending=action['status']=='PENDING_ACTION_POLICY'; buys={}
    if pending:
        fields(action,'schema status reason decision_session execution_session','Pending action'); name(action['reason'])
    else:
        insist(action['status'] in ('EXPLICIT_BUY','EXPLICIT_NO_TRADE'),'Explicit disposition')
        fields(action,'schema status action_id decision_session decision_at_utc execution_session information_cutoff_utc decision_state_sha256 fill_baseline_sha256 frozen_baseline policy_reference source_references '+('buy_shares' if action['status']=='EXPLICIT_BUY' else 'reason'),'Explicit action')
        name(action['action_id']); insist(action['action_id'] not in prior['applied_action_ids'],'Duplicate action ID')
        insist(action['decision_state_sha256']==prior['content_sha256'],'Decision state')
        insist(clock(action['information_cutoff_utc'])<=clock(action['decision_at_utc']) and clock(prior['close_at_utc'])<=clock(action['decision_at_utc'])<clock(frame['session_open_at_utc']),'Causal decision clock')
        ref(action['policy_reference']); equal(action['policy_reference'],scenario['action_policy_reference'],'Action policy')
        expected_baseline=dict(schema='FROZEN_PRE_EVENT_ACTION_BASELINE_V1',phase='PRIOR_CLOSE_BEFORE_FRAME_EVENTS_AND_FLOW',previous_state_sha256=prior['content_sha256'],holdings_by_sid=prior['holdings_by_sid'],cash_usd=prior['cash_usd'],planned_cashflow_event_ids=sorted(f['event_id'] for f in frame['cashflow_events']))
        equal(action['frozen_baseline'],expected_baseline,'Frozen pre-event baseline'); equal(action['fill_baseline_sha256'],fingerprint(expected_baseline),'Baseline digest')
        fields(action['source_references'],'decision_prices identity_risk policy','Action source roles')
        for role,evidence in action['source_references'].items():
            fields(evidence,'reference available_at_utc stage','Decision evidence'); ref(evidence['reference'])
            insist(evidence['stage']=='DECISION_KNOWN_ONLY' and clock(evidence['available_at_utc'])<=clock(action['information_cutoff_utc']),'Future evidence')
            wanted=scenario['action_policy_reference'] if role=='policy' else context['source_references_by_role'][role]
            if wanted is not None: equal(evidence['reference'],wanted,'Decision evidence role')
        insist(all(action['source_references']['decision_prices']['reference']!=context['source_references_by_role'][role] for role in ('open_prices','close_prices')),'Realized price leakage')
        if action['status']=='EXPLICIT_BUY': buys=shares(action['buy_shares'])
        else: name(action['reason'])
    insist(action['schema']=='EXPLICIT_RESEARCH_ACTION_V1' and action['decision_session']==prior['session'] and action['execution_session']==frame['session'],'Action coordinates')
    old=dict(prior['holdings_by_sid']); universe=set(old)|set(buys); insist(len(universe)<=256,'Union SID bound')
    prices={}
    for role in ('open_prices_usd','close_prices_usd'):
        insist(type(frame[role]) is dict,'Price mapping')
        prices[role]={sid:amount(value) for sid,value in frame[role].items()}
        insist(all(v>0 for v in prices[role].values()),'Positive prices')
        if set(frame[role])!=universe: gaps.append('MISSING_EXACT_'+role.upper())
    identity=frame['identity_risk_by_sid']; insist(type(identity) is dict,'Identity mapping')
    for sid,row in identity.items():
        name(sid); fields(row,'issuer_id risk_chain','Identity'); name(row['issuer_id']); name(row['risk_chain'])
    if set(identity)!=universe: gaps.append('MISSING_EXACT_IDENTITY_RISK')
    flows=[f for f in scenario['cashflow_schedule'] if f['session']==frame['session']]
    equal(frame['cashflow_events'],flows,'Exact scheduled flow')
    for flow in flows: insist(clock(flow['available_at_utc'])<=clock(frame['session_open_at_utc']),'Flow availability')
    events=frame['corporate_events']; insist(type(events) is list and len(events)<=4096,'Event resources')
    event_ids=[f['event_id'] for f in flows]
    for event in events:
        insist(type(event) is dict,'Corporate event')
        if event.get('schema')=='INTEGER_SPLIT_EVENT_V1':
            fields(event,'schema event_id session security_id new_shares old_shares','Split')
            for key in ('new_shares','old_shares'): insist(type(event[key]) is int and 0<event[key]<=10**12,'Split ratio')
            insist(event['new_shares']!=event['old_shares'],'Nontrivial split')
        else:
            fields(event,'schema event_id session security_id kind','Unsupported event')
            insist(event['schema']=='UNSUPPORTED_CORPORATE_EVENT_V1','Event schema'); name(event['kind']); gaps.append('UNSUPPORTED_CORPORATE_EVENT')
        name(event['event_id']); name(event['security_id']); insist(event['session']==frame['session'],'Event session'); event_ids.append(event['event_id'])
    insist(len(event_ids)==len(set(event_ids)) and not set(event_ids).intersection(prior['applied_event_ids']),'Duplicate event ID')
    insist(len(event_ids)+len(prior['applied_event_ids'])<=4096,'Event cumulative bound')
    if not pending: insist(len(prior['applied_action_ids'])<4096,'Action cumulative bound')
    inherited=sorted(set(prior['blockers']+prior['eligibility_blockers']+context['eligibility_blockers']))
    input_hash=fingerprint(dict(scenario_content_sha256=fingerprint(scenario),previous_state_sha256=prior['content_sha256'],frame=frame,explicit_action=action))
    base=dict(schema=TARGET_SCHEMA,previous_state_sha256=prior['content_sha256'],input_sha256=input_hash,authority=dict(FLAGS),readiness='SOURCE_BLOCKED',eligibility_blockers=inherited)
    def stop(status,extra):
        return seal(dict(base,status=status,consumed_event_ids=[],consumed_action_ids=[],phase_observations=[],action_disposition=status,risk_observations={},valuation_row=None,next_state=None,blockers=sorted(set(inherited+extra)),numeric_status='BLOCKED'))
    if gaps: return stop('BLOCKED_INPUT',gaps)
    adjusted=dict(old); stale=False
    for event in events:
        sid=event['security_id']; quantity=Fraction(adjusted.get(sid,0)*event['new_shares'],event['old_shares'])
        if quantity.denominator!=1: return stop('BLOCKED_INPUT',['UNSUPPORTED_FRACTIONAL_SPLIT_ENTITLEMENT'])
        insist(quantity<=10**12,'Actual split quantity bound')
        if sid in adjusted: adjusted[sid]=quantity.numerator
        stale=stale or sid in buys or old.get(sid,0)>0
    if pending: return stop('PENDING_ACTION_POLICY',[action['reason']])
    op,cl=prices['open_prices_usd'],prices['close_prices_usd']; cash=amount(prior['cash_usd'])
    start=cash+sum((q*op[s] for s,q in adjusted.items()),Fraction()); injection=sum((amount(f['amount_usd']) for f in flows),Fraction()); funded=start+injection
    insist(start>0 and funded>0,'Zero equity boundary')
    gross=fee=Fraction()
    if stale:
        disposition='REJECTED_STALE_CORPORATE_ACTION'; projected_risk=dict(status='NOT_EVALUATED_STALE_ACTION',all_passed=None,checks={},metrics={})
    else:
        proposed={s:adjusted.get(s,0)+buys.get(s,0) for s in sorted(universe)}
        insist(all(q<=10**12 for q in proposed.values()),'Proposed quantity bound')
        gross=sum((q*op[s] for s,q in buys.items()),Fraction()); fee=gross/1000
        projected_risk=observe_risk(proposed,op,identity); issuers=[identity[s]['issuer_id'] for s,q in proposed.items() if q>0]
        if action['status']=='EXPLICIT_NO_TRADE': disposition='EXPLICIT_NO_TRADE'
        elif cash+injection-gross-fee<100: disposition='REJECTED_CASH_BUFFER'
        elif len(issuers)!=len(set(issuers)): disposition='REJECTED_DUPLICATE_ISSUER'
        elif projected_risk['all_passed'] is not True: disposition='REJECTED_ORIGINAL_RISK'
        else: disposition='ACCEPTED_EXPLICIT_BUY'
    executed=buys if disposition=='ACCEPTED_EXPLICIT_BUY' else {}
    if not executed: gross=fee=Fraction()
    ending={s:adjusted.get(s,0)+executed.get(s,0) for s in sorted(universe)}; remaining=cash+injection-gross-fee
    closing=remaining+sum((q*cl[s] for s,q in ending.items()),Fraction()); after=remaining+sum((q*op[s] for s,q in ending.items()),Fraction())
    insist(after==funded-fee and closing>0,'Conservation')
    overnight=start/amount(prior['close_equity_usd']); intraday=closing/funded; factor=overnight*intraday
    prior_twr=Fraction(int(prior['cumulative_twr']['numerator']),int(prior['cumulative_twr']['denominator'])); cumulative=(1+prior_twr)*factor-1
    state=make_state(scenario,index,ending,remaining,closing,cumulative,prior['applied_event_ids']+event_ids,prior['applied_action_ids']+[action['action_id']],prior['content_sha256'],input_hash,inherited)
    row=dict(previous_close_equity_usd=prior['close_equity_usd'],pre_flow_open_equity_usd=decimal_text(start),cash_injection_usd=decimal_text(injection),post_flow_pre_fee_open_equity_usd=decimal_text(funded),post_trade_open_equity_usd=decimal_text(after),close_equity_usd=decimal_text(closing),gross_buy_usd=decimal_text(gross),fees_usd=decimal_text(fee),cash_after_usd=decimal_text(remaining),holdings_before_events=old,holdings_after_events=adjusted,buy_shares=executed,holdings_after=ending,overnight_return=rational(overnight-1),after_flow_return=rational(intraday-1),session_twr=rational(factor-1),cumulative_twr=rational(cumulative))
    return seal(dict(base,status='COMPLETED_RESEARCH_TRANSITION',consumed_event_ids=sorted(event_ids),consumed_action_ids=[action['action_id']],phase_observations=['VALIDATED','CORPORATE_EVENTS','OPEN_MARK','CASHFLOW','ACTION_DISPOSITION','CLOSE_MARK'],action_disposition=disposition,risk_observations=dict(prospective_open=projected_risk,actual_close=observe_risk(ending,cl,identity),risk_math_reference=dict(RISK_REFERENCE)),valuation_row=row,next_state=state,blockers=inherited,numeric_status='COMPUTED'))


def window_views(scenario,transitions,coordinates,mapping):
    fields(mapping,'schema book_lineage_id scenario_content_sha256 calendar terminal_boundary','Mapping')
    insist(mapping['schema']=='ROLLING_BOOK_WINDOW_VIEW_MAPPING_V1','Mapping schema')
    dates=[row['session'] for row in scenario['calendar']]
    equal(mapping['calendar'],dates,'Mapping supplied scenario calendar'); equal(mapping['book_lineage_id'],scenario['book_lineage_id'],'Mapping book'); equal(mapping['scenario_content_sha256'],fingerprint(scenario),'Mapping scenario')
    terminal=mapping['terminal_boundary']
    if terminal is not None:
        fields(terminal,'kind ordinal','Terminal'); insist(terminal['kind']=='AFTER_LAST_SAVED_MARK' and type(terminal['ordinal']) is int and terminal['ordinal']==len(dates),'Terminal ordinal')
    insist(type(coordinates) is list and len(coordinates)==13,'All thirteen coordinates')
    successful={t['next_state']['sequence']:t for t in transitions if t['next_state'] is not None}
    rows=[]; seen=set()
    for coordinate in coordinates:
        fields(coordinate,'window_id fit_end evaluation_start evaluation_end_inclusive','Window'); name(coordinate['window_id'])
        insist(coordinate['window_id'] not in seen,'Unique window'); seen.add(coordinate['window_id'])
        for key in ('fit_end','evaluation_start','evaluation_end_inclusive'): session(coordinate[key])
        insist(coordinate['fit_end']<coordinate['evaluation_start']<=coordinate['evaluation_end_inclusive'],'Window causality')
        errors=[]; start=stop=None
        if coordinate['evaluation_start'] not in dates or coordinate['evaluation_end_inclusive'] not in dates: errors.append('MISSING_ENDPOINT')
        else:
            start=dates.index(coordinate['evaluation_start']); stop=dates.index(coordinate['evaluation_end_inclusive'])+1
            if start==0: errors.append('MISSING_PREVIOUS_CLOSE_ANCHOR')
            if stop==len(dates) and terminal is None: errors.append('BLOCKED_ENDPOINT')
            if any(i not in successful for i in range(start,stop)): errors.append('MISSING_WINDOW_FRAME')
        if errors:
            rows.append(dict(window_preserved=deepcopy(coordinate),status='BLOCKED_WINDOW_VIEW',blockers=errors,view_twr=None,frame_references=[])); continue
        product=Fraction(1); links=[]
        for i in range(start,stop):
            result=successful[i]; value=result['valuation_row']['session_twr']; product*=1+Fraction(int(value['numerator']),int(value['denominator'])); rational(product)
            links.append(dict(sequence=i,session=dates[i],previous_state_sha256=result['previous_state_sha256'],state_sha256=result['next_state']['content_sha256']))
        rows.append(dict(window_preserved=deepcopy(coordinate),status='COMPUTED_RESEARCH_VIEW',start_index=start,stop_index=stop,anchor_close_session=dates[start-1],anchor_state_sha256=successful[start]['previous_state_sha256'],view_twr=rational(product-1),frame_references=links,blockers=[]))
    return seal(dict(schema='ROLLING_BOOK_WINDOW_VIEWS_V1',window_count=13,rows=rows,book_execution_performed=False,authority=dict(FLAGS)))


def inspect_saved_book(*,scenario,initial_state,initial_marks,initial_source_context,frames,explicit_actions,saved_bootstrap,saved_transitions,window_coordinates,mapping_contract,saved_views):
    """Inspect an entire explicit path, ending at its first noncommitted frame.

    Saved transitions are compared recursively against independent arithmetic,
    not used as subsequent state inputs. Full thirteen views are reconstructed
    from the successful prefix; a missing endpoint remains explicitly blocked.
    """
    insist(type(frames) is list and type(explicit_actions) is list and type(saved_transitions) is list and len(frames)==len(explicit_actions)==len(saved_transitions)<=512,'Complete parallel path bounds')
    # The frozen resource ceiling applies to each original document, not the
    # aggregate history: 512 individually valid frames must not acquire a new
    # combined 200k-node ceiling merely because inspection accepts a full path.
    for value in (scenario,initial_state,initial_marks,initial_source_context,saved_bootstrap,window_coordinates,mapping_contract,saved_views): serialize(value)
    for documents in (frames,explicit_actions,saved_transitions):
        for value in documents: serialize(value)
    read_scenario(scenario)
    boot=genesis(scenario,initial_state,initial_marks,initial_source_context); equal(saved_bootstrap,boot,'Complete bootstrap mismatch')
    previous=boot['next_state']; expected=[]
    for index,(frame,action,saved) in enumerate(zip(frames,explicit_actions,saved_transitions)):
        insist(previous is not None,'Uncommitted path cannot advance')
        result=transition(scenario,previous,frame,action); equal(saved,result,'Complete transition mismatch at '+str(index+1))
        expected.append(result); previous=result['next_state']
    views=window_views(scenario,expected,window_coordinates,mapping_contract); equal(saved_views,views,'Complete thirteen-view mismatch')
    return deepcopy(dict(schema='CAUSAL_WHOLE_BOOK_INDEPENDENT_READBACK_V1',status='PASS_SAVED_WHOLE_V2_PATH',target_schema=TARGET_SCHEMA,target_source_sha256=TARGET_SOURCE_SHA256,contract_sha256=CONTRACT_SHA256,transition_count=len(expected),committed_transition_count=sum(t['next_state'] is not None for t in expected),window_count=13,bootstrap=boot,transitions=expected,views=views,numeric_status='COMPUTED' if previous is not None else 'BLOCKED',readiness='SOURCE_BLOCKED',producer_called=False,source_io_performed=False,authority=dict(FLAGS)))

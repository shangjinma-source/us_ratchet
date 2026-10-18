"""Pure whole-share explicit-action research books. No IO, clock, fit or selection.

Source coverage and synthetic timestamps are declarations, never authentication.
Original risk arithmetic is independently transcribed, including float/tau 1e-9;
all money and return arithmetic is exact. This is not an independent readback.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import math
import re

SCHEMA = 'CAUSAL_RESEARCH_BOOK_MECHANICS_V1'
STATE_SCHEMA = 'CAUSAL_RESEARCH_BOOK_STATE_V1'
CONTRACT_SHA = '1b5aa8e2d48dc33adf089dc3f291c5c09cd7b01cf3ac45710e60c8ca6d6a6ee1'
RISK_REFERENCE = {'path': 'backtest/ndx_dynamic_whole_lot_repair_path.py', 'sha256': 'e614be1a2fe461e483e17413af03153f9a2fe99c31e0412b5daa8954c53d3f34', 'json_pointer': '/_risk_snapshot'}
MAX_FRAMES, MAX_SIDS, MAX_SHARES, MAX_IDS, MAX_RATIO_BITS = 512, 256, 10**12, 4096, 12000
FLAGS = dict.fromkeys(('source_authenticity_verified','point_in_time_verified','current_account_verified','objective_registered','action_policy_registered','fit_called','solver_called','execution_authorized','promotion_allowed','future_oos'), False)
COVERAGE = ('prices','identity_risk','corporate_events','calendar','cashflow')
SOURCE_ROLES = ('open_prices','close_prices','decision_prices','identity_risk','corporate_events','calendar')
STATE_KEYS = ('schema','scenario_content_sha256','book_lineage_id','sequence','session','phase','holdings_by_sid','cash_usd','close_equity_usd','cumulative_twr','applied_event_ids','applied_action_ids','previous_state_sha256','transition_input_sha256','blockers','authority','content_sha256','numeric_status','readiness','eligibility_blockers','close_at_utc')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def keys(value, expected, label):
    require(type(value) is dict and set(value) == set(expected), label + ' exact fields')


def identifier(value):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,128}', value) is not None, 'ASCII identifier 1..128')
    return value


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def encoded(value):
    # Bounded JSON domain: reject custom objects, floats, non-string keys and deep trees.
    count = [0]
    def visit(item, depth):
        count[0] += 1
        require(depth <= 64 and count[0] <= 200000, 'JSON engineering bound')
        require(type(item) in (dict,list,str,int,bool,type(None)), 'Exact JSON types, no float')
        if type(item) is dict:
            require(all(type(k) is str for k in item), 'JSON string keys')
            for val in item.values(): visit(val, depth + 1)
        elif type(item) is list:
            for val in item: visit(val, depth + 1)
    visit(value, 0)
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def same(a, b, label):
    require(encoded(a) == encoded(b), label)


def sha(value):
    require(type(value) is str and re.fullmatch('[a-f0-9]{64}',value) is not None, 'SHA256')
    return value


def reference(value):
    keys(value, ('path','sha256','json_pointer'), 'Reference')
    require(type(value['path']) is str and 0 < len(value['path']) <= 4096 and value['path'].strip() == value['path'], 'Reference path syntax only')
    sha(value['sha256'])
    require(type(value['json_pointer']) is str and len(value['json_pointer']) <= 4096 and (value['json_pointer'] == '' or value['json_pointer'].startswith('/')), 'JSON pointer syntax')


def day(value):
    require(type(value) is str and date.fromisoformat(value).isoformat() == value, 'Canonical session')
    return value


def utc(value):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?Z',value) is not None, 'Canonical UTC Z')
    require('.000000Z' not in value, 'Zero micros omitted')
    return datetime.fromisoformat(value.replace('Z','+00:00'))


def number(value):
    require(type(value) is str and 0 < len(value) <= 82 and re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?',value) is not None, 'Canonical nonnegative plain decimal string')
    parsed = Decimal(value)
    require(parsed.is_finite() and len(parsed.as_tuple().digits) <= 40 and abs(parsed.as_tuple().exponent) <= 40, 'Decimal engineering bound')
    return Fraction(parsed)


def money(value):
    require(value >= 0, 'Nonnegative monetary state')
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0: denominator //= 2; twos += 1
    while denominator % 5 == 0: denominator //= 5; fives += 1
    require(denominator == 1, 'Terminating decimal money')
    places = max(twos,fives)
    integer = value.numerator * 2**(places-twos) * 5**(places-fives)
    text = str(integer).zfill(places+1)
    return text if not places else (text[:-places]+'.'+text[-places:]).rstrip('0').rstrip('.')


def ratio(value):
    require(max(abs(value.numerator).bit_length(),value.denominator.bit_length()) <= MAX_RATIO_BITS, 'Ratio engineering bound')
    return dict(numerator=str(value.numerator),denominator=str(value.denominator))


def parse_ratio(value):
    keys(value,('numerator','denominator'),'Ratio')
    require(type(value['numerator']) is str and re.fullmatch(r'-?(?:0|[1-9][0-9]*)',value['numerator']) is not None and value['numerator'] != '-0', 'Ratio numerator')
    require(type(value['denominator']) is str and re.fullmatch('[1-9][0-9]*',value['denominator']) is not None, 'Ratio denominator')
    require(max(len(value['numerator']),len(value['denominator'])) <= 3615, 'Ratio input bound')
    result=Fraction(int(value['numerator']),int(value['denominator']))
    same(ratio(result),value,'Reduced canonical ratio')
    return result


def holdings(value):
    require(type(value) is dict and len(value) <= MAX_SIDS, 'Holdings engineering bound')
    for sid,q in value.items():
        identifier(sid)
        require(type(q) is int and 0 <= q <= MAX_SHARES, 'Nonnegative whole shares, no bool')
    return dict(sorted(value.items()))


def ids(value):
    require(type(value) is list and len(value) <= MAX_IDS, 'Cumulative ID engineering bound')
    for val in value: identifier(val)
    require(value == sorted(set(value)), 'Sorted unique IDs')


def blockers(value):
    require(type(value) is list and len(value) <= 256, 'Blocker list')
    for val in value: identifier(val)
    require(value == sorted(set(value)), 'Canonical blocker set')


def stamp(value):
    value['content_sha256']=digest(value)
    return value


def check_state(state, scenario):
    keys(state,STATE_KEYS,'State')
    require(state['schema']==STATE_SCHEMA and state['phase']=='CLOSE' and state['numeric_status']=='COMPUTED' and state['readiness']=='SOURCE_BLOCKED','Research computed state')
    same(state['authority'],FLAGS,'No state authority')
    require(state['scenario_content_sha256']==digest(scenario) and state['book_lineage_id']==scenario['book_lineage_id'],'Same scenario/book')
    require(type(state['sequence']) is int and 0 <= state['sequence'] <= MAX_FRAMES,'State sequence')
    day(state['session']);utc(state['close_at_utc']);holdings(state['holdings_by_sid']);number(state['cash_usd']);require(number(state['close_equity_usd'])>0,'Positive state equity');require(parse_ratio(state['cumulative_twr'])>-1,'Positive cumulative factor')
    ids(state['applied_event_ids']);ids(state['applied_action_ids']);blockers(state['blockers']);blockers(state['eligibility_blockers'])
    if state['sequence']==0:
        require(state['previous_state_sha256'] is None,'Genesis prior null')
    else: sha(state['previous_state_sha256'])
    sha(state['transition_input_sha256']);sha(state['content_sha256'])
    same(state['content_sha256'],digest({k:v for k,v in state.items() if k!='content_sha256'}),'Exact state hash')


def validate_scenario(value):
    keys(value,('schema','scenario_id','currency','quantity_domain','book_lineage_id','bootstrap_policy','cashflow_schedule','calendar','lane_coordinate','risk_policy_reference','action_policy_reference','source_requirements'),'Scenario')
    require(value['schema']=='CAUSAL_RESEARCH_SCENARIO_V1' and value['currency']=='USD','Research USD scenario')
    require(value['quantity_domain']=='WHOLE_SHARES','UNSUPPORTED_QUANTITY_DOMAIN')
    identifier(value['scenario_id']);identifier(value['book_lineage_id'])
    require(value['bootstrap_policy']=='EXPLICIT_POSITIVE_PRIOR_CLOSE_RESEARCH','Explicit positive bootstrap')
    keys(value['lane_coordinate'],('lane','fx_mode','lineage_kind'),'Lane coordinate')
    for x in value['lane_coordinate'].values():identifier(x)
    reference(value['risk_policy_reference']);reference(value['action_policy_reference'])
    require(value['source_requirements']==list(COVERAGE),'Exact declared source obligations')
    cal=value['calendar'];require(type(cal) is list and 2 <= len(cal) <= MAX_FRAMES+1,'513 mark bound')
    prev=None
    for row in cal:
        keys(row,('session','open_at_utc','close_at_utc'),'Calendar mark')
        day(row['session']);op,cl=utc(row['open_at_utc']),utc(row['close_at_utc'])
        require(op<cl and op.date().isoformat()==row['session'] and cl.date().isoformat()==row['session'],'Supplied UTC session association')
        require(prev is None or (row['session']>prev['session'] and utc(prev['close_at_utc'])<op),'Strict supplied calendar')
        prev=row
    flows=value['cashflow_schedule'];require(type(flows) is list and len(flows)<=MAX_IDS,'Cashflow bound')
    seen=set()
    for flow in flows:
        keys(flow,('event_id','session','amount_usd','available_at_utc'),'Flow')
        identifier(flow['event_id']);day(flow['session']);number(flow['amount_usd']);utc(flow['available_at_utc'])
        require(flow['event_id'] not in seen and flow['session'] in [r['session'] for r in cal[1:]],'Unique scheduled flow/session')
        seen.add(flow['event_id'])
    require(flows==sorted(flows,key=lambda f:(f['session'],f['event_id'])),'Ordered fixed flow schedule')
    encoded(value)


def source_context(value):
    keys(value,('input_scope','numeric_coverage','source_references_by_role','full_inventory_reference','eligibility_blockers','authority'),'Source context')
    require(value['input_scope'] in ('SYNTHETIC_EXPLICIT','CONDITIONAL_SOURCE_BOUND'),'Source scope')
    keys(value['numeric_coverage'],COVERAGE,'Numeric coverage')
    for status in value['numeric_coverage'].values():require(status in ('DECLARED_COMPLETE','MISSING'),'Coverage declaration')
    keys(value['source_references_by_role'],SOURCE_ROLES,'Closed source roles')
    for ref in value['source_references_by_role'].values():
        if ref is not None:reference(ref)
    reference(value['full_inventory_reference']);blockers(value['eligibility_blockers']);same(value['authority'],FLAGS,'No source authority')
    return ['MISSING_'+k.upper() for k,v in value['numeric_coverage'].items() if v=='MISSING']+[ 'MISSING_REFERENCE_'+k.upper() for k,v in value['source_references_by_role'].items() if v is None]


def risk_snapshot(positions, marks, identity):
    positive={k:q for k,q in positions.items() if q>0}
    if not positive:return {'status':'NO_POSITIVE_STOCK_EXPOSURE_NOT_EVALUATED','all_passed':None,'checks':{},'metrics':{}}
    # Same original arithmetic order and tolerance; no caller risk boolean.
    notionals={k:int(q)*float(marks[k]) for k,q in positive.items()};invested=sum(notionals.values())
    require(math.isfinite(invested) and invested>0,'Finite original float risk domain')
    weights={k:v/invested for k,v in notionals.items()};ordered=sorted(weights.values(),reverse=True)
    effective=1.0/sum(w*w for w in ordered);chains={}
    for sid,w in weights.items():chains[identity[sid]['risk_chain']]=chains.get(identity[sid]['risk_chain'],0.0)+w
    checks={'MAX_SINGLE_WEIGHT':ordered[0]<=.45+1e-9,'MIN_SINGLE_WEIGHT':ordered[-1]>=.05-1e-9,'SECURITY_TOP3_WEIGHT':sum(ordered[:3])<=.8+1e-9,'MINIMUM_EFFECTIVE_N':effective>=.7*len(ordered)-1e-9,'RISK_CHAIN_TOP1_WEIGHT':max(chains.values())<=.55+1e-9}
    # Risk floats are represented as repr strings so state JSON never accepts floats.
    return dict(status='ORIGINAL_FLOAT_TAU_1E_MINUS9_OBSERVATION',all_passed=all(checks.values()),checks=checks,metrics={'actual_weights':{k:repr(v) for k,v in sorted(weights.items())},'top1_weight':repr(ordered[0]),'minimum_single_weight':repr(ordered[-1]),'top3_weight':repr(sum(ordered[:3])),'effective_n':repr(effective),'risk_chain_top1_weight':repr(max(chains.values()))})


def bootstrap_research_book(*, scenario, initial_state, initial_marks, source_context):
    validate_scenario(scenario)
    context=source_context
    gaps=globals()['source_context'](context)
    keys(initial_state,('session','close_at_utc','holdings_by_sid','cash_usd'),'Initial state')
    require(initial_state['session']==scenario['calendar'][0]['session'] and initial_state['close_at_utc']==scenario['calendar'][0]['close_at_utc'],'Initial calendar close')
    positions=holdings(initial_state['holdings_by_sid']);cash=number(initial_state['cash_usd'])
    require(type(initial_marks) is dict,'Initial mark object')
    for val in initial_marks.values():require(number(val)>0,'Positive mark')
    if set(initial_marks)!=set(positions):gaps.append('MISSING_INITIAL_PRICE_COVERAGE')
    if gaps:return deepcopy(dict(schema=SCHEMA,status='BLOCKED_INPUT',numeric_status='BLOCKED',readiness='SOURCE_BLOCKED',next_state=None,blockers=sorted(set(gaps)),authority=FLAGS))
    equity=cash+sum((q*number(initial_marks[s]) for s,q in positions.items()),Fraction())
    require(equity>0,'UNSUPPORTED_ZERO_CAPITAL_INCEPTION')
    inherited=context['eligibility_blockers']
    state=dict(schema=STATE_SCHEMA,scenario_content_sha256=digest(scenario),book_lineage_id=scenario['book_lineage_id'],sequence=0,session=initial_state['session'],phase='CLOSE',holdings_by_sid=positions,cash_usd=money(cash),close_equity_usd=money(equity),cumulative_twr=ratio(Fraction()),applied_event_ids=[],applied_action_ids=[],previous_state_sha256=None,transition_input_sha256=digest(dict(initial_state=initial_state,initial_marks=initial_marks,source_context=context)),blockers=list(inherited),authority=dict(FLAGS),numeric_status='COMPUTED',readiness='SOURCE_BLOCKED',eligibility_blockers=list(inherited),close_at_utc=initial_state['close_at_utc'])
    stamp(state);check_state(state,scenario)
    return deepcopy(dict(schema=SCHEMA,status='BOOTSTRAPPED_RESEARCH_ONLY',numeric_status='COMPUTED',readiness='SOURCE_BLOCKED',next_state=state,blockers=list(inherited),authority=dict(FLAGS)))


def advance_research_book(*, scenario, previous_state, frame, explicit_action):
    validate_scenario(scenario);check_state(previous_state,scenario)
    keys(frame,('schema','session','previous_state_sha256','identity_risk_by_sid','open_prices_usd','close_prices_usd','cashflow_events','corporate_events','source_context','session_open_at_utc','session_close_at_utc'),'Frame')
    require(frame['schema']=='CAUSAL_RESEARCH_FRAME_V1' and frame['previous_state_sha256']==previous_state['content_sha256'],'Frame prior/schema')
    index=previous_state['sequence']+1;require(index<len(scenario['calendar']),'Calendar exhausted')
    cal=scenario['calendar'][index];require(frame['session']==cal['session'] and frame['session_open_at_utc']==cal['open_at_utc'] and frame['session_close_at_utc']==cal['close_at_utc'],'Exact next supplied frame')
    require(previous_state['session']==scenario['calendar'][index-1]['session'] and previous_state['close_at_utc']==scenario['calendar'][index-1]['close_at_utc'],'Prior calendar coordinate')
    gaps=source_context(frame['source_context']);context=frame['source_context']
    action=explicit_action;require(type(action) is dict and type(action.get('status')) is str,'Explicit action union')
    pending=action['status']=='PENDING_ACTION_POLICY';buys={}
    common=('schema','status','action_id','decision_session','decision_at_utc','execution_session','information_cutoff_utc','decision_state_sha256','fill_baseline_sha256','frozen_baseline','policy_reference','source_references')
    if pending:
        keys(action,('schema','status','reason','decision_session','execution_session'),'Pending action')
        identifier(action['reason']);require(action['schema']=='EXPLICIT_RESEARCH_ACTION_V1' and action['decision_session']==previous_state['session'] and action['execution_session']==frame['session'],'Pending coordinate')
    else:
        require(action['status'] in ('EXPLICIT_BUY','EXPLICIT_NO_TRADE'),'Known action status')
        keys(action,common+(('buy_shares',) if action['status']=='EXPLICIT_BUY' else ('reason',)),'Frozen action')
        require(action['schema']=='EXPLICIT_RESEARCH_ACTION_V1','Action schema');identifier(action['action_id']);require(action['action_id'] not in previous_state['applied_action_ids'],'Duplicate action ID')
        require(action['decision_session']==previous_state['session'] and action['execution_session']==frame['session'] and action['decision_state_sha256']==previous_state['content_sha256'],'Decision prior/next execution')
        require(utc(action['information_cutoff_utc'])<=utc(action['decision_at_utc']) and utc(previous_state['close_at_utc'])<=utc(action['decision_at_utc'])<utc(frame['session_open_at_utc']),'Action causal clock')
        reference(action['policy_reference']);same(action['policy_reference'],scenario['action_policy_reference'],'Scenario action policy declaration')
        baseline=action['frozen_baseline'];keys(baseline,('schema','phase','previous_state_sha256','holdings_by_sid','cash_usd','planned_cashflow_event_ids'),'Frozen baseline')
        require(baseline['schema']=='FROZEN_PRE_EVENT_ACTION_BASELINE_V1' and baseline['phase']=='PRIOR_CLOSE_BEFORE_FRAME_EVENTS_AND_FLOW','Frozen phase')
        same(baseline['previous_state_sha256'],previous_state['content_sha256'],'Baseline prior');same(baseline['holdings_by_sid'],previous_state['holdings_by_sid'],'Baseline shares');same(baseline['cash_usd'],previous_state['cash_usd'],'Baseline cash');sha(action['fill_baseline_sha256']);require(digest(baseline)==action['fill_baseline_sha256'],'Exact frozen baseline hash')
        keys(action['source_references'],('decision_prices','identity_risk','policy'),'Action evidence roles')
        for role,evidence in action['source_references'].items():
            keys(evidence,('reference','available_at_utc','stage'),'Decision observation');reference(evidence['reference']);require(evidence['stage']=='DECISION_KNOWN_ONLY' and utc(evidence['available_at_utc'])<=utc(action['information_cutoff_utc']),'No future decision evidence')
            expected=scenario['action_policy_reference'] if role=='policy' else context['source_references_by_role'][role]
            if expected is not None:same(evidence['reference'],expected,'Exact action/source role')
        decisionref=action['source_references']['decision_prices']['reference']
        require(all(decisionref!=context['source_references_by_role'][r] for r in ('open_prices','close_prices')),'No realized Open/Close evidence in decision role')
        if action['status']=='EXPLICIT_BUY':buys=holdings(action['buy_shares'])
        else:identifier(action['reason'])
    positions=holdings(previous_state['holdings_by_sid']);union=set(positions)|set(buys);require(len(union)<=MAX_SIDS,'SID bound')
    for name in ('open_prices_usd','close_prices_usd'):
        require(type(frame[name]) is dict,'Price map')
        for v in frame[name].values():require(number(v)>0,'Positive numeric mark')
        if set(frame[name])!=union:gaps.append('MISSING_EXACT_'+name.upper())
    identity=frame['identity_risk_by_sid'];require(type(identity) is dict,'Identity map')
    for sid,row in identity.items():
        identifier(sid);keys(row,('issuer_id','risk_chain'),'Identity/risk');identifier(row['issuer_id']);identifier(row['risk_chain'])
    if set(identity)!=union:gaps.append('MISSING_EXACT_IDENTITY_RISK')
    scheduled=[f for f in scenario['cashflow_schedule'] if f['session']==frame['session']]
    same(frame['cashflow_events'],scheduled,'No invented/dropped flow events')
    if not pending:same(action['frozen_baseline']['planned_cashflow_event_ids'],sorted(f['event_id'] for f in scheduled),'Frozen cashflow IDs')
    for f in scheduled:require(utc(f['available_at_utc'])<=utc(frame['session_open_at_utc']),'Scenario flow declared available before use')
    events=frame['corporate_events'];require(type(events) is list and len(events)<=MAX_IDS,'Event bound')
    currentids=[f['event_id'] for f in scheduled];unsupported=False;affected=set()
    for event in events:
        require(type(event) is dict and event.get('schema') in ('INTEGER_SPLIT_EVENT_V1','UNSUPPORTED_CORPORATE_EVENT_V1'),'Typed corporate event')
        if event['schema']=='INTEGER_SPLIT_EVENT_V1':
            keys(event,('schema','event_id','session','security_id','new_shares','old_shares'),'Split event')
            require(type(event['new_shares']) is int and type(event['old_shares']) is int and 0<event['new_shares']<=MAX_SHARES and 0<event['old_shares']<=MAX_SHARES and event['new_shares']!=event['old_shares'],'Exact nontrivial split ratio')
        else:
            keys(event,('schema','event_id','session','security_id','kind'),'Unsupported event');identifier(event['kind']);unsupported=True
        identifier(event['event_id']);identifier(event['security_id']);require(event['session']==frame['session'],'Event session');currentids.append(event['event_id'])
    require(len(currentids)==len(set(currentids)) and not(set(currentids)&set(previous_state['applied_event_ids'])),'Duplicate event ID across kinds or sessions')
    require(len(currentids)+len(previous_state['applied_event_ids'])<=MAX_IDS,'Cumulative event bound')
    if not pending:require(len(previous_state['applied_action_ids'])<MAX_IDS,'Cumulative action bound')
    if unsupported:gaps.append('UNSUPPORTED_CORPORATE_EVENT')
    inherited=sorted(set(previous_state['eligibility_blockers']+previous_state['blockers']+context['eligibility_blockers']))
    inputsha=digest(dict(scenario_content_sha256=digest(scenario),previous_state_sha256=previous_state['content_sha256'],frame=frame,explicit_action=action))
    def blocked(status,reasons):
        return deepcopy(dict(schema=SCHEMA,status=status,previous_state_sha256=previous_state['content_sha256'],input_sha256=inputsha,consumed_event_ids=[],consumed_action_ids=[],phase_observations=[],action_disposition=status,risk_observations={},valuation_row=None,next_state=None,blockers=sorted(set(inherited+reasons)),authority=dict(FLAGS),numeric_status='BLOCKED',readiness='SOURCE_BLOCKED',eligibility_blockers=inherited))
    if gaps:return stamp(blocked('BLOCKED_INPUT',gaps))
    # Only integral splits supported. Explicit coverage declaration is not proof of absence.
    for event in events:
        sid=event['security_id'];quantity=Fraction(positions.get(sid,0)*event['new_shares'],event['old_shares'])
        if quantity.denominator!=1:return stamp(blocked('BLOCKED_INPUT',['UNSUPPORTED_FRACTIONAL_SPLIT_ENTITLEMENT']))
        require(quantity<=MAX_SHARES,'Postsplit share bound')
        if sid in positions:positions[sid]=quantity.numerator
        if sid in buys or previous_state['holdings_by_sid'].get(sid,0)>0:affected.add(sid)
    if pending:return stamp(blocked('PENDING_ACTION_POLICY',[action['reason']]))
    cash=number(previous_state['cash_usd']);opens={k:number(v) for k,v in frame['open_prices_usd'].items()};closes={k:number(v) for k,v in frame['close_prices_usd'].items()}
    before=cash+sum((q*opens[s] for s,q in positions.items()),Fraction());flow=sum((number(f['amount_usd']) for f in scheduled),Fraction());post=before+flow
    require(before>0 and post>0,'Undefined zero-equity boundary')
    prospective={s:positions.get(s,0)+buys.get(s,0) for s in sorted(union)};require(all(q<=MAX_SHARES for q in prospective.values()),'Postbuy share bound')
    gross=sum((q*opens[s] for s,q in buys.items()),Fraction());fee=gross/Fraction(1000);aftercash=cash+flow-gross-fee
    prospective_risk=risk_snapshot(prospective,opens,identity)
    issuers=[identity[s]['issuer_id'] for s,q in prospective.items() if q>0]
    if affected:disposition='REJECTED_STALE_CORPORATE_ACTION'
    elif action['status']=='EXPLICIT_NO_TRADE':disposition='EXPLICIT_NO_TRADE'
    elif aftercash<Fraction(100):disposition='REJECTED_CASH_BUFFER'
    elif len(issuers)!=len(set(issuers)):disposition='REJECTED_DUPLICATE_ISSUER'
    elif prospective_risk['all_passed'] is not True:disposition='REJECTED_ORIGINAL_RISK'
    else:disposition='ACCEPTED_EXPLICIT_BUY'
    accepted=disposition=='ACCEPTED_EXPLICIT_BUY'
    actualbuys=buys if accepted else {};actualgross=gross if accepted else Fraction();actualfee=fee if accepted else Fraction()
    finalcash=cash+flow-actualgross-actualfee;finalshares={s:positions.get(s,0)+actualbuys.get(s,0) for s in sorted(union)}
    closevalue=finalcash+sum((q*closes[s] for s,q in finalshares.items()),Fraction());aftertrade=finalcash+sum((q*opens[s] for s,q in finalshares.items()),Fraction())
    require(aftertrade==post-actualfee and closevalue>0,'Exact conservation/positive close')
    overnight=before/number(previous_state['close_equity_usd']);intraday=closevalue/post;factor=overnight*intraday
    cumulative=(1+parse_ratio(previous_state['cumulative_twr']))*factor-1
    state=dict(schema=STATE_SCHEMA,scenario_content_sha256=digest(scenario),book_lineage_id=scenario['book_lineage_id'],sequence=index,session=frame['session'],phase='CLOSE',holdings_by_sid=finalshares,cash_usd=money(finalcash),close_equity_usd=money(closevalue),cumulative_twr=ratio(cumulative),applied_event_ids=sorted(previous_state['applied_event_ids']+currentids),applied_action_ids=sorted(previous_state['applied_action_ids']+[action['action_id']]),previous_state_sha256=previous_state['content_sha256'],transition_input_sha256=inputsha,blockers=inherited,authority=dict(FLAGS),numeric_status='COMPUTED',readiness='SOURCE_BLOCKED',eligibility_blockers=inherited,close_at_utc=frame['session_close_at_utc'])
    row=dict(previous_close_equity_usd=previous_state['close_equity_usd'],pre_flow_open_equity_usd=money(before),cash_injection_usd=money(flow),post_flow_pre_fee_open_equity_usd=money(post),post_trade_open_equity_usd=money(aftertrade),close_equity_usd=money(closevalue),gross_buy_usd=money(actualgross),fees_usd=money(actualfee),cash_after_usd=money(finalcash),holdings_before_events=deepcopy(previous_state['holdings_by_sid']),holdings_after_events=positions,buy_shares=actualbuys,holdings_after=finalshares,overnight_return=ratio(overnight-1),after_flow_return=ratio(intraday-1),session_twr=ratio(factor-1),cumulative_twr=ratio(cumulative))
    stamp(state);check_state(state,scenario)
    result=dict(schema=SCHEMA,status='COMPLETED_RESEARCH_TRANSITION',previous_state_sha256=previous_state['content_sha256'],input_sha256=inputsha,consumed_event_ids=sorted(currentids),consumed_action_ids=[action['action_id']],phase_observations=['VALIDATED','CORPORATE_EVENTS','OPEN_MARK','CASHFLOW','ACTION_DISPOSITION','CLOSE_MARK'],action_disposition=disposition,risk_observations={'prospective_open':prospective_risk,'actual_close':risk_snapshot(finalshares,closes,identity),'risk_math_reference':deepcopy(RISK_REFERENCE)},valuation_row=row,next_state=state,blockers=inherited,authority=dict(FLAGS),numeric_status='COMPUTED',readiness='SOURCE_BLOCKED',eligibility_blockers=inherited)
    return deepcopy(stamp(result))


def map_rolling_windows_to_book_views(*, window_coordinates, book_timeline, mapping_contract):
    keys(mapping_contract,('schema','book_lineage_id','scenario_content_sha256','calendar','terminal_boundary'),'Window mapping')
    require(mapping_contract['schema']=='ROLLING_BOOK_WINDOW_VIEW_MAPPING_V1','Mapping schema')
    identifier(mapping_contract['book_lineage_id']);sha(mapping_contract['scenario_content_sha256'])
    calendar=mapping_contract['calendar'];require(type(calendar) is list and 2<=len(calendar)<=513,'Mapping calendar bound')
    for session in calendar:day(session)
    require(calendar==sorted(set(calendar)),'Unique calendar')
    terminal=mapping_contract['terminal_boundary']
    if terminal is not None:
        keys(terminal,('kind','ordinal'),'Terminal boundary');require(terminal['kind']=='AFTER_LAST_SAVED_MARK' and type(terminal['ordinal']) is int and terminal['ordinal']==len(calendar),'Exact terminal sentinel')
    require(type(window_coordinates) is list and len(window_coordinates)==13,'Full13 windows')
    require(type(book_timeline) is list and len(book_timeline)<=MAX_FRAMES,'Timeline bound')
    indexed={};previous=None
    for record in book_timeline:
        keys(record,('sequence','session','previous_close_session','previous_state_sha256','state_sha256','book_lineage_id','scenario_content_sha256','session_twr','status'),'Window frame record')
        require(type(record['sequence']) is int and 1<=record['sequence']<len(calendar),'Frame index')
        require(record['session']==calendar[record['sequence']] and record['previous_close_session']==calendar[record['sequence']-1],'Frame calendar mapping')
        require(record['book_lineage_id']==mapping_contract['book_lineage_id'] and record['scenario_content_sha256']==mapping_contract['scenario_content_sha256'],'No mixed vintage/book')
        sha(record['previous_state_sha256']);sha(record['state_sha256']);require(parse_ratio(record['session_twr'])>-1,'Positive frame return factor');require(record['status']=='COMPUTED','Computed frame only')
        require(record['sequence'] not in indexed and (previous is None or record['sequence']>previous['sequence']),'Ordered unique frame records')
        if previous is not None and record['sequence']==previous['sequence']+1:require(record['previous_state_sha256']==previous['state_sha256'],'Adjacent hash chain')
        indexed[record['sequence']]=record;previous=record
    rows=[];seen=set()
    for window in window_coordinates:
        keys(window,('window_id','fit_end','evaluation_start','evaluation_end_inclusive'),'Original window coordinate')
        identifier(window['window_id']);require(window['window_id'] not in seen,'Unique window ID');seen.add(window['window_id'])
        for key in ('fit_end','evaluation_start','evaluation_end_inclusive'):day(window[key])
        require(window['fit_end']<window['evaluation_start']<=window['evaluation_end_inclusive'],'Fit strictly before evaluation')
        reasons=[];a=b=None
        if window['evaluation_start'] not in calendar or window['evaluation_end_inclusive'] not in calendar:reasons.append('MISSING_ENDPOINT')
        else:
            a=calendar.index(window['evaluation_start']);b=calendar.index(window['evaluation_end_inclusive'])+1
            if a==0:reasons.append('MISSING_PREVIOUS_CLOSE_ANCHOR')
            if b==len(calendar) and terminal is None:reasons.append('BLOCKED_ENDPOINT')
            if any(i not in indexed for i in range(a,b)):reasons.append('MISSING_WINDOW_FRAME')
        if reasons:rows.append(dict(window_preserved=deepcopy(window),status='BLOCKED_WINDOW_VIEW',blockers=reasons,view_twr=None,frame_references=[]));continue
        factor=Fraction(1);links=[]
        for i in range(a,b):
            record=indexed[i];factor*=1+parse_ratio(record['session_twr']);ratio(factor)
            links.append(dict(sequence=i,session=record['session'],previous_state_sha256=record['previous_state_sha256'],state_sha256=record['state_sha256']))
        rows.append(dict(window_preserved=deepcopy(window),status='COMPUTED_RESEARCH_VIEW',start_index=a,stop_index=b,anchor_close_session=calendar[a-1],anchor_state_sha256=indexed[a]['previous_state_sha256'],view_twr=ratio(factor-1),frame_references=links,blockers=[]))
    return deepcopy(stamp(dict(schema='ROLLING_BOOK_WINDOW_VIEWS_V1',window_count=13,rows=rows,book_execution_performed=False,authority=dict(FLAGS))))

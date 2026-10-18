"""Saved causal liquidity slices; no IO, raw decode, selection or certification."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import math
import re
from decimal import Decimal

SOURCE_SHA='68595f10bde6d917682d8543ebd081462f0df90b0e330f606ca1ac9a2c596804'
CONTRACT=dict(schema='FROZEN_CONDITIONAL_LIQUIDITY_CONTRACT_V1',lookback_sessions=63,minimum_median_dollar_volume_usd=50000000,median_order_index=31,volume_policy='RAW_VOLUME_UNSCALED',event_gate='ALL_RETURNED_SPLITS_SESSION_GE_WINDOW_START_INCLUDING_AFTER_CUTOFF')
SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
FLAGS=dict.fromkeys(('source_bytes_authenticated','point_in_time_verified','historical_liquidity_qualified','volume_units_certified','complete_actions_verified','complete_ndx_universe_verified','historical_pool_eligibility_verified','selection_performed','fit_performed','execution_authorized','promotion_allowed','future_independent_oos','decision_contract_registered'),False)
def require(ok,message):
    if not ok:raise ValueError(message)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def exact(a,b,msg):require(digest(a)==digest(b),msg)
def ref(r):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and bool(r['path']),'Reference')
    require(type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Reference SHA')
def day(v):
    require(type(v) is str and date.fromisoformat(v).isoformat()==v and date.fromisoformat(v).weekday()<5,'Canonical session');return v
def rational(v):
    require(type(v) is str and 0<len(v)<=1024,'Bounded exact quote');f=Fraction(v);require(str(f)==v and f>0,'Positive canonical exact quote');return f

ENCODING='ALL_KEYS_PRESERVED_NONINTEGER_JSON_NUMBERS_AS_DECIMAL_STRINGS'
RECOVERY_REFERENCES={
 'prior_core':dict(path='E:/Git/us_ratchet/backtest/ndx_multidecision_liquidity_inputs_research.py',sha256='4dca3642c27929231a1399defd5d8d58ac739049558599c7fe5e6f9026706d64'),
 'prior_started':dict(path='E:/Git/us_ratchet/tmp/multidecision_liquidity_saved_probe_20261003_v1/started.json',sha256='5c5cf950d38314245d984d7218294e1b096623c2a873d0cead48c26fe3c3c099'),
 'prior_failure':dict(path='E:/Git/us_ratchet/tmp/multidecision_liquidity_saved_probe_20261003_v1/failure.json',sha256='46af656f69525d059842fb0174f822079aee8b2c7f99f34a6f6e2586fee8f383')}

def compare_split_representations(saved,bridge,encoding):
    require(encoding==ENCODING,'Declared split number encoding')
    require(type(saved) is dict and type(bridge) is dict and set(saved)==set(bridge),'All split keys')
    for key,a in saved.items():
        b=bridge[key];require(type(a) is dict and type(b) is dict and set(a)==set(b),'All event fields')
        for field,v in a.items():
            w=b[field]
            if field in ('numerator','denominator'):
                if type(w) is int:require(type(v) is int and v==w and w>0,'Original integer split number')
                else:
                    require(type(w) is float and math.isfinite(w) and w>0 and type(v) is str and len(v)<=128 and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?',v),'Declared decimal string split number')
                    require(Fraction(Decimal(v))==Fraction(Decimal(str(w))),'Exact encoded split number')
            else:exact(v,w,'Unchanged nonnumeric event field and type')
        require(type(a['date']) is int and a['date']>0 and str(a['date'])==key,'Original event timestamp key')
        ratio=a['splitRatio'];require(type(ratio) is str and re.fullmatch(r'[0-9]+:[0-9]+',ratio),'Original split ratio')
        numerator,denominator=map(int,ratio.split(':'));require(numerator>0 and denominator>0 and Fraction(numerator,denominator)==Fraction(str(a['numerator']))/Fraction(str(a['denominator'])),'Original ratio exact')

def prepare_decision_liquidity(*,channels_document,channels_reference,channels_readback_reference,full_inventory,decision_contract,liquidity_contract):
    s=channels_document; refs=[channels_reference,channels_readback_reference,decision_contract['reference'],liquidity_contract['source_reference'],*RECOVERY_REFERENCES.values()]
    for r in refs:ref(r)
    contract={k:v for k,v in liquidity_contract.items() if k!='source_reference'};exact(contract,CONTRACT,'Frozen63/50m/event/volume contract')
    require(liquidity_contract['source_reference']['sha256']==SOURCE_SHA and liquidity_contract['source_reference']['path'].replace('\\','/').endswith('/backtest/ndx_conditional_channel_input_research.py'),'Frozen liquidity source')
    sources=deepcopy(s['source_hashes'])
    require(type(sources) is dict,'Source declaration map')
    for path,h in sources.items():ref(dict(path=path,sha256=h))
    for r in refs:
        require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Conflicting source reference');sources[r['path']]=r['sha256']
    require(s['schema']=='BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1','Channel schema')
    for k in ('point_in_time_verified','fit_performed','execution_authorized','promotion_allowed','volume_unit_certified','historical_identity_verified','historical_risk_verified','identity_interval_extended','future_independent_oos','untouched_holdout'):require(s[k] is False,'Source authority')
    require(s['evaluation_interval_previously_used_for_fitting'] is True,'Previously consumed interval')
    calendar=s['calendar253'];require(type(calendar) is list and len(calendar)==253 and calendar==sorted(set(calendar)),'Full253 calendar')
    for d in calendar:day(d)
    require(type(full_inventory) is list and full_inventory,'Full inventory')
    for c in full_inventory:require(type(c) is dict and set(c)=={'security_id','issuer_id','ticker'} and all(type(v) is str and v for v in c.values()),'Identity inventory')
    require([c['security_id'] for c in full_inventory]==sorted({c['security_id'] for c in full_inventory}) and len({c['ticker'] for c in full_inventory})==len(full_inventory),'Unique ordered inventory')
    rows=s['rows'];require(type(rows) is list and len(rows)==len(full_inventory),'All rows')
    exact(sorted([{k:r['coordinate'][k] for k in ('security_id','issuer_id','ticker')} for r in rows],key=lambda c:c['security_id']),full_inventory,'Full source inventory')
    for k,n in [('security_count',len(rows)),('issuer_count',len({c['issuer_id'] for c in full_inventory})),('observed_security_count',101)]:require(type(s[k]) is int and s[k]==n,'Exact source count')
    provenance=s['original_provenance_and_missing'];require(type(provenance) is list and len(provenance)==101 and len({p['ticker'] for p in provenance})==101 and {c['ticker'] for c in full_inventory}<={p['ticker'] for p in provenance},'Full101 provenance')
    require(set(s['preserved_evidence_sidecars'])==set(SIDECARS) and set(s['preserved_sidecar_references'])==set(SIDECARS),'All7 sidecars')
    panel_ref=s['input_references']['panel'];ref(panel_ref)
    require(sources.get(panel_ref['path'])==panel_ref['sha256'],'Parent panel source declaration')
    for name in SIDECARS:exact(s['preserved_sidecar_references'][name],dict(panel_ref,json_pointer='/'+name),'Exact sidecar source pointer')
    for r in rows:
        c=r['channel'];require(c['schema']=='BULK_LONG_WINDOW_CONDITIONAL_CHANNEL_V1' and c['ticker']==r['coordinate']['ticker'],'Channel identity')
        require(c['status'] in ('CONDITIONAL_NUMERIC_RESULT','BLOCKED_PRICE_INPUT'),'Channel status')
        for k in ('point_in_time_verified','volume_unit_verified','liquidity_qualified','legal_training_input_admitted','source_bytes_authenticated'):require(c[k] is False,'Conditional channel')
        exact(c['calendar'],calendar,'Channel calendar');exact(r['original_identity_assumed_window'],s['original_identity_assumed_window'],'Original identity interval')
        for key,bridgekey in [('raw_reference','new_raw_reference'),('receipt_reference','new_receipt_reference')]:
            ref(c[key]);exact(c[key],c['bridge_row_preserved'][bridgekey],'Bridge source binding')
            require(sources.get(c[key]['path'])==c[key]['sha256'],'Original source declaration covers reference')
        compare_split_representations(c['returned_events'].get('splits',{}),c['bridge_row_preserved']['new_returned_splits'],c['returned_event_encoding'])
        policies=c['event_policies'];require(type(policies) is list and len({p['session'] for p in policies})==len(policies),'Full event policies')
        require(len(policies)==len(c['returned_events'].get('splits',{}))==len(c['bridge_row_preserved']['event_policy_bridge']['events']),'Full split denominator')
        require([p['session'] for p in policies]==sorted(p['session'] for p in policies),'Ordered policies')
        if c['regular_floor'] is not None:day(c['regular_floor'])
        keys=[b['provider_event_key'] for b in c['bridge_row_preserved']['event_policy_bridge']['events']]
        require(all(type(k) is str and k for k in keys) and len(keys)==len(set(keys)) and set(keys)==set(c['returned_events'].get('splits',{})),'Split bridge bijection')
        for p,b in zip(policies,sorted(c['bridge_row_preserved']['event_policy_bridge']['events'],key=lambda e:e['session'])):
            day(p['session']);require(p['kind'] in ('ORDINARY_SPLIT','BEFORE_PARTITION_UNMODELLED') and type(p['numerator']) is int and type(p['denominator']) is int and p['numerator']>0 and p['denominator']>0,'Event ratio')
            event=c['returned_events']['splits'][b['provider_event_key']];require(b['session']==p['session'] and b['policy']['kind']==p['kind'] and b['policy']['session']==p['session'] and type(b['policy']['numerator']) is int and type(b['policy']['denominator']) is int and Fraction(b['policy']['numerator'],b['policy']['denominator'])==Fraction(p['numerator'],p['denominator']) and Fraction(str(event['numerator']))/Fraction(str(event['denominator']))==Fraction(p['numerator'],p['denominator']),'Split inventory binding')
        if c['status']=='CONDITIONAL_NUMERIC_RESULT':
            q=c['quote_rows'];require(type(q) is list and len(q)==253 and [x['session'] for x in q]==calendar,'No holes or date compression');require(digest(q)==c['quote_rows_sha256'],'Saved quote checksum')
        else:require(c['quote_rows'] is None and c['reasons'],'Blocked source retains reasons')
    d=decision_contract['document'];require(set(d)=={'schema','status','rule','rule_reference','decisions','expected_decision_count','selection_contract_reference','search_budget_reference'},'Explicit draft shape')
    require(d['schema']=='EXPLICIT_HISTORICAL_MULTIDECISION_DRAFT_V1' and d['status']=='DRAFT_NOT_REGISTERED' and d['rule']=='MONTH_FIRST_SAVED_SESSION_EXECUTION_PREVIOUS_SAVED_CLOSE','Explicit historical draft')
    ref(d['rule_reference'])
    for key in ('selection_contract_reference','search_budget_reference'):
        if d[key] is not None:ref(d[key])
    for r in [d['rule_reference'],d['selection_contract_reference'],d['search_budget_reference']]:
        if r is not None:
            require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Decision source conflict');sources[r['path']]=r['sha256']
    require(type(d['decisions']) is list and d['decisions'] and type(d['expected_decision_count']) is int and d['expected_decision_count']==len(d['decisions']),'Decision denominator')
    months={}
    for x in calendar:months.setdefault(x[:7],x)
    periods=[];previous=None
    for decision in d['decisions']:
        require(set(decision)=={'decision_date','execution_date'},'Decision coordinates');cutoff=day(decision['decision_date']);execution=day(decision['execution_date']);require(cutoff in calendar,'Decision in calendar');j=calendar.index(cutoff)
        require(126<=j<252 and calendar[j+1]==execution and months[execution[:7]]==execution and (previous is None or cutoff>previous),'Causal historical clock');previous=cutoff
        dates=calendar[j-62:j+1];items=[]
        for i,r in enumerate(rows):
            c=r['channel'];affected=[p for p in c['event_policies'] if p['session']>=dates[0]];reasons=[]
            if c['status']=='BLOCKED_PRICE_INPUT':reasons+=list(c['reasons'])
            if affected:reasons.append('BLOCKED_VOLUME_UNIT_UNKNOWN_ALL_RETURNED_SPLITS_GE_WINDOW_START')
            if c['regular_floor'] is not None and c['regular_floor']>dates[0]:reasons.append('BEFORE_REGULAR_FLOOR')
            details=[];median=None
            if c['status']=='CONDITIONAL_NUMERIC_RESULT':
                for offset,q in enumerate(c['quote_rows'][j-62:j+1]):
                    close=rational(q['nominal_close_exact']);volume=q['raw_volume']
                    if volume is None:reasons.append('MISSING_RAW_VOLUME');continue
                    require(type(volume) is int and volume>0,'Positive integer unscaled volume')
                    details.append(dict(session=q['session'],nominal_close_exact=str(close),raw_volume=volume,source_reference=dict(channels_reference,json_pointer=f'/rows/{i}/channel/quote_rows/{j-62+offset}')))
                if not reasons:median=sorted(Fraction(q['nominal_close_exact'])*q['raw_volume'] for q in details)[31]
            items.append(dict(coordinate=deepcopy(r['coordinate']),channel_reference=dict(channels_reference,json_pointer=f'/rows/{i}/channel'),status='CONDITIONAL_MDV_COMPUTABLE' if median is not None else 'UNKNOWN_LIQUIDITY',reasons=list(dict.fromkeys(reasons)),required_dates=list(dates),quote_evidence=details,affecting_returned_splits=deepcopy(affected),median_dollar_volume_exact=None if median is None else str(median),conditional_numerical_threshold_passed=None if median is None else median>=50000000,formal_eligibility_verified=False))
        periods.append(dict(**deepcopy(decision),security_denominator=len(rows),rows=items,computable_count=sum(x['status']=='CONDITIONAL_MDV_COMPUTABLE' for x in items),unknown_count=sum(x['status']=='UNKNOWN_LIQUIDITY' for x in items)))
    return dict(schema='CONDITIONAL_MULTIDECISION_LIQUIDITY_INPUTS_V2',recovery_evidence_references=deepcopy(RECOVERY_REFERENCES),recovery_semantics='V1_PREPARATION_FAILED_ON_DECLARED_DECIMAL_STRING_VS_FLOAT_SPLIT_REPRESENTATION;NEW_VERSION_ONLY;PRIOR_NAMESPACE_NOT_RETRIED;WRAPPER_MUST_AUTHENTICATE_PRIOR_BYTES',split_comparison_semantics='ONLY_DECLARED_NUMERATOR_DENOMINATOR_DECIMAL_STRINGS_TO_EXACT_BRIDGE_FLOAT_DECIMAL;ALL_OTHER_FIELDS_TYPED_EXACT;ORIGINAL_OBJECTS_PRESERVED',status='PREPARED_CONDITIONAL_LIQUIDITY_NOT_ELIGIBILITY',periods=periods,full_inventory=deepcopy(full_inventory),original_provenance_and_missing=deepcopy(provenance),preserved_evidence_sidecars=deepcopy(s['preserved_evidence_sidecars']),preserved_sidecar_references=deepcopy(s['preserved_sidecar_references']),original_identity_assumed_window=deepcopy(s['original_identity_assumed_window']),decision_contract=deepcopy(decision_contract),liquidity_contract=deepcopy(liquidity_contract),input_references=dict(channels=deepcopy(channels_reference),saved_readback=deepcopy(channels_readback_reference)),source_hash_declarations=sources,channel_action_and_source_evidence=[dict(coordinate=deepcopy(r['coordinate']),channel_reference=dict(channels_reference,json_pointer=f'/rows/{i}/channel'),**{k:deepcopy(r['channel'][k]) for k in ('raw_reference','receipt_reference','returned_events','event_policies','bridge_row_preserved','regular_floor')}) for i,r in enumerate(rows)],arithmetic='EXACT_FRACTION_MEDIAN_OF_63_NOMINAL_CLOSE_TIMES_UNSCALED_RAW_VOLUME;NOT_LEGACY_FLOAT_BITWISE_PROJECTION',future_event_semantics='RETROSPECTIVE_VOLUME_UNIT_UNCERTAINTY_NOT_INFORMATION_AVAILABLE_AT_DECISION',**FLAGS)

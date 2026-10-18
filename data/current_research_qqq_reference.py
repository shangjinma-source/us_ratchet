"""Pure non-ranking QQQ reference for the frozen daily-close policy only."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json

from data.current_research_fill_ledger import review_paper_ledger
from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_monthly_policy import route_monthly_research_policy
from data.current_research_successor_plan import _review_roll_state,_bind_monthly_session

METHOD='QQQ_MONTHLY_OWN_EQUITY_NONRANKING_DAILY_CLOSE_V1'
SCOPE='FROZEN_DAILY_CLOSE_REFERENCE_NOT_INTRADAY_REFERENCE_VALIDATION'
INITIAL_REVISION='INITIAL_QQQ_REFERENCE'


def _require(ok,reason):
    if not ok:raise ValueError(reason)


def _amount(value):
    _require(not isinstance(value,bool) and isinstance(value,(str,int,Fraction)),'EXACT_MONEY_REQUIRED')
    parsed=Fraction(str(value));_require(parsed>=0,'NEGATIVE_MONEY')
    return parsed


def build_qqq_reference_plan(state=None,*,expected_revision,comparison_anchor,qqq_security,
                             quote_observation,decision_date,active_date,calendar,market_session,
                             source_hashes,unit_continuity,commission_bps='0',minimum_commission='0'):
    """Returns a proposal only. Source truth and paired registration belong to caller.

    A fresh-cash initial proposal does not create a ledger. Later calls require
    an independently verified QQQ ledger, never the stock strategy's account.
    """
    flags=dict(research_only=True,execution_blocked=True,activation_performed=False,
               account_created=False,search_calls=0,selector_calls=0,method=METHOD,method_scope=SCOPE,
               paired_registration_verified=False,source_verified=False,total_return_certified=False,
               other_charges='UNKNOWN_NOT_RESERVED',intraday_rule_validated=False)
    try:
        _require(_amount(commission_bps)==0 and _amount(minimum_commission)==0,'QQQ_REFERENCE_REQUIRES_ZERO_COMMISSION_MODEL')
        _require(isinstance(comparison_anchor,dict) and isinstance(source_hashes,dict),'EXPLICIT_ANCHOR_AND_PINS_REQUIRED')
        def refs(references):
            _require(isinstance(references,list) and references and all(isinstance(p,str) and p in source_hashes for p in references),'SOURCE_REFERENCES_NOT_PINNED')
        refs(comparison_anchor['source_references']);refs(qqq_security['source_references'])
        budget=_amount(comparison_anchor['initial_cash']);_require(budget>0,'POSITIVE_COMPARISON_CAPITAL_REQUIRED')
        start=comparison_anchor['decision_date'];first_active=comparison_anchor['active_date']
        _require(date.fromisoformat(start).isoformat()==start and date.fromisoformat(first_active).isoformat()==first_active,'INVALID_ANCHOR_DATES')
        _require(comparison_anchor['calendar']==calendar,'COMPARATOR_CALENDAR_DIFFERS_FROM_CALLER_ANCHOR')
        sid=qqq_security['security_id']
        _require(isinstance(sid,str) and sid.strip() and qqq_security.get('identifier_kind')=='INTERNAL_RESEARCH_ID'
                 and qqq_security.get('ticker')=='QQQ' and qqq_security.get('security_type')=='ETF'
                 and qqq_security.get('currency')=='USD','EXPLICIT_QQQ_INTERNAL_IDENTITY_REQUIRED')
        observation=quote_observation
        _require(observation.get('ticker')=='QQQ' and observation.get('security_type')=='ETF'
                 and observation.get('decision_date')==decision_date,'QQQ_OBSERVATION_IDENTITY_DATE_MISMATCH')
        _require(observation.get('research_only') is True and observation.get('execution_blocked') is True,'RESEARCH_OBSERVATION_REQUIRED')
        observation_pins=observation['source_hashes']
        _require(isinstance(observation_pins,dict) and observation_pins and all(source_hashes.get(p)==h for p,h in observation_pins.items()),'QUOTE_OBSERVATION_PINS_UNBOUND')
        close_text=observation['ohlc']['close'];close=_amount(close_text);_require(close>0,'NONPOSITIVE_QQQ_CLOSE')
        basis=observation['price_basis'];_require(isinstance(basis,str) and basis,'PRICE_BASIS_REQUIRED')
        if state is None:
            _require(expected_revision==INITIAL_REVISION,'INITIAL_REFERENCE_REVISION_REQUIRED')
            _require((decision_date,active_date)==(start,first_active),'INITIAL_REFERENCE_START_MISMATCH')
            route=route_monthly_research_policy(decision_date=decision_date,active_date=active_date,calendar=calendar,current_target_month=active_date[:7])
            route.update(action='INITIAL_REFERENCE',reason='EXPLICIT_CALLER_COMPARISON_ANCHOR')
            cash=budget;held={};equity=budget;target={sid:int(budget//close)};selection_date=decision_date
            snapshot=None;from_date=decision_date;pins=deepcopy(source_hashes)
        else:
            reviewed=_review_roll_state(state,expected_revision,decision_date,active_date,calendar)
            for field in ('receivable','receivables','merger_entitlements','distribution_entitlements','pending_rights'):
                _require(not state.get(field),'UNSUPPORTED_CAPITAL_COMPONENT')
            old=state['plan'];snapshot=old['causal_inputs']['research_snapshot']
            _require(snapshot.get('method')==METHOD and snapshot.get('comparison_anchor')==comparison_anchor,'NOT_MATCHING_INDEPENDENT_QQQ_REFERENCE_ACCOUNT')
            first=state['plans'][0]
            _require(_amount(first['available_cash'])==budget and first['signal_asof']==start and first['active_date']==first_active
                     and not any(first['causal_inputs']['shares'].values()),'QQQ_GENESIS_DIFFERS_FROM_ANCHOR')
            _require(set(reviewed['shares'])<={sid} and set(old['target_quantities'])<={sid},'NON_QQQ_ASSETS_OR_TARGETS')
            _require(all(p['causal_inputs']['securities']=={sid:'QQQ'} for p in state['plans']),'QQQ_IDENTITY_HISTORY_CHANGED')
            _require(old['causal_inputs']['quotes'][sid]['price_basis']==basis,'QQQ_UNIT_BASIS_CHANGED')
            pins=deepcopy(snapshot['source_hashes'])
            for path,value in source_hashes.items():
                _require(path not in pins or pins[path]==value,'SOURCE_PIN_CONFLICT');pins[path]=value
            cash=_amount(reviewed['cash']);held=deepcopy(reviewed['shares']);equity=cash+held.get(sid,0)*close
            route=route_monthly_research_policy(decision_date=decision_date,active_date=active_date,calendar=calendar,current_target_month=snapshot['target_month'])
            target={sid:int(equity//close)} if route['action']=='RESELECT' else deepcopy(old['target_quantities'])
            selection_date=decision_date if route['action']=='RESELECT' else snapshot['as_of']
            from_date=old['causal_inputs']['decision_date']
        continuity=unit_continuity
        _require(isinstance(continuity,dict) and continuity.get('from_date')==from_date and continuity.get('to_date')==decision_date
                 and continuity.get('price_basis')==basis and continuity.get('status')=='NO_UNPROCESSED_ACTIONS_OR_DIVIDENDS','QQQ_CONTINUITY_DECLARATION_REQUIRED')
        refs(continuity['source_references'])
        events=observation['event_details'];_require(isinstance(events,list),'EXPLICIT_RETURNED_EVENT_DETAILS_REQUIRED')
        ignored_events=[]
        orders={} if state is None else {(p['plan_id'],o['order_id']):o for p in state['plans'] for o in p['orders']}
        def shares_before(day):
            if state is None:return 0
            quantity=0
            for event in state['events']:
                if event.get('event_type','FILL')!='FILL' or event['session']>=day:continue
                order=orders[(event['plan_id'],event['order_id'])]
                if order['security_id']==sid:quantity+=(1 if order['side']=='BUY' else -1)*event['qty']
            return quantity
        for event in events:
            day=event['session'];_require(date.fromisoformat(day).isoformat()==day,'INVALID_EVENT_DATE')
            # Newly returned evidence may predate the current plan; no action
            # accounting exists in this adapter, so inspect the entire account life.
            if start<day<=decision_date or (day==decision_date and state is None):
                before=shares_before(day)
                target_exposed=state is not None and state['plan']['target_quantities'].get(sid,0)>0 and day>from_date
                exposed=before>0 or (event['kind']!='dividends' and target_exposed)
                _require(not exposed,'UNSUPPORTED_EXPOSED_QQQ_ACTION_OR_DIVIDEND:'+event['kind'])
                ignored_events.append(dict(session=day,kind=event['kind'],pre_session_shares=before,
                                           reason='NO_PRE_EVENT_ASSET_ENTITLEMENT_OR_UNIT_EXPOSED_TARGET'))
        if snapshot is not None and route['action']=='ROLL':snapshot=deepcopy(snapshot)
        else:
            binding=dict(method=METHOD,comparison_anchor=comparison_anchor,decision_date=decision_date,quote_observation=observation,
                         account_revision=expected_revision,equity=str(equity),target_quantities=target,source_hashes=pins)
            research_id=sha256(json.dumps(binding,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()[:24]
            snapshot=dict(research_id=research_id,method=METHOD,selection_method=METHOD,research_version=METHOD,as_of=selection_date,
                          stocks=[dict(security_id=sid,ticker='QQQ')],comparison_anchor=deepcopy(comparison_anchor),
                          qqq_identity=deepcopy(qqq_security),scope=SCOPE,paired_registration_verified=False)
        snapshot.update(source_hashes=pins,unit_continuity=deepcopy(continuity),research_only=True,execution_blocked=True)
        _bind_monthly_session(snapshot,target_month=route['target_month'],market_session=market_session,active_date=active_date,source_hashes=pins)
        plan=build_current_research_limit_plan(research_snapshot=snapshot,
            quotes=[dict(security_id=sid,price=close_text,as_of=decision_date,price_kind='RAW_PROVIDER_CLOSE_DECIMAL',price_basis=basis,source_references=list(observation_pins))],
            available_cash=str(cash),shares=held,account_revision=expected_revision,decision_date=decision_date,active_date=active_date,
            calendar=calendar,strategy_version=METHOD,target_quantities=target)
        _require(plan['status']=='READY','QQQ_PLAN_BLOCKED:'+str(plan.get('reason')))
        return dict(flags,status='READY',plan=plan,route=route,target_quantities=target,investable_equity=str(equity),available_cash=str(cash),
                    target_recalculated=route['action']!='ROLL',initial_cash=str(budget),source_hashes=pins,
                    action_completeness_verified=False,ignored_unexposed_events=ignored_events,limitations=['Only declared exact raw Close, sources and continuity are checked; source authenticity belongs to caller.',
                    'This proposal neither starts a comparator account nor establishes paired prospective registration.',
                    'No ranking, historical QQQ performance, intraday reference, dividends, rights or external cash injection is inferred.'])
    except (ValueError,KeyError,TypeError,OverflowError,ZeroDivisionError) as error:
        return dict(flags,status='BLOCKED',reason=str(error),plan=None)

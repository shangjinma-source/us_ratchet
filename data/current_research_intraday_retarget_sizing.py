"""Pure fresh-price TOP1 retarget differences; no order activation or sales credit."""
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
from hashlib import sha256
import json
import re
from zoneinfo import ZoneInfo
from data.current_research_intraday_monthly_selection import build_intraday_monthly_top1_selection
from data.current_research_intraday_continuation_ledger import review_continuation_ledger
from data.current_research_intraday_buy_plan import _require,_time,_cash

POLICY='FRESH_REGULAR_BUY_LOW_CAP_SELL_LAST_CEIL_V1'


def build_intraday_retarget_sizing(state,*,selection,selection_inputs,execution_references,
        execution_unit_continuity,source_hashes,now):
    flags=dict(research_only=True,execution_blocked=True,activated=False,account_mutated=False,
               source_authenticated=False,forecast_return=None,global_optimum_established=False,
               schema='FRESH_INTRADAY_TOP1_RETARGET_SIZING_V1')
    try:
        now=_time(now);verified=review_continuation_ledger(state)
        _require(not {'state','now'} & set(selection_inputs),'SELECTION_ARGUMENT_SCHEMA')
        selected_at=_time(selection['binding']['selected_at'])
        rebuilt=build_intraday_monthly_top1_selection(state,now=selected_at,**selection_inputs)
        _require(rebuilt['status']=='READY' and rebuilt==selection,'SELECTION_RECONSTRUCTION_MISMATCH')
        _require(selected_at<=now,'SELECTION_AFTER_NOW')
        _require(selection['binding']['account_revision']==verified['revision'],'STALE_SELECTION_REVISION')
        cash=Fraction(verified['cash']);held={sid:q for sid,q in verified['shares'].items() if q}
        winner=selection['selected_security_id'];needed=set(held)|{winner}
        _require(isinstance(execution_references,dict) and set(execution_references)==needed
                 and isinstance(execution_unit_continuity,dict) and set(execution_unit_continuity)==needed,'COMPLETE_HELD_AND_SELECTED_REFERENCES_REQUIRED')
        _require(isinstance(source_hashes,dict) and source_hashes and all(isinstance(p,str) and p and isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) for p,h in source_hashes.items()),'EXECUTION_SOURCE_PINS_REQUIRED')
        for p,h in selection['binding']['source_hashes'].items():_require(source_hashes.get(p)==h,'SELECTION_SOURCE_PIN_CHANGED')
        month=selection['target_month'];scope=verified['account_id']+':'+month
        session=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        _require(session[:7]==month,'TARGET_MONTH_MISMATCH')
        metadata=selection['binding']['training_input']['search_arguments']['metadata']
        historical_security=verified['acceptance']['proposal']['security']
        floor=_time(selection['binding']['capital']['capital']['ledger_observation_floor'])
        limits={};lasts={};deadlines=[]
        for sid in sorted(needed):
            ref=execution_references[sid];unit=execution_unit_continuity[sid]
            ticker=metadata[sid]['ticker'] if sid==winner else historical_security['ticker']
            if sid!=winner:_require(sid==historical_security['security_id'],'UNKNOWN_HELD_SECURITY')
            if sid in held:_require(sid==historical_security['security_id'] and ticker==historical_security['ticker'],'HELD_IDENTITY_CHANGED')
            _require(ref['security_id']==sid and ref['ticker']==ticker and ref['session']==session
                     and ref['scope_id']==scope and ref['policy']==POLICY,'EXECUTION_REFERENCE_BINDING_MISMATCH')
            opening=_time(ref['session_open']);closing=_time(ref['session_close'])
            captured=_time(ref['captured_at']);checked=_time(ref['checked_at']);end=_time(ref['minute_end']);start=_time(ref['minute_start']);tick=_time(ref['last_at']);deadline=_time(ref['valid_until'])
            # A saved provider response may contain a future tick and become
            # valid later. Journal replay retains its real capture time.
            tick_upper = checked if ref.get('source_kind') == 'INTRADAY_JOURNAL_OBSERVATION_V1' else captured
            _require(selected_at<=checked<=now<deadline<=closing and opening<=checked<closing and opening<=tick and opening<=start and floor<=tick<=tick_upper and captured<=checked
                     and (checked-tick).total_seconds()<=120 and start.second==0 and start.microsecond==0
                     and (end-start).total_seconds()==60 and end<=captured and (checked-end).total_seconds()<=120
                     and deadline<=min(tick+timedelta(seconds=120),end+timedelta(seconds=120)), 'STALE_OR_INVALID_EXECUTION_REFERENCE_TIME')
            _require(all(t.astimezone(ZoneInfo('America/New_York')).date().isoformat()==session for t in (opening,closing,start,end,tick,checked,deadline)),'REFERENCE_SESSION_COORDINATE_MISMATCH')
            last=_cash(ref['last_price']);low=_cash(ref['minute_low']);buy=_cash(ref['buy_limit']);sell=_cash(ref['sell_limit'])
            _require(min(last,low,buy,sell)>0,'NONPOSITIVE_EXECUTION_PRICE')
            prior=ref['prior_buy_cap'];raw=min(last,low) if prior is None else min(last,low,_cash(prior))
            expected_buy=Fraction(raw*100//1,100);expected_sell=Fraction(-(-last*100//1),100)
            _require(buy==expected_buy and sell==expected_sell,'EXECUTION_LIMIT_POLICY_MISMATCH')
            pins=ref['source_hashes'];_require(isinstance(pins,dict) and pins and all(source_hashes.get(p)==h for p,h in pins.items()),'REFERENCE_SOURCE_NOT_PINNED')
            _require(unit['security_id']==sid and unit['selection_decision_id']==selection['decision_id']
                     and unit['status']=='NO_UNPROCESSED_ACTIONS' and unit['reference_source_hashes']==pins
                     and unit['price_basis']=='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS','EXECUTION_UNIT_BINDING_MISMATCH')
            refs=unit['source_references'];_require(isinstance(refs,list) and refs and all(p in source_hashes for p in refs),'EXECUTION_UNIT_SOURCE_NOT_PINNED')
            _require(_time(unit['covered_from'])<=selected_at<=checked<=_time(unit['covered_through'])<=_time(unit['reviewed_asof'])<=now,'EXECUTION_UNIT_TIME_COVERAGE_INVALID')
            limits[sid]=(buy,sell);lasts[sid]=last;deadlines.append(deadline)
        equity=cash+sum((q*lasts[sid] for sid,q in held.items()),Fraction(0))
        target={winner:int(equity//limits[winner][0])};orders=[];waiting=[];remaining=cash
        for sid in sorted(needed):
            delta=target.get(sid,0)-held.get(sid,0)
            if delta<0:orders.append(dict(security_id=sid,side='SELL',quantity=-delta,limit_price=str(limits[sid][1])))
            if delta>0:
                buy=limits[sid][0];quantity=min(delta,int(remaining//buy))
                if quantity:orders.append(dict(security_id=sid,side='BUY',quantity=quantity,limit_price=str(buy)));remaining-=quantity*buy
                if quantity<delta:waiting.append(dict(security_id=sid,remaining_deficit=delta-quantity,reason='WAIT_CASH'))
        binding=dict(account_id=verified['account_id'],account_revision=verified['revision'],selection=deepcopy(selection),
            execution_references=deepcopy(execution_references),execution_unit_continuity=deepcopy(execution_unit_continuity),source_hashes=deepcopy(source_hashes),
            target_quantities=target,cash=str(cash),shares=deepcopy(held),selection_equity=selection['investable_equity'],sizing_equity=str(equity),
            proposed_at=now.isoformat(),reference_valid_until=min(deadlines).isoformat(),orders=orders,wait_cash=waiting)
        identifier=sha256(json.dumps(binding,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        return dict(flags,status='READY',proposal_id=identifier,binding=binding,target_quantities=target,orders=orders,wait_cash=waiting,
            actual_cash=str(cash),reserved_buy_cash=str(cash-remaining),unreserved_cash=str(remaining),
            selection_equity=selection['investable_equity'],sizing_equity=str(equity),unfilled_sell_proceeds_available='0',
            reference_valid_until=min(deadlines).isoformat(),action='PROPOSE_DIFFERENCES' if orders else 'WAIT_CASH' if waiting else 'NO_ACTION',
            limitations=['Pure reference mathematics and declared source bindings only; the server reader must replay pinned raw observations.',
                'SELL uses fresh last rounded upward, not the BUY cap, bid/ask, or a validated return rule.',
                'Targets use fresh BUY limits; unfilled sales never increase reserved BUY cash. No orders are activated.'])
    except (ValueError,KeyError,TypeError,ZeroDivisionError) as error:
        return dict(flags,status='BLOCKED',reason=str(error),proposal_id=None)

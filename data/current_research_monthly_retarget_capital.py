"""Verified intraday account capital for a future monthly retarget proposal.

Does not select securities, create targets/orders, or certify supplied sources.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import re
from zoneinfo import ZoneInfo
from data.current_research_intraday_continuation_ledger import review_continuation_ledger
from data.current_research_intraday_buy_plan import _require,_time,_cash


def build_monthly_retarget_capital(state,*,expected_revision,initial_capital_identity,
        valuation_quotes,unit_continuity,source_hashes,market_session,now):
    flags=dict(research_only=True,execution_blocked=True,source_authenticated=False,
               selection_performed=False,orders_generated=False,account_mutated=False,
               schema='VERIFIED_INTRADAY_MONTHLY_RETARGET_CAPITAL_V1')
    try:
        verified=review_continuation_ledger(state);now=_time(now)
        _require(verified['revision']==expected_revision,'STALE_ACCOUNT_REVISION')
        _require(Fraction(verified['reserved_cash'])==0 and (verified['closed'] is not None or verified['filled_quantity']==verified['order']['quantity']),'OPEN_ORDER_OR_RESERVATION')
        _require(not verified['events'] or _time(verified['events'][-1]['recorded_at'])<=now,'ACCOUNT_HISTORY_AFTER_NOW')
        for key in ('receivable','receivables','pending_rights','merger_entitlements','distribution_entitlements'):
            _require(not verified.get(key),'UNSUPPORTED_CAPITAL_COMPONENT')
        observation_times=[_time(verified['acceptance']['accepted_at'])]
        observation_times.extend(_time(event['recorded_at']) for event in verified['events'])
        observation_times.extend(_time(operation['evidence']['accepted_at']) for operation in verified.get('operations',[]) if operation['kind']=='ACCEPT')
        observation_floor=max(observation_times)
        _require(observation_floor<=now,'LEDGER_OBSERVATION_AFTER_NOW')
        original=verified['acceptance']['proposal'];causal=original['causal_inputs']
        identity=dict(account_id=verified['account_id'],initial_acceptance_id=verified['acceptance_id'],
            initial_proposal_id=original['proposal_id'],initial_research_id=original['research_id'],
            initial_cash=causal['available_cash'])
        _require(initial_capital_identity==identity,'INITIAL_CAPITAL_IDENTITY_MISMATCH')
        principal=sum((event['quantity']*Fraction(event['price']) for event in verified['events'] if event['kind']=='FILL'),Fraction(0))
        recorded_fees=sum((Fraction(event['fees']) for event in verified['events'] if event['kind']=='FILL'),Fraction(0))
        _require(recorded_fees==Fraction(verified['fees']) and Fraction(identity['initial_cash'])==Fraction(verified['cash'])+principal+recorded_fees,'INITIAL_CASH_PRINCIPAL_FEES_IDENTITY_MISMATCH')
        _require(isinstance(source_hashes,dict) and source_hashes and all(isinstance(p,str) and p and isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) for p,h in source_hashes.items()),'SOURCE_PINS_REQUIRED')
        def refs(items):
            _require(isinstance(items,list) and items and all(isinstance(p,str) and p in source_hashes for p in items),'SOURCE_REFERENCES_NOT_PINNED')
        day=market_session['date'];ny=ZoneInfo('America/New_York')
        opening=_time(market_session['open_at']);closing=_time(market_session['close_at'])
        _require(market_session['timezone']=='America/New_York' and opening<=now<closing
                 and all(t.astimezone(ny).date().isoformat()==day for t in (now,opening,closing)),'OUTSIDE_BOUND_SESSION')
        refs(market_session['source_references'])
        held={sid:q for sid,q in verified['shares'].items() if q}
        _require(isinstance(valuation_quotes,list) and isinstance(unit_continuity,dict),'EXPLICIT_QUOTE_AND_UNIT_DOMAIN_REQUIRED')
        quotes={}
        for quote in valuation_quotes:
            sid=quote['security_id'];_require(sid not in quotes,'DUPLICATE_QUOTE')
            quotes[sid]=quote
        _require(set(quotes)==set(held)==set(unit_continuity),'ACTUAL_HELD_VALUATION_DOMAIN_MISMATCH')
        marks={};declared_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS'
        for sid,q in held.items():
            quote=quotes[sid];unit=unit_continuity[sid]
            _require(sid==original['security']['security_id'] and quote['ticker']==original['security']['ticker'],'HISTORICAL_SECURITY_BINDING_MISMATCH')
            _require(quote['currency']=='USD' and quote['price_basis']==declared_basis
                     and quote['price_kind']=='REGULAR_MARKET_LAST','INTRADAY_UNIT_PRICE_KIND_REQUIRED')
            price=_cash(quote['price']);_require(price>0,'NONPOSITIVE_MARK')
            timestamp=_time(quote['quoted_at']);capture=_time(quote['captured_at'])
            _require(opening<=timestamp<=capture<=now and observation_floor<=timestamp and (now-timestamp).total_seconds()<=120,'STALE_OR_FUTURE_INTRADAY_MARK')
            refs(quote['source_references'])
            _require(unit['security_id']==sid and unit['price_basis']==declared_basis
                     and unit['status']=='NO_UNPROCESSED_ACTIONS'
                     and unit['initial_event_sha256']==causal['event_sha256']
                     and unit['quote_source_references']==quote['source_references'],'UNIT_EVIDENCE_BINDING_MISMATCH')
            _require(_time(unit['covered_from'])<=_time(causal['observation']['checked_at'])
                     and timestamp<=_time(unit['covered_through'])<=_time(unit['reviewed_asof'])<=now,'UNIT_COVERAGE_OR_REVIEW_TIME_INVALID')
            refs(unit['source_references']);marks[sid]=q*price
        cash=Fraction(verified['cash']);equity=cash+sum(marks.values(),Fraction(0))
        binding=dict(account_revision=expected_revision,initial_capital_identity=identity,
            cash=str(cash),shares=deepcopy(held),recorded_fees=verified['fees'],
            recorded_buy_principal=str(principal),ledger_observation_floor=observation_floor.isoformat(),
            valuation_quotes=deepcopy(valuation_quotes),unit_continuity=deepcopy(unit_continuity),
            source_hashes=deepcopy(source_hashes),market_session=deepcopy(market_session),as_of=now.isoformat(),
            stock_value=str(sum(marks.values(),Fraction(0))),investable_equity=str(equity),
            buy_cash_limit=str(cash),unfilled_sell_proceeds_available='0')
        identifier=sha256(json.dumps(binding,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        return dict(flags,status='READY',capital_binding_id=identifier,capital=binding,
            limitations=['No new-month target or selection is accepted by this component.',
                'Quote freshness and pinned declarations are checked; raw-source authenticity and action completeness require a server loader.',
                'Equity is a sizing reference. Only existing cash can reserve new BUY orders; anticipated sales are unavailable.',
                '120-second mark freshness reuses the present engineering quote rule, not a validated return improvement.'])
    except (ValueError,KeyError,TypeError,ZeroDivisionError) as error:
        return dict(flags,status='BLOCKED',reason=str(error),capital_binding_id=None)

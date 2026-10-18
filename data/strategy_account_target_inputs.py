"""Verified input construction only: historical training and current capital are distinct.

Reuses the raw monthly compiler, not its paper-account registry. Unit reviews are
explicit caller-authenticated conditional evidence, not complete action/PIT proof.
No search, account mutation, price fetch or executable target is produced.
"""
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import replay, canonical
from data.current_quantity_v2_monthly_training import compile_saved_training
from data.current_research_capital_decision_v2 import VERSION


def require(ok,reason):
    if not ok:raise ValueError(reason)


def stamp(value):
    require(isinstance(value,str),'TIMESTAMP_REQUIRED')
    value=datetime.fromisoformat(value)
    require(value.tzinfo is not None and value.utcoffset() is not None,'AWARE_TIMESTAMP_REQUIRED')
    return value


def build_target_inputs(*,state,source_package,manifest_path,marks_path,unit_review_path,
                        now,maximum_mark_age_seconds):
    require(replay(state['account_id'],[e['payload'] for e in state['events']])==state,'ACCOUNT_REPLAY_MISMATCH')
    require(state['cash_confirmation_valid'] and state['cash_confirmed_for_holdings_revision']==state['holdings_revision'],'CASH_RECONFIRMATION_REQUIRED')
    require(state['execution_ready'],'ACCOUNT_RESERVATIONS_REQUIRE_RECONCILIATION')
    require(type(maximum_mark_age_seconds) is int and maximum_mark_age_seconds>0,'EXPLICIT_FRESHNESS_REQUIRED')
    current=stamp(now)
    files,pins=source_package['files'],source_package['source_hashes']
    require(set(files)==set(pins) and sum(len(raw) for raw in files.values())<=128*1024*1024,'SOURCE_PACKAGE_BUDGET_OR_DOMAIN')
    require(all(isinstance(raw,bytes) and len(raw)<=32*1024*1024 and sha256(raw).hexdigest()==pins[path] for path,raw in files.items()),'SOURCE_HASH_MISMATCH')
    for path in (manifest_path,marks_path,unit_review_path):require(path in files,'REQUIRED_SOURCE_MISSING')
    compiled=compile_saved_training(source_package,manifest_path)
    historical=compiled['input']['search_arguments']
    cutoff=historical['decision_date']
    valuation_day=current.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(cutoff<=valuation_day,'TRAINING_AFTER_VALUATION')
    marks=json.loads(files[marks_path]);review=json.loads(files[unit_review_path])
    domain=set(historical['prices'])
    needed=domain|{sid for sid,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
    require(isinstance(marks,dict) and set(marks)==needed,'FULL_CANDIDATE_HELD_MARKS_REQUIRED')
    require(review.get('schema')=='STRATEGY_TARGET_UNIT_REVIEW_V1' and review.get('status')=='CONDITIONAL_CURRENT_UNITS_REVIEWED','UNIT_REVIEW_REQUIRED')
    require(review.get('training_manifest_sha256')==pins[manifest_path] and review.get('historical_search_arguments_sha256')==sha256(canonical(historical)).hexdigest()
            and review.get('marks_sha256')==pins[marks_path] and review.get('account_revision')==state['revision'],'UNIT_REVIEW_BINDING_MISMATCH')
    require(review.get('training_cutoff_date')==cutoff and set(review.get('securities',{}))==needed,'UNIT_REVIEW_DOMAIN_MISMATCH')
    require(review.get('unresolved')==[] and review.get('pending_rights')==[],'UNRESOLVED_UNIT_OR_RIGHTS')
    reviewed=stamp(review['reviewed_at']);require(reviewed<=current,'FUTURE_UNIT_REVIEW')
    training_closed=stamp(review['training_closed_at'])
    require(training_closed.astimezone(ZoneInfo('America/New_York')).date().isoformat()==cutoff and training_closed<=reviewed<=current,'TRAINING_NOT_CLOSED')
    def references(row):
        refs=row.get('source_references')
        require(isinstance(refs,list) and bool(refs) and all(isinstance(p,str) and p in pins for p in refs),'UNPINNED_EVIDENCE')
    references(review)
    values={};basis=None
    for sid in sorted(needed):
        mark=marks[sid];unit=review['securities'][sid]
        require(mark.get('security_id')==sid and mark.get('currency')=='USD','MARK_IDENTITY_OR_CURRENCY')
        observed=stamp(mark['observed_at'])
        require(0<=(current-observed).total_seconds()<=maximum_mark_age_seconds and training_closed<=observed<=reviewed,'STALE_OR_FUTURE_MARK')
        require(isinstance(mark.get('price'),(str,int)) and not isinstance(mark['price'],bool),'EXACT_MARK_REQUIRED')
        values[sid]=Fraction(mark['price']);require(values[sid]>0,'NONPOSITIVE_MARK')
        require(isinstance(mark.get('price_basis'),str) and bool(mark['price_basis']),'CURRENT_UNIT_REQUIRED')
        basis=basis or mark['price_basis'];require(basis==mark['price_basis'],'MIXED_MARK_UNITS')
        require(unit.get('security_id')==sid and unit.get('current_price_basis')==basis
                and unit.get('current_mark_sha256')==sha256(canonical(mark)).hexdigest()
                and unit.get('historical_price_basis')==historical['price_basis']
                and unit.get('training_manifest_sha256')==pins[manifest_path]
                and unit.get('historical_scenarios_usable_in_current_units') is True
                and unit.get('held_quantities_in_current_units') is True
                and stamp(unit['covered_through'])>=observed
                and stamp(unit['covered_through'])<=reviewed,'UNIT_CONTINUITY_NOT_BOUND')
        references(mark);references(unit)
    cash=Fraction(state['total_uninvested_cash'])
    holding_values={sid:str(q*values[sid]) for sid,q in state['shares'].items() if q}
    equity=cash+sum((Fraction(v) for v in holding_values.values()),Fraction(0))
    require(equity>0,'NONPOSITIVE_STRATEGY_EQUITY')
    arguments=deepcopy(historical)
    arguments.pop('quote_as_of');arguments.pop('price_basis')
    arguments.update(decision_date=valuation_day,entered_cash=str(equity),prices={sid:str(values[sid]) for sid in sorted(domain)})
    binding=dict(schema='STRATEGY_ACCOUNT_TARGET_INPUT_V1',selection_method=VERSION,
        account_id=state['account_id'],account_revision=state['revision'],holdings_revision=state['holdings_revision'],
        training_cutoff_date=cutoff,valuation_at=now,valuation_date=valuation_day,
        historical_search_arguments=deepcopy(historical),search_arguments=arguments,
        strategy_shares=deepcopy(state['shares']),total_uninvested_cash=str(cash),strategy_equity=str(equity),
        holding_market_values=holding_values,marks=deepcopy(marks),current_price_basis=basis,
        execution_context=dict(pending_orders=[deepcopy(o) for o in state['orders'].values() if o['status']=='OPEN'],
            reserved_cash=state['reserved_cash'],reserved_shares=deepcopy(state['reserved_shares']),available_cash=state['available_cash'],
            cash_confirmation_revision=state['cash_confirmed_for_holdings_revision'],sell_proceeds_available=False),
        source_hashes=deepcopy(pins),documents=dict(training_manifest=manifest_path,marks=marks_path,unit_review=unit_review_path))
    return dict(status='INPUTS_READY_NOT_EXECUTED',input_id=sha256(canonical(binding)).hexdigest(),binding=binding,
        core_calls=0,orders_created=False,execution_blocked=True,source_bytes_verified=True,
        source_authenticated=False,full_actions_verified=False,full_pit_verified=False,
        limitations=['Current prices replace historical purchase costs; historical gross scenarios remain unchanged.',
                    'Conditional unit review is supplied evidence, not independent completeness authentication.',
                    'Pending orders remain execution obligations; target differences require current revision and reservation checks.'])

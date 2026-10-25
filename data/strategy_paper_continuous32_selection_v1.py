"""Independent paper-equity adapter to the actual continuous32 selector.

Selection-only application, no web authority, target publication or orders.
The raw training compiler and original continuous32 validator remain unchanged.
Conditional source reviews are not vendor authenticity or PIT completeness.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import json
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical
from data.strategy_account_target_inputs import require, stamp
from data.current_quantity_v2_monthly_training import compile_saved_training
from data.strategy_continuous32_target_decision import VERSION, PROFILE_ID, REQUIRED_PINS, validate_result
from backtest.continuous_guided_account_decision import enhanced_search
from backtest.current_strategy_paper_slice_v1 import replay, project

ROOT = Path(__file__).resolve().parents[1]
SCOPE = 'ISOLATED_CURRENT_STRATEGY_PAPER_SELECTION_ONLY'
CODE_PATHS = set(REQUIRED_PINS) | {
    'backtest/current_strategy_paper_slice_v1.py',
    'data/strategy_paper_continuous32_selection_v1.py',
    'data/strategy_account_target_inputs.py',
    'data/strategy_continuous32_target_decision.py',
    'data/current_quantity_v2_monthly_training.py',
}


def _admit(*, book, application_bytes, trusted_application_sha256, calendar_bytes, source_package, now):
    require(type(application_bytes) is bytes and sha256(application_bytes).hexdigest()==trusted_application_sha256,
            'PAPER_SELECTION_APPLICATION_HASH')
    app=json.loads(application_bytes)
    require(app.get('schema')=='CURRENT_STRATEGY_PAPER_SELECTION_APPLICATION_V1' and
            app.get('scope')==SCOPE and app.get('approved_for_selection') is True and
            app.get('automatic_acceptance_allowed') is False, 'PAPER_SELECTION_APPLICATION_SCOPE')
    verified=replay(book)
    current=stamp(now)
    require(app['account_id']==verified['application']['account_id'] and
            app['ledger_schema']==verified['schema'] and
            app['account_genesis_sha256']==sha256(canonical(verified['application'])).hexdigest(),
            'PAPER_SELECTION_ACCOUNT_BINDING')
    require(stamp(app['approved_at'])<=stamp(app['valid_from'])<=current<stamp(app['valid_until']),
            'PAPER_SELECTION_APPLICATION_TIME')
    require(app['selector_profile']==PROFILE_ID and app['selection_method']==VERSION and
            type(app['continuous_iterations']) is int and app['continuous_iterations']==32,
            'PAPER_SELECTION_PROFILE')
    require(type(app['code_sha256']) is dict and set(app['code_sha256'])==CODE_PATHS and
            all(sha256((ROOT/path).read_bytes()).hexdigest()==h for path,h in app['code_sha256'].items()),
            'PAPER_SELECTION_CODE_CHANGED')
    require(type(calendar_bytes) is bytes and len(calendar_bytes)<=4*1024*1024 and
            sha256(calendar_bytes).hexdigest()==app['calendar_sha256'], 'PAPER_SELECTION_CALENDAR_HASH')
    calendar=json.loads(calendar_bytes)
    require(calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange']=='NASDAQ',
            'PAPER_SELECTION_CALENDAR_IDENTITY')
    days=[];previous=None
    for session in calendar['sessions']:
        opened,closed=stamp(session['open']),stamp(session['close'])
        day=session['date']
        require(opened<closed and (previous is None or previous<opened) and
                opened.astimezone(ZoneInfo('America/New_York')).date().isoformat()==day and
                closed.astimezone(ZoneInfo('America/New_York')).date().isoformat()==day,
                'PAPER_SELECTION_CALENDAR_SESSION')
        days.append(day);previous=closed
    require(days==sorted(set(days)) and any(stamp(s['open'])<=current<stamp(s['close'])
            for s in calendar['sessions']), 'PAPER_SELECTION_OUTSIDE_SESSION')
    require(sha256(canonical(source_package['source_hashes'])).hexdigest()==app['admitted_source_hashes_sha256'],
            'PAPER_SELECTION_SOURCE_ADMISSION_BINDING')
    require(all(source_package['source_hashes'].get(path)==app['code_sha256'][path]
                for path in CODE_PATHS), 'PAPER_SELECTION_SOURCE_CODE_BINDING')
    require(verified['last_available_at'] is None or stamp(verified['last_available_at'])<=current,
            'PAPER_SELECTION_BEFORE_STATE_AVAILABLE')
    state=project(verified)
    state.update(holdings_revision=state['revision'], total_uninvested_cash=state['cash'],
                 reserved_cash=str(Fraction(state['cash'])-Fraction(state['available_cash'])),
                 orders={o['order_id']:dict(o,status='OPEN') for o in state['pending_orders']})
    return app,state,calendar


def build_paper_target_inputs(*,book,application_bytes,trusted_application_sha256,calendar_bytes,
        source_package,manifest_path,marks_path,unit_review_path,now,maximum_mark_age_seconds):
    app,state,calendar=_admit(book=book,application_bytes=application_bytes,
        trusted_application_sha256=trusted_application_sha256,calendar_bytes=calendar_bytes,
        source_package=source_package,now=now)
    require(type(maximum_mark_age_seconds) is int and 0<maximum_mark_age_seconds<=120,
            'PAPER_EXPLICIT_FRESHNESS_REQUIRED')
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
    binding=dict(schema='PAPER_CONTINUOUS32_TARGET_INPUT_V1',selection_method=VERSION,
        account_id=state['account_id'],account_revision=state['revision'],holdings_revision=state['holdings_revision'],
        training_cutoff_date=cutoff,valuation_at=now,valuation_date=valuation_day,
        historical_search_arguments=deepcopy(historical),search_arguments=arguments,
        strategy_shares=deepcopy(state['shares']),total_uninvested_cash=str(cash),strategy_equity=str(equity),
        holding_market_values=holding_values,marks=deepcopy(marks),current_price_basis=basis,
        execution_context=dict(pending_orders=[deepcopy(o) for o in state['orders'].values() if o['status']=='OPEN'],
            reserved_cash=state['reserved_cash'],reserved_shares=deepcopy(state['reserved_shares']),available_cash=state['available_cash'],
            paper_state_revision=state['revision'],sell_proceeds_available=False),
        source_hashes=deepcopy(pins),documents=dict(training_manifest=manifest_path,marks=marks_path,unit_review=unit_review_path))
    manifest=json.loads(files[manifest_path])
    sessions={s['date']:s for s in calendar['sessions']}
    require(cutoff in sessions and stamp(review['training_closed_at'])==stamp(sessions[cutoff]['close']) and
            manifest['training_dates']==[d for d in sessions if d<=cutoff][-253:],
            'PAPER_TRAINING_CALENDAR_BINDING')
    require(all(type(v) in (str,int) for v in (historical['fee_bps'],app['fee_bps'],book['application']['fee_bps']))
            and Fraction(historical['fee_bps'])==Fraction(app['fee_bps'])==Fraction(book['application']['fee_bps']),
            'PAPER_SELECTION_FEE_BINDING')
    binding.update(paper_application_sha256=trusted_application_sha256,
        calendar_sha256=app['calendar_sha256'], account_genesis_sha256=app['account_genesis_sha256'],
        source_admission_sha256=app['admitted_source_hashes_sha256'],
        selector_profile=PROFILE_ID,selection_method=VERSION,continuous_iterations=32)
    return dict(binding=binding,input_id=sha256(canonical(binding)).hexdigest())


def select_paper_target(**arguments):
    inputs=build_paper_target_inputs(**arguments)
    binding=inputs['binding']
    result=enhanced_search(**deepcopy(binding['search_arguments']))
    quantities=validate_result(result,binding['search_arguments'])
    payload=dict(schema='PAPER_CONTINUOUS32_TARGET_DECISION_V1',input_id=inputs['input_id'],
                 target_month=binding['valuation_date'][:7], input_binding=binding,
                 search_result=result,target_quantities=quantities)
    return dict(status='TARGET_READY' if quantities is not None else 'SEARCH_INCOMPLETE',
        payload=payload,decision_id=sha256(canonical(payload)).hexdigest(),core_calls=1,
        source_bytes_verified=True,source_authenticated=False,full_pit_verified=False,
        orders_created=False,account_mutated=False,target_published=False,
        application_scope=SCOPE,automatic_acceptance_allowed=False)


def verify_paper_target(result, **arguments):
    """Replay saved target against exact paper book and admitted source bytes.

    Uses the original result validator, never reruns the base search. This is
    not publication or authority to accept an order.
    """
    require(set(result)=={'status','payload','decision_id','core_calls','source_bytes_verified',
            'source_authenticated','full_pit_verified','orders_created','account_mutated',
            'target_published','application_scope','automatic_acceptance_allowed'} and
            result['source_authenticated'] is False and result['full_pit_verified'] is False
            and result['source_bytes_verified'] is True and type(result['core_calls']) is int
            and result['core_calls']==1, 'PAPER_TARGET_EVIDENCE_FLAGS_CHANGED')
    inputs=build_paper_target_inputs(**arguments)
    payload=result['payload']
    require(result['decision_id']==sha256(canonical(payload)).hexdigest()
            and payload['schema']=='PAPER_CONTINUOUS32_TARGET_DECISION_V1'
            and payload['input_id']==inputs['input_id'] and payload['input_binding']==inputs['binding']
            and payload['target_month']==inputs['binding']['valuation_date'][:7],
            'PAPER_TARGET_BINDING_CHANGED')
    quantities=validate_result(payload['search_result'],inputs['binding']['search_arguments'])
    require(quantities==payload['target_quantities'] and result['status']==
            ('TARGET_READY' if quantities is not None else 'SEARCH_INCOMPLETE') and
            result['application_scope']==SCOPE and result['automatic_acceptance_allowed'] is False
            and result['target_published'] is False and result['account_mutated'] is False
            and result['orders_created'] is False, 'PAPER_TARGET_RESULT_CHANGED')
    return dict(status='VERIFIED_SELECTION_ONLY',target_id=result['decision_id'],
                account_id=inputs['binding']['account_id'],account_revision=inputs['binding']['account_revision'],
                target_month=payload['target_month'],target_quantities=deepcopy(quantities),
                application_scope=SCOPE,orders_created=False,target_published=False)

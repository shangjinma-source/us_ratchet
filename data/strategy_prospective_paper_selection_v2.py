"""Static registered-paper admission to the shared current target selector."""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v2 import document,require,stamp,sessions,SCOPE
from backtest.current_strategy_prospective_paper_book_v2 import replay,_context
from backtest.current_strategy_paper_slice_v1 import _projection
from data.strategy_paper_continuous32_selection_v1 import CODE_PATHS as ORIGINAL_SELECTION_PINS
from data.strategy_paper_target_common_v1 import build_target_inputs_core,verify_target_core
from data.strategy_paper_exact_target_v2 import select_target_core

CODE_PATHS=set(ORIGINAL_SELECTION_PINS)|{
    'data/strategy_paper_target_common_v1.py','data/strategy_prospective_paper_selection_v2.py',
    'backtest/current_strategy_prospective_paper_book_v2.py','data/strategy_paper_application_descriptor_v2.py',
    'data/strategy_paper_exact_target_v2.py','backtest/paper_exact_integer_quantity_search_v2.py'}


def build_prospective_target_inputs(*,book,authority,admitted_decisions,source_review_bytes,
        trusted_source_review_sha256,source_package,manifest_path,marks_path,unit_review_path,
        now,maximum_mark_age_seconds,admitted_settlements=None):
    app=_context(authority,now)
    require(CODE_PATHS<=set(app['code_sha256']),'PROSPECTIVE_SELECTOR_CODE_SCOPE')
    verified=replay(book,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
    state=_projection(verified)
    state.update(holdings_revision=state['revision'],total_uninvested_cash=state['cash'],
        reserved_cash=str(Fraction(state['cash'])-Fraction(state['available_cash'])),
        orders={o['order_id']:dict(o,status='OPEN') for o in state['pending_orders']})
    review=document(source_review_bytes,trusted_source_review_sha256)
    require(review.get('schema')=='PROSPECTIVE_PAPER_SOURCE_ADMISSION_V1' and review.get('scope')==SCOPE and
        review.get('descriptor_sha256')==book['descriptor_sha256'] and review.get('account_id')==book['account_id'] and
        review.get('account_revision')==book['revision'] and review.get('source_sha256')==source_package['source_hashes'] and
        review.get('source_authenticated') is False and review.get('coverage_complete') is False,
        'PROSPECTIVE_SELECTION_SOURCE_BINDING')
    require(stamp(book['last_available_at'])<=stamp(review['available_at'])<=stamp(now),
        'PROSPECTIVE_SELECTION_SOURCE_CLOCK')
    require(all(source_package['source_hashes'].get(p)==app['code_sha256'][p] for p in CODE_PATHS),
        'PROSPECTIVE_SELECTION_SOURCE_CODE')
    calendar_bytes=authority['descriptor_arguments']['calendar_bytes']
    rows=sessions(calendar_bytes,app['calendar_sha256'])
    require(any(stamp(r['open'])<=stamp(now)<stamp(r['close']) for r in rows),'PAPER_SELECTION_OUTSIDE_SESSION')
    calendar=json.loads(calendar_bytes)
    # This validated internal context is not a fixture application or permission.
    context=dict(fee_bps=app['policy']['fee_bps'],calendar_sha256=app['calendar_sha256'],
        account_genesis_sha256=sha256(canonical(verified['application'])).hexdigest(),
        admitted_source_hashes_sha256=sha256(canonical(source_package['source_hashes'])).hexdigest())
    result=build_target_inputs_core(book=verified,app=context,state=state,calendar=calendar,
        trusted_application_sha256=book['descriptor_sha256'],source_package=source_package,
        manifest_path=manifest_path,marks_path=marks_path,unit_review_path=unit_review_path,
        now=now,maximum_mark_age_seconds=maximum_mark_age_seconds)
    result['binding'].update(registration_sha256=book['registration_sha256'],
        source_review_sha256=trusted_source_review_sha256,formal_application_scope=SCOPE)
    result['input_id']=sha256(canonical(result['binding'])).hexdigest()
    return result


def select_prospective_target(*,clock,**arguments):
    original=deepcopy(arguments);started=stamp(clock())
    require(0 <= (started-stamp(arguments['now'])).total_seconds() <= arguments['maximum_mark_age_seconds'],
            'PROSPECTIVE_SELECTION_FRESH_CLOCK')
    result=select_target_core(build_prospective_target_inputs(**arguments),scope=SCOPE)
    # Full code/authority replay occurs before the last cheap live clock gate.
    app=_context(arguments['authority'],stamp(clock()))
    rows=sessions(arguments['authority']['descriptor_arguments']['calendar_bytes'],app['calendar_sha256'])
    require(arguments==original,'PROSPECTIVE_SELECTION_INPUT_CHANGED')
    finished=stamp(clock());require(finished>=started,'PROSPECTIVE_SELECTION_CLOCK_ROLLBACK')
    marks=result['payload']['input_binding']['marks']
    require(all(0<=(finished-stamp(m['observed_at'])).total_seconds()<=arguments['maximum_mark_age_seconds']
        for m in marks.values()),'PROSPECTIVE_SELECTION_EXPIRED')
    require(any(stamp(r['open'])<=started<=finished<stamp(r['close']) for r in rows),'PROSPECTIVE_SELECTION_SESSION_ENDED')
    result['payload']['computation_finished_at']=finished.isoformat()
    result['decision_id']=sha256(canonical(result['payload'])).hexdigest()
    tail=stamp(clock());require(tail>=finished,'PROSPECTIVE_SELECTION_CLOCK_ROLLBACK')
    require(all((tail-stamp(m['observed_at'])).total_seconds()<=arguments['maximum_mark_age_seconds']
        for m in marks.values()) and any(stamp(r['open'])<=started<=tail<stamp(r['close']) for r in rows),
        'PROSPECTIVE_SELECTION_EXPIRED')
    return result


def verify_prospective_target(result,**arguments):
    finished=stamp(result['payload']['computation_finished_at'])
    require(finished>=stamp(arguments['now']) and all(
        0<=(finished-stamp(m['observed_at'])).total_seconds()<=arguments['maximum_mark_age_seconds']
        for m in result['payload']['input_binding']['marks'].values()),'PROSPECTIVE_SELECTION_COMPLETION_TIME')
    return verify_target_core(result,build_prospective_target_inputs(**arguments),scope=SCOPE)


def verify_empty_paper_target(*,book,authority,admitted_decisions,admitted_settlements,
                            selection_result,selection_arguments):
    require(selection_arguments['authority']==authority,'PAPER_EMPTY_TARGET_AUTHORITY')
    selected=verify_prospective_target(selection_result,**selection_arguments)
    current=replay(book,authority=authority,admitted_decisions=admitted_decisions,
                   admitted_settlements=admitted_settlements)
    previous=replay(selection_arguments['book'],authority=authority,
        admitted_decisions=selection_arguments['admitted_decisions'],
        admitted_settlements=selection_arguments.get('admitted_settlements'))
    require(previous['descriptor_sha256']==current['descriptor_sha256'] and
        previous['registration_sha256']==current['registration_sha256'] and
        previous['operations']==current['operations'][:len(previous['operations'])],
        'PAPER_EMPTY_TARGET_ANCESTRY')
    require(not any(selected['target_quantities'].values()) and not any(current['shares'].values()) and
        not any(order['closed'] is None for order in current['orders'].values()),'PAPER_EMPTY_TARGET_HAS_EXPOSURE')
    return dict(status='HOLD_EMPTY_TARGET',account_revision=current['revision'],
                target_id=selected['target_id'],orders_created=False)


def prospective_target_training_context(*, selection_result, selection_arguments):
    """Execution uses the training bound to the saved target, not startup defaults."""
    verify_prospective_target(selection_result, **selection_arguments)
    binding=selection_result['payload']['input_binding']
    package=selection_arguments['source_package']
    review=json.loads(package['files'][selection_arguments['unit_review_path']])
    historical=binding['historical_search_arguments']
    manifest_hash=package['source_hashes'][selection_arguments['manifest_path']]
    historical_hash=sha256(canonical(historical)).hexdigest()
    require(review['training_manifest_sha256']==manifest_hash and
            review['historical_search_arguments_sha256']==historical_hash,
            'PAPER_TARGET_TRAINING_BINDING')
    return dict(training_manifest_sha256=manifest_hash,
        historical_search_arguments_sha256=historical_hash,
        training_closed_at=review['training_closed_at'],historical_price_basis=historical['price_basis'])

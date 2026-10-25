"""Formal paper decision producer over original daily/limit/difference rules.

This implementation is an isolated in-memory end-to-end integration. Its private
cap store is temporary, not a registered durable execution service.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from core.strategy_account_ledger import canonical
from core.strategy_account_difference import build_strategy_difference
from data.strategy_paper_application_descriptor_v1 import require,stamp,document,sessions,SCOPE
from backtest.current_strategy_prospective_paper_book_v1 import replay,project,_context,DECISION_SCHEMA
from data.strategy_prospective_paper_daily_v1 import verify_prospective_daily,CODE_PATHS as DAILY_PINS
from data.strategy_paper_execution_preview_v1 import _local_import_closure,BUY_WAIT_ERRORS
from data.strategy_paper_execution_caps_v1 import PaperExecutionCaps
from data.strategy_prospective_paper_cap_store_v1 import ProspectivePersistentCaps
from data.strategy_execution_limits_common_v1 import _build_execution_limits_core
from data.strategy_daily_target_gate import resolve_daily_target

CODE_PATHS=_local_import_closure(set(DAILY_PINS)|{
    'data/strategy_prospective_paper_decision_v1.py','data/strategy_execution_limits_common_v1.py',
    'data/strategy_paper_execution_caps_v1.py','data/strategy_paper_execution_preview_v1.py',
    'data/strategy_daily_target_gate.py'})


class ProspectiveTemporaryCaps(PaperExecutionCaps):
    storage_kind='TEMPORARY_ISOLATED_INTEGRATION_ONLY'
    def __init__(self,*,book,authority,admitted_decisions,clock,admitted_settlements=None):
        verified=replay(book,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
        self.account_id=verified['account_id'];self.genesis=verified['registration_sha256']
        self.namespace_id='prospective-temp-cap:'+str(uuid4());self.clock=clock
        self.directory=TemporaryDirectory(prefix='ratchet-prospective-cap-')
        self.stores={};self.proofs=[];self.closed=False

    def validate(self,book):
        require(not self.closed and book['account_id']==self.account_id and
            book['registration_sha256']==self.genesis,'PROSPECTIVE_CAP_BINDING')


def produce_prospective_decision(*,daily_arguments,execution_admission_bytes,
        trusted_execution_admission_sha256,market_capture,unit_review,caps,clock,
        sell_market_capture=None,sell_unit_review=None):
    supplied_sources=(market_capture,unit_review,sell_market_capture,sell_unit_review)
    source_snapshot=deepcopy(supplied_sources)
    market_capture,unit_review,sell_market_capture,sell_unit_review=source_snapshot
    original=deepcopy(daily_arguments);started=stamp(clock());arguments=deepcopy(original)
    arguments['now']=started.isoformat()
    authority=arguments['authority'];app=_context(authority,started)
    require(CODE_PATHS<=set(app['code_sha256']),'PROSPECTIVE_DECISION_CODE_SCOPE')
    book=replay(arguments['book'],authority=authority,admitted_decisions=arguments['admitted_decisions'],
        admitted_settlements=arguments.get('admitted_settlements'))
    require(type(caps) in (ProspectiveTemporaryCaps,ProspectivePersistentCaps),'PROSPECTIVE_CAP_REQUIRED');caps.validate(book)
    state=project(book,authority=authority,admitted_decisions=arguments['admitted_decisions'],
        admitted_settlements=arguments.get('admitted_settlements'))
    state['orders']={o['order_id']:dict(o,status='OPEN') for o in state['pending_orders']}
    daily=verify_prospective_daily(**arguments)
    if daily['status']!='DAILY_SIGNAL_READY':
        return dict(status=daily['status'],decision_bytes=None,new_orders=[],orders_created=False)
    signal=daily['signal'];target=arguments['selection_result']
    receipt=document(execution_admission_bytes,trusted_execution_admission_sha256)
    require(receipt.get('schema')=='PROSPECTIVE_PAPER_EXECUTION_ADMISSION_V1' and receipt.get('scope')==SCOPE and
        receipt.get('descriptor_sha256')==book['descriptor_sha256'] and receipt.get('account_revision')==book['revision'] and
        receipt.get('account_id')==book['account_id'] and receipt.get('target_id')==daily['target_id'] and
        receipt.get('daily_evidence_id')==signal['evidence_id'] and receipt.get('cap_namespace_id')==caps.namespace_id and
        receipt.get('source_sha256')==market_capture['source_hashes'] and
        receipt.get('unit_review_sha256')==sha256(canonical(unit_review)).hexdigest(), 'PROSPECTIVE_EXECUTION_ADMISSION')
    require(stamp(book['last_available_at'])<=stamp(receipt['available_at'])<=started,'PROSPECTIVE_EXECUTION_ADMISSION_TIME')
    gate=resolve_daily_target(account_id=book['account_id'],account_revision=book['revision'],target_id=daily['target_id'],
        target_month=target['payload']['target_month'],monthly_quantities=target['payload']['target_quantities'],
        strategy_shares=state['shares'],available_cash=state['available_cash'],pending_orders=state['pending_orders'],
        now=started.isoformat(),expected_policy_id=signal['policy_id'],signal=signal)
    if gate['status']!='DAILY_TARGET_READY' or any(r['reason']=='PENDING_RECONCILIATION_REQUIRED' for r in gate['rows']):
        return dict(status='WAIT_PENDING_OR_DAILY_TARGET',decision_bytes=None,new_orders=[],orders_created=False)
    effective=gate['effective_target_quantities'];execution=deepcopy(effective);failure=None;proof_start=len(caps.proofs)
    try:
        evidence=_build_execution_limits_core(state=state,target_quantities=execution,market_capture=market_capture,
            unit_review=unit_review,cap_store=caps,now=stamp(clock()).isoformat())
    except ValueError as error:
        if str(error) not in BUY_WAIT_ERRORS:raise
        failure=dict(reason=str(error),source_sha256=deepcopy(market_capture['source_hashes']))
        execution={sid:min(q,state['shares'].get(sid,0)) for sid,q in effective.items()}
        if not any(q<state['shares'].get(sid,0) for sid,q in execution.items()):
            return dict(status='WAIT_BUY_MINUTE_DATA',decision_bytes=None,new_orders=[],buy_data_failure=failure,orders_created=False)
        require(sell_market_capture is not None and sell_unit_review is not None and
            receipt.get('sell_source_sha256')==sell_market_capture['source_hashes'] and
            receipt.get('sell_unit_review_sha256')==sha256(canonical(sell_unit_review)).hexdigest(),
            'PROSPECTIVE_SELL_ADMISSION_REQUIRED')
        evidence=_build_execution_limits_core(state=state,target_quantities=execution,market_capture=sell_market_capture,
            unit_review=sell_unit_review,cap_store=caps,now=stamp(clock()).isoformat())
    finished=stamp(clock())
    require(finished>=started,'PROSPECTIVE_CLOCK_ROLLBACK')
    difference=build_strategy_difference(account_id=book['account_id'],account_revision=book['revision'],
        holdings_revision=book['revision'],cash_confirmed_for_holdings_revision=book['revision'],
        cash_balance=state['cash'],cash_basis='TOTAL_UNINVESTED',strategy_shares=state['shares'],legacy_shares={},
        pending_orders=state['pending_orders'],target_quantities=execution,now=finished.isoformat(),
        maximum_mark_age_seconds=120,fee_bps=app['policy']['fee_bps'],**evidence)
    require(failure is None or all(o['side']=='SELL' for o in difference['new_orders']),'PROSPECTIVE_SELL_SUBSET')
    _context(authority,finished)
    rows=sessions(authority['descriptor_arguments']['calendar_bytes'],app['calendar_sha256'])
    require(daily_arguments==original and supplied_sources==source_snapshot,'PROSPECTIVE_INPUT_CHANGED')
    final=stamp(clock());require(final>=finished,'PROSPECTIVE_CLOCK_ROLLBACK')
    quote_until=min([stamp(signal['valid_until'])]+[stamp(ref['reference_valid_until']) for ref in evidence['limits'].values()])
    require(stamp(signal['valid_from'])<=final<quote_until,'PROSPECTIVE_DECISION_EXPIRED')
    if not difference['new_orders']:
        return dict(status='HOLD',decision_bytes=None,new_orders=[],difference=difference,orders_created=False)
    row=next((r for r in rows if stamp(r['decision_at'])<=final<stamp(r['decision_until'])),None)
    require(row is not None and app['plan']['first_session']['date']<=row['date']<=app['plan']['terminal_session']['date'],
        'PROSPECTIVE_DECISION_WINDOW')
    valid_until=min(stamp(signal['valid_until']),stamp(row['decision_until']),
        *(stamp(ref['reference_valid_until']) for ref in evidence['limits'].values()))
    require(stamp(signal['valid_from'])<=final<valid_until,'PROSPECTIVE_DECISION_EXPIRED')
    decision=dict(schema=DECISION_SCHEMA,scope=SCOPE,status='VERIFIED_PROSPECTIVE_PAPER_EXECUTION_DECISION',
        descriptor_sha256=book['descriptor_sha256'],registration_sha256=book['registration_sha256'],
        account_id=book['account_id'],account_revision=book['revision'],target_id=daily['target_id'],session_date=row['date'],
        available_at=final.isoformat(),valid_until=valid_until.isoformat(),fee_bps=app['policy']['fee_bps'],
        cancel_before_recalculate=difference['cancel_before_recalculate'],new_orders=difference['new_orders'],
        effective_target_quantities=effective,execution_quantities=execution,daily_evidence_id=signal['evidence_id'],
        execution_admission_sha256=trusted_execution_admission_sha256,source_sha256=deepcopy(market_capture['source_hashes']),
        cap_namespace_id=caps.namespace_id,cap_proofs=deepcopy(caps.proofs[proof_start:]),
        cap_storage=caps.storage_kind,buy_data_failure=failure,
        limits=evidence['limits'],orders_created=False)
    raw=canonical(decision)
    result=dict(status=decision['status'],decision_bytes=raw,decision_sha256=sha256(raw).hexdigest(),
        decision=decision,new_orders=deepcopy(decision['new_orders']),orders_created=False)
    require(daily_arguments==original and supplied_sources==source_snapshot,'PROSPECTIVE_INPUT_CHANGED')
    tail=stamp(clock())
    require(tail>=final,'PROSPECTIVE_CLOCK_ROLLBACK')
    require(tail<valid_until,'PROSPECTIVE_DECISION_EXPIRED')
    return result

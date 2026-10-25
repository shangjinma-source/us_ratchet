"""Default-off saved-frontier research preview; no server or production mount.

The normal monthly journal lifecycle stores the unchanged saved decision. A
separate proposal is admitted by the complete-source reviewer and risk reader,
then reaches the existing execution bridge and cash difference engine. This is
an independent service, not a claim of DailyCompositionV7 integration.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from core.saved_monthly_frontier_proposal import build_frontier_proposal
from core.strategy_account_difference import number, timestamp
from core.strategy_account_ledger import canonical, require
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.saved_frontier_policy_archive import (
    _research_root, archive_saved_frontier_policy, read_saved_frontier_policy,
)
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_preview import preview_scoped_account
from data.strategy_daily_execution_bridge import DailyExecutionBridge
from data.strategy_daily_mixed_execution_bridge import DailyMixedExecutionBridge
from data.strategy_daily_session_capture import reject_links
from data.strategy_daily_target_gate import resolve_daily_target
from data.strategy_monthly_target_service import LIFECYCLE_PATHS, StrategyMonthlyTargetService


def _inside(root, value):
    path = Path(value).absolute()
    reject_links(path)
    require(path.resolve().is_relative_to(root) and path.resolve() != root,
            'FRONTIER_PIPELINE_ISOLATED_PATH_REQUIRED')
    return path


def run_isolated_saved_frontier_pipeline(*, research_root, account_store, saved_target,
        source_files, risk_source_path, risk_source_sha256, review_bytes,
        trusted_review_sha256, daily_files, execution_provider, clock,
        previous_targets=(), authorized_monthly_reset=None, enabled=False):
    """Explicit research-only invocation; never select, optimize or record orders.

    A trusted caller supplies a saved decision, independently fixed review hash,
    complete source bytes and an offline evidence provider. All databases and
    execution artifacts must be beneath the explicit existing tmp workspace.
    """
    require(type(enabled) is bool, 'FRONTIER_ENABLED_BOOLEAN')
    if not enabled:
        return dict(status='ISOLATED_FRONTIER_PIPELINE_DISABLED', new_orders=[],
                    production_admitted=False, orders_created=False)
    from data.saved_frontier_cap_exit_reader import (
        clone_monthly_risk_store, project_saved_frontier_cap_exit,
    )
    root = _research_root(research_root)
    require(type(account_store) is StrategyAccountStore, 'FRONTIER_PIPELINE_ACCOUNT_STORE_REQUIRED')
    _inside(root, account_store.path)
    require(type(execution_provider) is StrategyAccountEvidenceProvider,
            'FRONTIER_PIPELINE_PROVIDER_REQUIRED')
    _inside(root, execution_provider.root)
    _inside(root, execution_provider.output)
    _inside(root, risk_source_path)
    target = deepcopy(saved_target)
    sources = source_files.copy()
    daily_sources = daily_files.copy()
    original_account = account_store.read()
    account_bytes = account_store.path.read_bytes()
    proposal = build_frontier_proposal(target=target)
    require(target['payload']['account_id'] == original_account['account_id'],
            'FRONTIER_PIPELINE_ACCOUNT_BINDING')
    pins = target['payload']['runtime_pins']
    require(LIFECYCLE_PATHS <= set(pins), 'MONTHLY_LIFECYCLE_PINS_REQUIRED')

    run_root = root / ('pipeline-' + uuid4().hex)
    run_root.mkdir()
    created = timestamp(target['payload']['created_at'])
    # Reconstruct the actual recorded revision at the original selection. Later
    # cash confirmations/cancellations remain only in the current preview state.
    selection_store = StrategyAccountStore(run_root / 'selection-account.sqlite3', clock=lambda: created)
    selection_store.initialize(original_account['account_id'], operation_id='saved-selection-snapshot')
    expected = target['payload']['request']['expected_revision']
    for row in original_account['events']:
        if selection_store.read()['revision'] == expected:
            break
        selection_store.append(deepcopy(row['payload']), expected_revision=selection_store.read()['revision'])
    selection_state = selection_store.read()
    require(selection_state['revision'] == expected, 'FRONTIER_PIPELINE_SELECTION_REVISION_MISSING')
    original_binding = target['payload']['decision']['payload']['input_binding']
    require(original_binding['account_revision'] == expected,
            'FRONTIER_PIPELINE_SELECTION_REVISION_BINDING')
    require(original_binding['strategy_shares'] == selection_state['shares']
            and original_binding['holdings_revision'] == selection_state['holdings_revision']
            and number(original_binding['total_uninvested_cash'])
                == number(selection_state['total_uninvested_cash']),
            'FRONTIER_PIPELINE_SELECTION_ACCOUNT_FACTS')
    expected_context = dict(
        pending_orders=[deepcopy(o) for o in selection_state['orders'].values() if o['status'] == 'OPEN'],
        reserved_cash=selection_state['reserved_cash'], reserved_shares=selection_state['reserved_shares'],
        available_cash=selection_state['available_cash'],
        cash_confirmation_revision=selection_state['cash_confirmed_for_holdings_revision'],
        sell_proceeds_available=False)
    require(original_binding['execution_context'] == expected_context,
            'FRONTIER_PIPELINE_SELECTION_EXECUTION_CONTEXT')
    original_domain = (set(original_binding['historical_search_arguments']['prices'])
        | {sid for sid, quantity in selection_state['shares'].items() if quantity}
        | {order['security_id'] for order in selection_state['orders'].values() if order['status'] == 'OPEN'})
    require(set(original_binding['historical_search_arguments']['prices'])
                == set(original_binding['historical_search_arguments']['metadata'])
                == set(original_binding['search_arguments']['prices'])
            and set(original_binding['marks']) == original_domain
            and selection_state['cash_confirmation_valid'] and selection_state['execution_ready'],
            'FRONTIER_PIPELINE_ORIGINAL_MARK_DOMAIN')

    class SavedSelection:
        store = selection_store
        fees = proposal['payload']['fee_bps']

        def _pins(self):
            for name, digest in pins.items():
                require(name in sources and sha256(sources[name]).hexdigest() == digest,
                        'FRONTIER_PIPELINE_SOURCE_CHANGED')
            executing_root = Path(__file__).resolve().parents[1]
            for name in LIFECYCLE_PATHS:
                require(sha256((executing_root / name).read_bytes()).hexdigest() == pins[name],
                        'FRONTIER_PIPELINE_LIFECYCLE_CHANGED')

        def select(self):
            self._pins()
            require(selection_store.read() == selection_state, 'ACCOUNT_CHANGED_DURING_TARGET')
            self.current = (deepcopy(target['payload']['decision']), None, deepcopy(selection_state))
            return dict(status='READY', core_calls=0)

    selection = SavedSelection()
    selection.pins = deepcopy(pins)
    targets = StrategyMonthlyTargetStore(run_root / 'monthly-targets.sqlite3')
    for previous in previous_targets:
        require(targets.append(deepcopy(previous['payload'])) == previous,
                'FRONTIER_PIPELINE_PRIOR_TARGET_CHANGED')
    monthly = StrategyMonthlyTargetService(selection_service=selection,
        target_store=targets, execution_provider=execution_provider.execution, clock=lambda: created)
    generated = monthly.generate(**target['payload']['request'])
    require(generated == target, 'FRONTIER_PIPELINE_MONTHLY_TARGET_CHANGED')
    archive_saved_frontier_policy(research_root=root, target=generated, proposal=proposal,
                                  source_files=sources, enabled=True)

    def unchanged():
        selection._pins()
        require(account_store.read() == original_account
                and account_store.path.read_bytes() == account_bytes,
                'ACCOUNT_CHANGED_DURING_PREVIEW')
        require(targets.current() == target, 'TARGET_CHANGED_DURING_PREVIEW')
        archived = read_saved_frontier_policy(research_root=root, target_id=target['target_id'])
        require(archived['target'] == target and archived['proposal'] == proposal,
                'FRONTIER_PIPELINE_PROPOSAL_CHANGED')
        now = clock()
        require(isinstance(now, datetime) and now.utcoffset() is not None
                and now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
                    == target['payload']['target_month'], 'MONTHLY_TARGET_REQUIRED')
        require(sha256(Path(risk_source_path).read_bytes()).hexdigest() == risk_source_sha256,
                'FRONTIER_PIPELINE_RISK_SEED_CHANGED')

    unchanged()
    clone = clone_monthly_risk_store(research_root=root, source_path=risk_source_path,
        source_sha256=risk_source_sha256, clone_name='risk-' + run_root.name + '.sqlite3')
    risk_path = clone['path'] if type(clone) is dict else clone
    admitted = project_saved_frontier_cap_exit(research_root=root, risk_path=risk_path,
        target_id=target['target_id'], state=deepcopy(original_account),
        review_bytes=review_bytes, trusted_review_sha256=trusted_review_sha256,
        files=daily_sources, now=clock().isoformat(),
        authorized_monthly_reset=authorized_monthly_reset, enabled=True)
    unchanged()
    signal = deepcopy(admitted['signal'])
    require(signal.get('proposal_id') == proposal['proposal_id'],
            'FRONTIER_PIPELINE_SIGNAL_PROPOSAL_BINDING')
    require(signal.get('evidence_archive') == admitted['evidence_archive']
            and bool(admitted['evidence_archive']), 'DAILY_ARCHIVE_REQUIRED')
    effective = signal['effective_target_quantities']
    # The original raw monthly target remains untouched. The independent gate
    # receives the explicitly reviewed proposal domain, including risk zeroes.
    baseline = {sid: proposal['payload']['proposed_target_quantities'].get(sid, 0)
                for sid in effective}
    require({sid for sid, q in proposal['payload']['proposed_target_quantities'].items() if q}
            <= set(effective),
            'FRONTIER_PIPELINE_PROPOSAL_DOMAIN')
    now = clock()
    gate = resolve_daily_target(account_id=original_account['account_id'],
        account_revision=original_account['revision'], target_id=target['target_id'],
        target_month=target['payload']['target_month'], monthly_quantities=baseline,
        strategy_shares=original_account['shares'], available_cash=original_account['available_cash'],
        pending_orders=[o for o in original_account['orders'].values() if o['status'] == 'OPEN'],
        now=now.isoformat(), expected_policy_id='SAVED_FRONTIER_CAP50_EXIT20_ISOLATED_V1', signal=signal)
    unchanged()
    result = dict(status='WAIT', detail_status=gate['status'], daily_gate=gate,
        new_orders=[], reference_quotes={}, waiting_cash=[])
    rows = gate['rows']
    pending = any(row['reason'] == 'PENDING_RECONCILIATION_REQUIRED' for row in rows)
    if gate['status'] == 'DAILY_TARGET_READY' and pending:
        result['detail_status'] = 'WAIT_PENDING_RECONCILIATION'
    elif gate['status'] == 'DAILY_TARGET_READY':
        require(original_account['cash_confirmation_valid'], 'CASH_RECONFIRMATION_REQUIRED')
        zero_cash = number(original_account['available_cash']) == 0
        held = original_account['shares']
        quantities = ({sid: min(held.get(sid, 0), q) for sid, q in effective.items()}
                      if zero_cash else deepcopy(effective))
        waiting = ([dict(security_id=sid, quantity=q-held.get(sid, 0),
                         reason='WAIT_CASH_NO_SELL_PROCEEDS_ASSUMED')
                    for sid, q in effective.items() if q > held.get(sid, 0)] if zero_cash else [])
        if all(q == held.get(sid, 0) for sid, q in quantities.items()):
            result.update(status='WAIT' if waiting else 'HOLD',
                          detail_status='WAIT_EXECUTION_ELIGIBILITY' if waiting else 'HOLD',
                          waiting_cash=waiting)
        else:
            bridge_type = DailyMixedExecutionBridge if zero_cash else DailyExecutionBridge
            bridge = bridge_type(base_target=target, execution_provider=execution_provider.execution,
                                 validate_sources=unchanged, signal=signal)
            arguments = dict(execution_quantities=quantities) if zero_cash else {}
            evidence = bridge(deepcopy(original_account), deepcopy(effective), now, **arguments)
            finished = clock()
            require(finished >= now, 'SERVER_CLOCK_MOVED_BACKWARDS')
            require(timestamp(signal['valid_from']) <= finished < timestamp(signal['valid_until']),
                    'DAILY_SIGNAL_EXPIRED_DURING_PREVIEW')
            for limit in evidence['limits'].values():
                require(finished < timestamp(limit['reference_valid_until']), 'REQUOTE_REQUIRED')
            difference = preview_scoped_account(state=original_account, legacy_shares={},
                target_quantities=quantities, marks=evidence['marks'], limits=evidence['limits'],
                now=finished.isoformat(), maximum_mark_age_seconds=120,
                fee_bps=proposal['payload']['fee_bps'])
            if zero_cash:
                require(all(o['side'] == 'SELL' for o in difference['new_orders']),
                        'DAILY_SELL_ONLY_VIOLATION')
            pending_cash = waiting if zero_cash else difference['waiting_cash']
            ready = bool(difference['new_orders'])
            result.update(status='READY' if ready else 'WAIT' if pending_cash else 'HOLD',
                detail_status='ISOLATED_CONDITIONAL_PREVIEW_READY' if ready else
                    'WAIT_EXECUTION_ELIGIBILITY' if pending_cash else 'HOLD',
                new_orders=difference['new_orders'], difference=difference,
                reference_quotes=evidence['limits'] if ready else {},
                waiting_cash=pending_cash,
                execution_binding=bridge.last_binding,
                effective_target_quantities=deepcopy(effective), execution_quantities=quantities)
    unchanged()
    returned_at = clock()
    require(returned_at >= now, 'SERVER_CLOCK_MOVED_BACKWARDS')
    require(timestamp(signal['valid_from']) <= returned_at < timestamp(signal['valid_until']),
            'DAILY_SIGNAL_EXPIRED_DURING_PREVIEW')
    for quote in result['reference_quotes'].values():
        require(returned_at < timestamp(quote['reference_valid_until']), 'REQUOTE_REQUIRED')
    require(result['status'] == 'READY' or not result['new_orders'], 'WAIT_CANNOT_CONTAIN_ORDERS')
    for order in result['new_orders']:
        order.update(source_target_id=target['target_id'], proposal_id=proposal['proposal_id'])
    return dict(result, readiness_scope='ISOLATED_RESEARCH_PREVIEW_ONLY',
        policy_id='SAVED_FRONTIER_CAP50_EXIT20_ISOLATED_V1',
        source_target_id=target['target_id'], proposal_id=proposal['proposal_id'],
        account_revision=original_account['revision'], risk_projection=admitted,
        production_admitted=False, daily_composition_v7_integrated=False,
        optimizer_calls=0, orders_created=False, account_mutated=False,
        original_target_mutated=False, isolated_monthly_target_created=True,
        monthly_target_path=str(targets.path))

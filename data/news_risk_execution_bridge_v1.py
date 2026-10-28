"""Server-owned HOLD-only news projection. Quotes are real; orders remain proposals.

The original monthly decision and original daily risk signal remain unchanged.
Only the independent execution projection changes; no ledger write is performed.
"""
from contextlib import nullcontext
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4
from fractions import Fraction
import json

from core.strategy_account_ledger import canonical
from core.news_investment_review_v1 import integer, moment, require
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_preview import preview_scoped_account
from data.strategy_daily_target_gate import resolve_daily_target
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class NewsHoldExecutionBridge:
    """Authenticate the real base decision before projecting lower news targets."""
    def __init__(self, *, base_target, execution_provider, validate_sources, signal, proposal):
        require(getattr(execution_provider, '__func__', None) is StrategyAccountEvidenceProvider.execution,
                'NEWS_PROVIDER_INTERFACE_REQUIRED')
        self.provider = execution_provider.__self__
        self.base, self.signal, self.proposal = deepcopy((base_target, signal, proposal))
        self.validate_sources = validate_sources

    def __call__(self, state, targets, now):
        self.validate_sources()
        base, signal, proposal, expected, before = deepcopy((self.base, self.signal, self.proposal, targets, state))
        require(set(targets) == set(signal['effective_target_quantities']), 'NEWS_PROJECTION_DOMAIN')
        require(all(type(q) is int and 0 <= q <= signal['effective_target_quantities'][sid]
                    and q <= state['shares'].get(sid, 0) for sid, q in targets.items()), 'NEWS_SELL_ONLY_REQUIRED')
        lineage = dict(schema='NEWS_HOLD_EXECUTION_PROJECTION_V1', base_target_id=base['target_id'],
                       base_decision_id=base['payload']['decision']['decision_id'],
                       account_revision=state['revision'], original_signal=signal,
                       review_id=proposal['review_id'], review_sha256=digest(proposal),
                       projected_target_quantities=expected, original_signal_mutated=False)
        raw = canonical(lineage)
        provider = self.provider
        directory = provider.output / ('news-hold-' + uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / 'news-binding.json'
        with path.open('xb') as stream:
            stream.write(raw)

        class ExecutionView:
            output = directory
            def __getattr__(self, name):
                return getattr(provider, name)

            def _assemble(self, verified_state, package, historical, *, target_quantities, execution_only):
                require(target_quantities == base['payload']['target_quantities'], 'NEWS_BASE_QUANTITIES_CHANGED')
                require({sid for sid, q in targets.items() if q} <= set(historical['metadata']), 'NEWS_PROJECTION_DOMAIN')
                package = deepcopy(package)
                name = str(path)
                require(name not in package['files'], 'NEWS_BINDING_COLLISION')
                package['files'][name] = raw
                package['source_hashes'][name] = sha256(raw).hexdigest()
                package['documents']['news_execution_binding'] = name
                quantities = {sid: q for sid, q in targets.items() if q}
                saved = deepcopy(quantities)
                result = StrategyAccountEvidenceProvider._assemble(self, verified_state, package, historical,
                    target_quantities=quantities, execution_only=execution_only)
                require(saved == quantities, 'NEWS_PROVIDER_MUTATED_TARGET')
                return result

        result = StrategyAccountEvidenceProvider.execution(ExecutionView(), state, base, now)
        require(state == before and base == self.base and targets == expected, 'NEWS_PROVIDER_MUTATED_INPUT')
        self.validate_sources()
        self.binding = dict(path=str(path), sha256=sha256(raw).hexdigest(), lineage=lineage)
        return result


def make_hold_risk_plan_adapter(*, composition, validate, review_guard):
    """Create callback(*, original, proposal, account, target, now).

    validate and review_guard are mandatory server-owned callables. The latter
    must check current news/event generations and the review's source binding;
    None means success, False or an exception means rejection. The owning service
    must additionally retain its post-callback final validation.
    """
    require(callable(validate) and callable(review_guard), 'NEWS_SERVER_GUARDS_REQUIRED')

    def adapter(*, original, proposal, account, target, now):
        result = dict(schema='NEWS_AI_RISK_PLAN_V1', status='WAIT', reason='WAIT_NEW_QUOTES_REQUIRED',
            review_id=proposal.get('review_id'), original_binding=deepcopy(proposal.get('original_binding')),
            generated_at=now, valid_until=None, rows=[], candidate_orders=[], cash=None, waiting_cash=[],
            constraints=[], orders_created=False, executable=False, account_mutated=False,
            target_mutated=False, original_risk_mutated=False,
            limitation='Unadopted HOLD sell-only news projection; investment benefit is unverified.')
        try:
            with getattr(composition.monthly, 'snapshot_operation', nullcontext)():
                return build(result, original, proposal, account, target, now)
        except Exception as error:
            # No exception message or upstream response/body is exposed.
            code = str(error)
            result['reason'] = code if code and len(code) < 100 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_' for c in code) else 'NEWS_EXECUTION_EVIDENCE_UNAVAILABLE'
            return result

    def build(result, original, proposal, account, target, now):
        started = moment(now)
        require(composition.enabled, 'DAILY_PREVIEW_DISABLED')
        require(original.get('status') == 'HOLD' and not original.get('new_orders'), 'NEWS_ORIGINAL_HOLD_REQUIRED')
        require(proposal.get('schema') == 'NEWS_INVESTMENT_REVIEW_PROPOSAL_V1'
                and proposal.get('status') == 'REVIEW_PROPOSAL_ONLY', 'NEWS_REVIEW_REQUIRED')
        require(proposal.get('executable') is False and proposal.get('orders_created') is False, 'NEWS_NONEXECUTABLE_REQUIRED')
        state, base = deepcopy(composition.monthly.accounts.read()), deepcopy(composition.monthly.current())
        view = deepcopy(composition.monthly_view.current())
        require(state == account and view == target, 'NEWS_ACCOUNT_OR_TARGET_CHANGED')
        binding = {key: original[key] for key in ('account_revision', 'target_id', 'proposal_id')}
        require(all(binding.values()) and binding == proposal['original_binding']
                and binding['account_revision'] == state['revision'] and binding['target_id'] == base['target_id'], 'NEWS_BINDING_CHANGED')
        require(base['payload']['account_id'] == state['account_id'], 'TARGET_ACCOUNT_MISMATCH')
        require(state.get('cash_confirmation_valid') is True and state.get('execution_ready') is True, 'CASH_CONFIRMATION_REQUIRED')
        require(not any(o['status'] == 'OPEN' for o in state['orders'].values()), 'WAIT_PENDING_RECONCILIATION')
        monthly_proposal = deepcopy(composition.monthly_view.require_proposal(target_id=base['target_id'], expected_proposal_id=binding['proposal_id']))
        require(SavedFrontierMonthlyView._view(composition.monthly_view, base, monthly_proposal) == view, 'NEWS_TARGET_VIEW_CHANGED')
        require(Fraction(str(composition.fees)) == Fraction(str(monthly_proposal['payload']['fee_bps'])), 'FRONTIER_FEE_MISMATCH')

        def unchanged():
            validate()
            composition.monthly.validate_current_target_pins()
            require(review_guard() is not False, 'NEWS_REVIEW_INVALIDATED')
            require(composition.monthly.accounts.read() == state and composition.monthly.current() == base, 'NEWS_ACCOUNT_OR_TARGET_CHANGED')
            require(composition.monthly_view.current() == view, 'NEWS_TARGET_VIEW_CHANGED')
            require(composition.monthly_view.require_proposal(target_id=base['target_id'], expected_proposal_id=binding['proposal_id']) == monthly_proposal, 'FRONTIER_PROPOSAL_CHANGED')
            current = moment(composition.clock().isoformat())
            require(current >= started, 'SERVER_CLOCK_MOVED_BACKWARDS')
            require(moment(proposal['review_created_at']) <= current < moment(proposal['review_valid_until']), 'REVIEW_EXPIRED')
            require(moment(original['risk_valid_from']) <= current < moment(original['risk_valid_until']), 'ORIGINAL_RISK_EXPIRED')
            return current

        unchanged()
        evidence = composition.reader(deepcopy(state), deepcopy(base), composition.clock(), proposal=deepcopy(monthly_proposal))
        current = unchanged()
        signal = evidence.get('signal')
        require(evidence.get('status') == 'DAILY_SIGNAL_READY' and type(signal) is dict
                and bool(evidence.get('evidence_archive')) and signal.get('evidence_archive') == evidence['evidence_archive'], 'DAILY_ARCHIVE_REQUIRED')
        require(signal.get('proposal_id') == binding['proposal_id'] and signal.get('policy_id') == original.get('policy_id') == composition.policy_id, 'NEWS_SIGNAL_BINDING_CHANGED')
        effective = signal['effective_target_quantities']
        monthly = monthly_proposal['payload']['proposed_target_quantities']
        require(set(monthly) <= set(effective), 'FRONTIER_SIGNAL_DOMAIN')
        gate = resolve_daily_target(account_id=state['account_id'], account_revision=state['revision'],
            target_id=base['target_id'], target_month=base['payload']['target_month'],
            monthly_quantities={sid: monthly.get(sid, 0) for sid in effective}, strategy_shares=state['shares'],
            available_cash=state['available_cash'], pending_orders=[], now=current.isoformat(),
            expected_policy_id=composition.policy_id, signal=signal)
        require(gate['status'] == 'DAILY_TARGET_READY' and all(r['action'] == 'HOLD' for r in gate['rows']), 'NEWS_FRESH_HOLD_REQUIRED')
        if original.get('effective_target_quantities') is not None:
            require(original['effective_target_quantities'] == effective, 'NEWS_ORIGINAL_RISK_CHANGED')
        domain = {sid for sid in effective if effective[sid] or state['shares'].get(sid, 0)}
        rows = proposal['rows']
        require(type(rows) is list and len(rows) == len(domain) and {r['security_id'] for r in rows} == domain, 'NEWS_EXACT_DOMAIN_REQUIRED')
        targets, output = deepcopy(effective), []
        for row in rows:
            sid = row['security_id']; held = integer(state['shares'].get(sid, 0)); desired = integer(row['proposed_target_quantity'])
            require(row['held_quantity'] == held and row['original_target_quantity'] == effective[sid], 'NEWS_TARGET_ANCHOR_CHANGED')
            require(desired <= effective[sid] == held, 'NEWS_SELL_ONLY_REQUIRED')
            action = row['action']
            require(action in {'KEEP','PAUSE_BUY','REDUCE_BUY','REDUCE_HOLDING','EXIT','ABSTAIN'}, 'NEWS_ACTION_INVALID')
            require(desired == held or (row.get('reviewed') is True and action in {'REDUCE_HOLDING','EXIT'}), 'NEWS_REDUCTION_NOT_REVIEWED')
            require(action != 'EXIT' or desired == 0, 'NEWS_EXIT_TARGET_INVALID')
            targets[sid] = desired
            output.append(dict(security_id=sid, action=action, held_quantity=held, original_target_quantity=held,
                proposed_target_quantity=desired, desired_target_quantity=desired, planned_target_quantity=desired,
                execution_buy_cap=0, reviewed=row.get('reviewed') is True))
        if targets == effective:
            return dict(result, status='ABSTAIN', reason='NO_ADMITTED_HOLD_REDUCTION')
        bridge = NewsHoldExecutionBridge(base_target=base, execution_provider=composition.provider,
            validate_sources=unchanged, signal=signal, proposal=proposal)
        quotes = bridge(deepcopy(state), targets, composition.clock())
        current = unchanged()
        require(moment(signal['valid_from']) <= current < moment(signal['valid_until']), 'DAILY_SIGNAL_EXPIRED_DURING_PREVIEW')
        deadlines = [moment(proposal['review_valid_until']), moment(signal['valid_until']), moment(original['risk_valid_until'])]
        for sid in domain:
            mark, quote = quotes['marks'][sid], quotes['limits'][sid]
            require(quote['evaluated_account_revision'] == state['revision'] and quote['evaluated_net_gap'] == targets[sid]-state['shares'].get(sid,0), 'NEWS_QUOTE_BINDING_CHANGED')
            require(bool(mark.get('source_hashes')) and all(quote.get('source_hashes',{}).get(p) == h for p,h in mark['source_hashes'].items()), 'NEWS_QUOTE_SOURCE_REQUIRED')
            deadline = moment(quote['reference_valid_until']); require(current < deadline, 'REQUOTE_REQUIRED'); deadlines.append(deadline)
            if targets[sid] < state['shares'].get(sid,0):
                price = Fraction(mark['price']); rounded = Fraction(-(-price.numerator*100//price.denominator),100)
                require(bool(quote.get('sell_reason')) and Fraction(quote['sell']) == rounded, 'VERIFIED_SELL_QUOTE_REQUIRED')
        difference = preview_scoped_account(state=state, legacy_shares={}, marks=quotes['marks'], limits=quotes['limits'],
            target_quantities=targets, now=current.isoformat(), maximum_mark_age_seconds=120, fee_bps=composition.fees)
        require(difference['status'] == 'READY' and all(o['side'] == 'SELL' for o in difference['new_orders']), 'NEWS_SELL_ONLY_REQUIRED')
        current = unchanged(); require(current < min(deadlines), 'REQUOTE_REQUIRED')
        return dict(result, status='READY', reason='HOLD_LOWER_TARGET_PREVIEW_ONLY', rows=output,
            candidate_orders=deepcopy(difference['new_orders']), valid_until=min(deadlines).isoformat(),
            cash={**{k:difference[k] for k in ('spendable_cash','new_buy_cash_required','unallocated_spendable_cash')},'sell_proceeds_assumed':False},
            binding=bridge.binding, binding_sha256=digest(bridge.binding), original_preview_sha256=digest(original),
            original_risk_interval={'valid_from':original['risk_valid_from'],'valid_until':original['risk_valid_until']},
            derived_account_proof_sha256=difference['binding_sha256'])
    return adapter


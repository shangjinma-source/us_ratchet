"""Fixed execution staging only; dedicated offline process, never production."""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from threading import RLock

LOCK = RLock()


def canonical_hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def uncapped_winner(selection):
    """Prove the selected capped basket comes from this same-call winner."""
    raw = selection['raw_selection']
    arguments = raw['binding']['search_arguments']
    audit = selection['rerank_audit']
    quantities = (raw['search_result']['best_by_k'][str(audit['source_cardinality'])]['quantities']
                  if audit['strict_improvement'] else raw['target_quantities'])
    equity = Fraction(raw['investable_equity'])
    if equity != Fraction(arguments['entered_cash']):
        raise ValueError('STAGE_SELECTION_EQUITY_MISMATCH')
    if any(type(q) is not int or q < 0 for q in quantities.values()):
        raise ValueError('STAGE_UNCAPPED_QUANTITY_INVALID')
    capped = {}
    for sid, q in quantities.items():
        price = Fraction(arguments['prices'][sid])
        if price <= 0:
            raise ValueError('STAGE_SELECTION_PRICE_INVALID')
        capped[sid] = min(q, int(equity / (2 * price)))
    positive = lambda value: {s: q for s, q in value.items() if q}
    if positive(capped) != positive(selection['target_quantities']):
        raise ValueError('STAGE_UNCAPPED_WINNER_BINDING_MISMATCH')
    return dict(quantities=deepcopy(quantities), capped=deepcopy(selection['target_quantities']),
                selection_sha256=canonical_hash(selection), raw_sha256=canonical_hash(raw),
                source_cardinality=audit['source_cardinality'], strict_improvement=audit['strict_improvement'])


class TwoStageExecution:
    def __init__(self, mode):
        if mode not in ('BASELINE', 'BUY_TWO_OPENS', 'CAP_SELL_TWO_OPENS'):
            raise ValueError('FIXED_STAGE_MODE_REQUIRED')
        self.mode = mode
        self.epoch = None
        self.episodes = {}
        self.winners = {}
        self.audit = []

    def register(self, day, selection):
        self.winners[day] = uncapped_winner(selection)

    def adjust(self, result, *, state, decision_date, active_date):
        original = deepcopy(result)
        adjusted = deepcopy(result)
        if result.get('status') != 'READY':
            return adjusted
        if result.get('action') == 'WAIT_POST_ACTION_MARK':
            if self.episodes:
                raise ValueError('STAGE_PENDING_POST_ACTION_REVIEW_REQUIRED')
            return adjusted
        epoch = result.get('target_decision_date')
        if epoch != self.epoch:
            self.episodes = {}
            self.epoch = epoch
        target = result.get('target_shares', {})
        ceiling = result.get('monthly_ceiling', {})
        holdings = state['shares']
        # An old episode cannot cross corporate-action coordinates silently.
        for change in result.get('target_adjustments', []):
            if change['security_id'] in self.episodes:
                raise ValueError('STAGE_PENDING_ACTION_COORDINATE_REVIEW_REQUIRED')
        for sid in list(self.episodes):
            if not target.get(sid, 0) or holdings.get(sid, 0) == target.get(sid, 0):
                del self.episodes[sid]
        orders = []
        decisions = []
        for order in result.get('orders', []):
            item = deepcopy(order)
            sid = item['security_id']
            h, effective = holdings.get(sid, 0), target.get(sid, 0)
            qualifies = (self.mode == 'BUY_TWO_OPENS' and item['side'] == 'BUY')
            pure_cap = 0
            noncap = 0
            if self.mode == 'CAP_SELL_TWO_OPENS' and item['side'] == 'SELL' and effective > 0 and effective == ceiling.get(sid):
                winner = self.winners.get(epoch)
                if winner is None:
                    raise ValueError('STAGE_WINNER_PROVENANCE_REQUIRED')
                u = winner['quantities'].get(sid, 0)
                if winner['capped'].get(sid, 0) != effective:
                    raise ValueError('STAGE_ACTION_ADJUSTED_WINNER_REVIEW_REQUIRED')
                noncap = max(0, h-u)
                pure_cap = max(0, min(h, u)-effective)
                qualifies = pure_cap > 0
            if not qualifies:
                orders.append(item)
                continue
            episode = self.episodes.get(sid)
            if episode is None:
                first = item['quantity']//2 if self.mode == 'BUY_TWO_OPENS' else noncap+(pure_cap+1)//2
                episode = dict(epoch=epoch, side=item['side'], first_quantity=first,
                               initial_gap=item['quantity'], start_decision=decision_date,
                               first_active_date=active_date, ids=[], phase=1)
                self.episodes[sid] = episode
            fills = [log for log in state.get('order_log', [])
                     if log.get('event') == 'ASSUMED_NEXT_OPEN_FILLED'
                     and log.get('id') in episode['ids'] and log.get('quantity', 0) > 0]
            if fills or (episode['first_quantity'] == 0 and decision_date >= episode['first_active_date']):
                episode['phase'] = 2
            quantity = (min(item['quantity'], episode['first_quantity'])
                        if episode['phase'] == 1 else item['quantity'])
            if self.mode == 'CAP_SELL_TWO_OPENS':
                quantity = max(quantity, noncap)
            item['id'] = 'stage:'+self.mode+':'+str(epoch)+':'+decision_date+':'+sid
            item['quantity'] = quantity
            if quantity:
                episode['ids'].append(item['id'])
                orders.append(item)
            decisions.append(dict(security_id=sid, original_quantity=order['quantity'],
                                  staged_quantity=quantity, phase=episode['phase'],
                                  pure_cap_quantity=pure_cap, noncap_quantity=noncap,
                                  episode=deepcopy(episode)))
        adjusted['orders'] = orders
        proof = dict(decision_date=decision_date, active_date=active_date, mode=self.mode,
                     original=original, adjusted=deepcopy(adjusted), decisions=decisions,
                     actual_shares=deepcopy(holdings), actual_cash=state['cash'])
        self.audit.append(proof)
        return adjusted


def run_staged(*, mode, assembled, selector=None, decision_callback=None, **kwargs):
    """Wrap original risk/account kernel; selector always receives branch state."""
    from backtest import historical_dividend_frontier_research as frontier
    if kwargs.get('verified_prefix'):
        raise ValueError('USE_EXACT_ARGUMENT_SELECTOR_CACHE_NOT_PREFIX')
    stage = TwoStageExecution(mode)
    with LOCK:
        old_select, old_rerank, old_book = frontier.decide_continuous_guided_for_account, frontier.rerank, frontier.run_next_open_book
        arguments_by_day = {}

        def select(**arguments):
            arguments_by_day[arguments['decision_date']] = deepcopy(arguments)
            return (selector or old_select)(**arguments)

        def rerank(raw):
            selection = old_rerank(raw)
            day = raw['decision_date']
            stage.register(day, selection)
            if decision_callback:
                decision_callback(deepcopy(arguments_by_day[day]), deepcopy(selection))
            return selection

        def book(**arguments):
            provider = arguments['order_provider']

            def staged_provider(**state_arguments):
                result = provider(**state_arguments)
                return stage.adjust(result, **state_arguments)

            arguments['order_provider'] = staged_provider
            return old_book(**arguments)

        try:
            frontier.decide_continuous_guided_for_account = select
            frontier.rerank = rerank
            frontier.run_next_open_book = book
            result = frontier.run_frontier_capped_next_open(assembled=assembled, **kwargs)
        finally:
            frontier.decide_continuous_guided_for_account = old_select
            frontier.rerank = old_rerank
            frontier.run_next_open_book = old_book
    result['execution_stage_audit'] = stage.audit
    result['execution_stage_mode'] = mode
    result['uncapped_winner_proofs'] = stage.winners
    return result

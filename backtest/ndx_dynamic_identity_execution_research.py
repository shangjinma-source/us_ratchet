"""Research execution wrapper: validated daily identity coordinates, frozen lots.

The old engine sees stable internal labels only. Display labels are restored at
their own decision/execution/valuation sessions, never from a future decision.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from backtest import ndx_price_identity_bridge_research as bridge
from backtest import ndx_dynamic_frozen_execution_research as engine

_SOURCE = Path(__file__).resolve()
_LOADED = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
    _SOURCE, Path(bridge.__file__).resolve(), Path(engine.__file__).resolve())}


def _verify(sources):
    for path, digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Identity execution source drift: ' + path)


def simulate_dynamic_identity_execution_research(*, calendar, securities, schedule, **execution_parameters):
    """Rebuild and verify the bridge on every call; never accept cached bridges.

    Other parameters are the frozen engine's original execution/risk contract.
    Raw prices and identity_events cannot be passed through this interface.
    Corporate split events remain separate SID-keyed inputs to the old engine.
    """
    _verify(_LOADED)
    engine._check_sources()
    forbidden = {'closes', 'opens', 'identity_events', 'bridge', 'price_bridge'}
    if forbidden & set(execution_parameters):
        raise ValueError('Unverified price/identity override forbidden')
    if type(schedule) not in (list, tuple) or not schedule:
        raise ValueError('Explicit nonempty schedule required')
    # Snapshot caller-owned inputs to avoid later mutation changing labels.
    security_inputs = deepcopy(securities)
    original_schedule = deepcopy(schedule)
    prices = bridge.build_price_identity_bridge(calendar=deepcopy(calendar), securities=security_inputs)
    sources = dict(_LOADED)
    for mapping in (engine._LOADED_SOURCES, prices['source_hashes']):
        for path, digest in mapping.items():
            if path in sources and sources[path] != digest:
                raise ValueError('Conflicting source closure')
            sources[path] = digest
    _verify(sources)
    columns = prices['internal_columns_by_security']
    labels = prices['tickers_by_session']
    translated = deepcopy(original_schedule)
    for row in translated:
        day = bridge._date(row['decision_date'])
        if day not in labels or type(row['targets']) is not dict:
            raise ValueError('Decision outside validated price identity calendar')
        for sid, target in row['targets'].items():
            if (sid not in columns or type(target) is not dict
                    or target.get('issuer_id') != security_inputs[sid]['issuer_id']
                    or target.get('ticker') != labels[day][sid]):
                raise ValueError('Decision SID/issuer/ticker differs from validated identity')
            target['ticker'] = columns[sid]
    try:
        result = engine.simulate_dynamic_frozen_execution_research(
            closes=prices['closes'], opens=prices['opens'], schedule=translated,
            identity_events=(), **deepcopy(execution_parameters))

        def plan_labels(plan):
            if plan is None:
                return
            day = plan['decision_date']
            for sid, target in plan['targets'].items():
                if target['ticker'] != columns[sid]:
                    raise ValueError('Unexpected internal engine label')
                target['internal_price_column'] = target['ticker']
                target['ticker'] = labels[day][sid]

        for decision in result['decisions']:
            plan_labels(decision)
        for execution in result['executions']:
            if 'plan' in execution:
                plan_labels(execution['plan'])
            execution['tickers_by_security'] = {sid: labels[execution['session']][sid]
                                               for sid in execution.get('prices', {})}
        for trade in result['trades']:
            sid = trade['security_id']
            if trade['ticker'] != columns[sid]:
                raise ValueError('Unexpected internal trade label')
            trade['internal_price_column'] = trade['ticker']
            trade['ticker'] = labels[trade['session']][sid]
        for day in result['daily']:
            day['internal_price_columns'] = day['tickers']
            day['tickers'] = {sid: labels[day['session']][sid] for sid in day['shares']}
        for action in result['corporate_actions']:
            plan_labels(action['cancelled_plan'])
            plan_labels(action['pending_plan'])
            for applied in action['applied_events']:
                # The original split primitive calls its SID key "ticker".
                # Make that distinct from the real session ticker in this API.
                event = applied['event']
                sid = event.pop('ticker')
                event['security_id'] = sid
                event['ticker'] = labels[action['session']][sid]
        result.update(engine_schema=result['schema'],
            schema='ndx_dynamic_identity_execution_research_v1', source_hashes=sources,
            identity_events=deepcopy(prices['rename_event_audit']),
            price_identity_audit=deepcopy(prices['price_audit']),
            internal_columns_by_security=dict(columns),
            tickers_by_session=deepcopy(labels),
            alias_policy='VALIDATED_SID_PRICE_INTERVALS_SAME_SECURITY_RENAME_NO_ACCOUNTING_ACTION',
            bridge_schema=prices['schema'],
            identity_event_source_authenticity_verified=False,
            source_authenticity_verified=False, point_in_time_verified=False,
            corporate_action_coverage_verified=False, promotion_allowed=False)
        return result
    finally:
        engine._check_sources()
        _verify(sources)

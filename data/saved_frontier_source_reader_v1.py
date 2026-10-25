"""Local source-reader pipeline from durable captures to conditional frontier review.

No network or account writes. The caller chooses capture transport and risk store.
Pinned baseline bytes are read by the versioned first-window reviewer; capture
prices cannot serve as their own historical continuity evidence.
"""
from copy import deepcopy
import json

from core.strategy_account_ledger import require
from data.saved_frontier_capture_review_v1 import review_supplement_packets
from data.saved_frontier_source_review_v1 import review_proposal_monthly_sources
from data.saved_frontier_exit_packet_v1 import apply_frontier_exit_packet


def read_frontier_capture(*, root, prepared, capture, state, target, proposal,
                          risk_state, now):
    require(prepared['status'] == 'SUPPLEMENT_REQUEST_PREPARED', 'WAIT_FRONTIER_PREPARED_REQUEST')
    extra = set() if risk_state is None else set(risk_state['peaks']) | set(risk_state['exited'])
    reviewed = review_supplement_packets(root=root, capture=capture,
        request=prepared['request'], binding=prepared['binding'], state=state, target=target,
        configurations=prepared['configurations'], proposal=proposal,
        extra_security_ids=extra, clock=lambda: now)
    combined = None
    identities = {}
    execution = None
    for sid, packet in reviewed['packets'].items():
        receipt = json.loads(packet['receipt_bytes'])
        current = json.loads(packet['files'][receipt['monthly_history_inputs_path']])
        if combined is None:
            combined = deepcopy(current)
            combined['histories'] = {}
            combined['base_target']['quantities'] = {}
            combined['base_target']['price_units'] = {}
            execution = receipt['execution_session']
        require(receipt['execution_session'] == execution and
                current['session_dates'] == combined['session_dates'] and
                current['signal_date'] == combined['signal_date'] and
                current['session_close_times'] == combined['session_close_times'],
                'FRONTIER_REVIEW_CALENDAR_CONFLICT')
        history = deepcopy(current['histories'][sid])
        epoch = current['base_target']['monthly_decision_date']
        history['closes'] = [row for row in history['closes'] if row['date'] >= epoch]
        combined['histories'][sid] = history
        combined['base_target']['quantities'][sid] = current['base_target']['quantities'][sid]
        combined['base_target']['price_units'][sid] = current['base_target']['price_units'][sid]
        meta = json.loads(packet['files'][history['source_reference']])['chart']['result'][0]['meta']
        identities[sid] = dict(ticker=meta['symbol'], exchange=meta['exchangeName'])
    require(combined is not None, 'FRONTIER_EMPTY_REVIEW')
    result = review_proposal_monthly_sources(target=target, proposal=proposal, state=state,
        risk_state=risk_state, inputs=combined, identities=identities, capture=capture,
        request=prepared['request'], execution_session=execution, now=now)
    return dict(review=result, packets=reviewed['packets'], identities=identities,
                account_mutated=False, production_admitted=False)


def read_and_apply_frontier_capture(*, root, prepared, capture, state, target,
        proposal, risk_store, now, authorized_monthly_reset=None):
    """Advance caller-owned risk storage only after full source admission."""
    previous = risk_store.read(state['account_id'])
    source = read_frontier_capture(root=root, prepared=prepared, capture=capture,
        state=state, target=target, proposal=proposal, risk_state=previous, now=now)
    inputs = source['review']['inputs']
    result = apply_frontier_exit_packet(target=target, proposal=proposal, inputs=inputs,
        risk_store=risk_store, account_id=state['account_id'],
        decision_date=inputs['base_target']['monthly_decision_date'],
        expected_previous_session=None if previous is None else previous['session_date'],
        authorized_monthly_reset=authorized_monthly_reset)
    return dict(source, risk_result=result)

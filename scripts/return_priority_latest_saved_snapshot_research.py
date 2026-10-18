"""Apply sealed historical rule order to one current conditional saved snapshot.

No backtest, forecast, network, old-account input or order generation. Invoke as
python -m scripts.return_priority_latest_saved_snapshot_research --help.
CLI writes a single create-only JSON; importing this file performs no IO.
"""
import argparse
from collections import Counter
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

from backtest.return_priority_joint_candidate_generator_research import generate_joint_candidates


PANEL_PATH = 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json'
PROPOSAL_PATH = 'tmp/current_conditional_metadata_proposal_20261014_v3/proposal.json'
RESULT_PATH = 'tmp/joint_family_experiment_20261014_v1/result.json'
FROZEN_PATH = 'tmp/joint_family_experiment_20261014_v1/frozen_candidate_snapshots.json'
GENERATOR_PATH = 'backtest/return_priority_joint_candidate_generator_research.py'
SOURCE_PINS = {
    PANEL_PATH: '92361a7321765594a5544ab3cb9128410c8296799d99b3d23090e24a37df9822',
    PROPOSAL_PATH: 'e61c04aaec6f2f7b477eb7a83c9b882305c7e0449ec60fae85c5e8c01f51d92c',
    RESULT_PATH: 'd59604d82d4398d9165373f70d6010c87150a387358b04695b4bd2f4a9a872ea',
    FROZEN_PATH: '25f18d1f12f8f6e2e1db3bbc0e78cb781c04328f963e6cec21425a2afe46ef19',
    GENERATOR_PATH: 'f9ec16351443c41454ee667daac3af2863d15471e3f43937044006300abc0a01',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_close(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def build_latest_saved_snapshot(*, panel, current_proposal, historical_result,
                                frozen_method_snapshot, entered_cash,
                                accepted_tickers, source_refs):
    """One pure call; explicit accepted_tickers records Root's research acceptance.

Acceptance never edits proposal rows or promotes identity/PIT/price certification.
The source proposal itself remains PROPOSED_NOT_ACCEPTED. This function separately
records which assumptions Root accepted for this one saved observation only.
"""
    calendar = panel['calendar']
    require(calendar and calendar == sorted(set(calendar)), 'Ordered unique saved calendar')
    day, index = calendar[-1], len(calendar) - 1
    require(day == current_proposal['observation_date'], 'Proposal must bind latest saved observation')
    require(current_proposal['assumption_role'] == 'CURRENT_CONDITIONAL_RESEARCH_ASSUMPTION',
            'Explicit current conditional assumption, not old qualification extension')
    require(type(accepted_tickers) is list and len(accepted_tickers) == len(set(accepted_tickers)),
            'Explicit unique Root accepted ticker list')
    require(type(source_refs) is list and source_refs, 'Explicit source references')
    budget = Fraction(str(entered_cash))
    require(budget > 0, 'Positive explicit fresh-cash research budget')
    channels = {row['ticker']: row for row in panel['stocks']}
    proposed = {row['ticker']: row for row in current_proposal['proposed_metadata']}
    exclusions = {row['ticker']: row for row in current_proposal['exclusions']}
    require(len(channels) == len(panel['stocks']), 'Unique saved stock channels')
    require(len(proposed) == len(current_proposal['proposed_metadata']) and
            len(exclusions) == len(current_proposal['exclusions']) and not set(proposed) & set(exclusions),
            'Unique exhaustive proposal/exclusion rows')
    require(set(proposed) | set(exclusions) == set(channels), 'Every saved stock has metadata coverage')
    require(set(accepted_tickers) <= set(proposed), 'Cannot accept excluded or invented securities')
    require(historical_result['status'] == 'COMPLETE_CONDITIONAL_FINITE_FAMILY_COMPARISON',
            'Complete sealed historical comparison required')
    historical_order = [row['rule'] for row in historical_result['rankings']]
    require(historical_order and len(historical_order) == len(set(historical_order)), 'Unique frozen rule order')
    metadata, prices, scores, coverage = {}, {}, [], []
    for ticker, channel in channels.items():
        source_row = proposed.get(ticker, exclusions.get(ticker))
        record = {'ticker': ticker, 'status': None, 'exclusion_reasons': [],
                  'metadata_proposal': deepcopy(source_row),
                  'root_accepted_current_assumption': ticker in accepted_tickers,
                  'channel_raw_reference': deepcopy(channel.get('raw_reference')),
                  'qualified': False, 'point_in_time_verified': False,
                  'current_interval_verified': False, 'live_adoption': False}
        values = channel['values']
        require(len(values) == len(calendar), 'Uncompressed aligned saved channel required')
        history = values[index - 252:index - 21 + 1] if index >= 252 else []
        valid_count = sum(len(value) > 3 and valid_close(value[3]) for value in history)
        record['momentum_history_required_close_count'] = 232
        record['momentum_history_valid_close_count'] = valid_count
        record['current_close'] = values[index][3]
        if ticker not in proposed:
            record['exclusion_reasons'].append('NO_PROPOSED_CURRENT_CONDITIONAL_METADATA')
        elif ticker not in accepted_tickers:
            record['exclusion_reasons'].append('CURRENT_ASSUMPTION_NOT_ACCEPTED_BY_ROOT')
        if len(history) != 232 or valid_count != 232:
            record['exclusion_reasons'].append('SHORT_OR_INCOMPLETE_232_CLOSE_MOMENTUM_HISTORY')
        if not valid_close(record['current_close']):
            record['exclusion_reasons'].append('LATEST_SAVED_CLOSE_MISSING_OR_INVALID')
        if record['exclusion_reasons']:
            record['status'] = 'EXCLUDED_FROM_CURRENT_CANDIDATE_GENERATION'
        else:
            security = source_row['security_id']
            require(security not in metadata, 'No duplicate accepted security ID')
            require(source_row['assumption_role'] == 'CURRENT_CONDITIONAL_RESEARCH_ASSUMPTION',
                    'Every included row must retain current conditional role')
            metadata[security] = {
                'ticker': ticker, 'issuer_id': source_row['issuer_id'], 'risk_chain': source_row['risk_chain'],
                'source_refs': deepcopy(source_row['evidence_references']),
                'current_conditional_metadata_proposal': deepcopy(source_row),
            }
            prices[security] = record['current_close']
            score = Fraction(str(history[-1][3])) / Fraction(str(history[0][3])) - 1
            scores.append((score, security))
            record.update(status='INCLUDED_CURRENT_CONDITIONAL_RESEARCH_ONLY',
                          security_id=security, momentum_score=str(score))
        coverage.append(record)
    scores.sort(key=lambda value: (-value[0], value[1]))
    generated = generate_joint_candidates(
        decision_date=day, ordered_security_ids=[security for _, security in scores],
        metadata=metadata, close_prices=prices, entered_cash=str(budget),
        fee_bps=frozen_method_snapshot['fee_bps'],
        minimum_cash_buffer=frozen_method_snapshot['minimum_cash_buffer'],
        risk_parameters=frozen_method_snapshot['risk_parameters'],
        fixed_seed=frozen_method_snapshot['fixed_seed'],
        source_context={
            'ranking_as_of': calendar[index - 21] if index >= 21 else day,
            'close_as_of': day, 'qualification_start': day, 'qualification_end': day,
            'source_refs': deepcopy(source_refs),
            'qualification_is_conditional_assumption': True,
            'interval_role': 'ONE_SAVED_OBSERVATION_CURRENT_ASSUMPTION_NOT_HISTORICAL_QUALIFICATION',
            'old_qualification_window_extended': False,
        })
    by_rule = {row['method_rule_id']: row for row in generated['records']}
    selection_trace, selected = [], None
    for position, rule in enumerate(historical_order, 1):
        candidate = by_rule.get(rule)
        legal = candidate is not None and candidate['status'] in ('LEGAL_INDICATIVE_ONLY', 'REFERENCE_ALL_CASH')
        entry = {'historical_rank': position, 'method_rule_id': rule,
                 'current_status': candidate['status'] if candidate else 'RULE_NOT_GENERATED_IN_CURRENT_DOMAIN',
                 'current_blocked_reasons': deepcopy(candidate.get('blocked_reasons', [])) if candidate else [],
                 'selected': False}
        if selected is None and legal:
            selected = deepcopy(candidate)
            entry['selected'] = True
        selection_trace.append(entry)
    selected_positions = []
    if selected:
        for security in selected['security_ids']:
            selected_positions.append({
                'security_id': security, 'ticker': metadata[security]['ticker'],
                'issuer_id': metadata[security]['issuer_id'],
                'stock_internal_weight': selected['stock_internal_profile_weights'][security],
                'target_weight': selected['target_weights'][security],
                'indicative_units': selected['indicative_quantities'][security],
                'saved_close': prices[security],
                'metadata_source_refs': deepcopy(metadata[security]['source_refs']),
            })
    return {
        'schema': 'LATEST_SAVED_CURRENT_CONDITIONAL_RULE_APPLICATION_V1',
        'status': 'SELECTED_CURRENT_INDICATIVE_RESEARCH_CANDIDATE' if selected else 'NO_CURRENT_LEGAL_SEALED_RULE',
        'saved_observation_date': day, 'date_role': 'SAVED_SNAPSHOT_NOT_TODAY_ORDER',
        'fresh_cash_pool': str(budget), 'initial_positions': {},
        'accepted_current_conditional_tickers': list(accepted_tickers),
        'all_observed_stock_coverage': coverage,
        'coverage_counts': dict(Counter(row['status'] for row in coverage)),
        'momentum_formula': 'P[T-21]/P[T-252]-1_WITH_ALL_232_CLOSES_REQUIRED',
        'momentum_first_date': calendar[index - 252] if index >= 252 else None,
        'momentum_last_date': calendar[index - 21] if index >= 21 else None,
        'current_momentum_ranking': [{'security_id': security, 'score': str(score)} for score, security in scores],
        'candidate_generation': generated, 'sealed_rule_application_trace': selection_trace,
        'selected_candidate': selected, 'selected_positions': selected_positions,
        'selection_method': 'FIRST_CURRENT_LEGAL_RULE_IN_UNCHANGED_SEALED_HISTORICAL_ORDER',
        'source_refs': deepcopy(source_refs),
        'generator_calls': 1, 'book_calls': 0, 'historical_replays': 0, 'parameter_searches': 0,
        'future_prices_read': False, 'forecast_return': None, 'current_adoption_allowed': False,
        'point_in_time_verified': False, 'price_basis_authenticated': False,
        'nominal_broker_shares_authenticated': False, 'dividend_total_return_verified': False,
        'old_qualification_window_extended': False, 'global_optimum_established': False,
        'today_orders': False, 'orders_created': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entered-cash', required=True)
    parser.add_argument('--accepted-tickers', required=True, help='Root reviewed current conditional tickers, comma separated')
    parser.add_argument('--accept-current-conditional-assumptions', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True, help='New JSON path; must not exist')
    arguments = parser.parse_args()
    require(not arguments.output.exists(), 'Create-only result: output already exists')
    require(arguments.output.parent.is_dir(), 'Existing output parent required')
    root = Path(__file__).resolve().parents[1]
    raw_sources = {}
    for relative, expected in SOURCE_PINS.items():
        raw = (root / relative).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, 'Source fingerprint changed: ' + relative)
        raw_sources[relative] = raw
    panel, proposal, historical, snapshots = [json.loads(raw_sources[path]) for path in
                                               (PANEL_PATH, PROPOSAL_PATH, RESULT_PATH, FROZEN_PATH)]
    require(panel['calendar'][-1] == '2026-10-12' and len(panel['stocks']) == 101, 'Pinned latest saved101 domain')
    require(len(historical['rankings']) == 46, 'Pinned 46 sealed historical rule order')
    require(historical['frozen_candidates_sha256'] == SOURCE_PINS[FROZEN_PATH], 'Frozen method/result binding')
    require(snapshots and snapshots[-1]['decision_date'] == '2026-09-21', 'Pinned final historical method snapshot')
    accepted = [ticker.strip() for ticker in arguments.accepted_tickers.split(',') if ticker.strip()]
    source_refs = [{'path': path, 'sha256': digest} for path, digest in SOURCE_PINS.items()]
    result = build_latest_saved_snapshot(
        panel=panel, current_proposal=proposal, historical_result=historical,
        frozen_method_snapshot=snapshots[-1], entered_cash=arguments.entered_cash,
        accepted_tickers=accepted, source_refs=source_refs)
    result['runner_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with arguments.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'status': result['status'], 'output': str(arguments.output.resolve()),
                      'saved_observation_date': result['saved_observation_date'],
                      'generator_calls': result['generator_calls'], 'book_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Explicit historical decision slices only; no fit, selection, file or network IO."""
from collections import Counter
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import math

SCHEMA = 'CONDITIONAL_MULTIDECISION_TRAINING_INPUTS_V1'
CONTRACT_SCHEMA = 'EXPLICIT_HISTORICAL_MULTIDECISION_DRAFT_V1'
RULE = 'MONTH_FIRST_SAVED_SESSION_EXECUTION_PREVIOUS_SAVED_CLOSE'
PARAMETERS = dict(fit_days=126, shrinkage_intensity=.35, turnover_anchor_strength=.25,
    max_single_weight=.45, min_single_weight=.05, top_weight_cap=.8,
    minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55)
SPECS = ['equal_weight', 'constrained_fixed_shrinkage', 'constrained_fixed_shrinkage_turnover_anchor']
SIDECARS = ('original_evidence_and_projection', 'incremental_evidence_and_projection',
    'v3_incremental_evidence_and_projection', 'v4_incremental_evidence_and_projection',
    'v5_incremental_evidence_and_projection', 'v6_incremental_evidence_and_projection',
    'bulk_incremental_evidence_and_projection')
FLAGS = dict.fromkeys(('source_bytes_authenticated', 'point_in_time_verified',
    'complete_ndx_universe_verified', 'historical_pool_eligibility_verified',
    'historical_liquidity_qualified', 'identity_interval_extended', 'fit_performed',
    'selection_performed', 'task_inputs_materialized', 'execution_authorized',
    'promotion_allowed', 'formal_benchmark_evaluation_performed', 'fresh_oos',
    'old_results_reused', 'registered_execution_contract_verified'), False)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def exact(a, b, message):
    require(encode(a) == encode(b), message)


def reference(value):
    require(type(value) is dict and set(value) == {'path', 'sha256'}, 'Explicit reference required')
    require(type(value['path']) is str and bool(value['path']), 'Reference path')
    h = value['sha256']
    require(type(h) is str and len(h) == 64 and all(c in '0123456789abcdef' for c in h), 'SHA256 reference')


def day(value):
    require(type(value) is str, 'Date string required')
    d = date.fromisoformat(value)
    require(d.isoformat() == value and d.weekday() < 5, 'Canonical weekday date')
    return value


def prepare_multidecision_inputs(*, channels_document, channels_reference,
        expected_security_inventory, decision_path_contract, decision_path_reference,
        fit_contract):
    """Prepare causal slices against a caller-supplied draft, never register it.

    The exact inventory is the entire supplied conditional pool, not an assertion
    of complete PIT Nasdaq100 membership. No candidate subset is chosen. Prior
    dependencies cannot be resolved from this preparation's matrices or old fits.
    """
    reference(channels_reference)
    reference(decision_path_reference)
    require(type(decision_path_contract) is dict, 'Missing explicit decision path contract')
    contract = decision_path_contract
    require(set(contract) == {'schema', 'status', 'rule', 'rule_reference', 'decisions',
        'expected_decision_count', 'selection_contract_reference', 'search_budget_reference'}, 'Exact draft contract')
    require(contract['schema'] == CONTRACT_SCHEMA and contract['status'] == 'DRAFT_NOT_REGISTERED', 'Draft only')
    require(contract['rule'] == RULE, 'Explicit historical clock, not forward or rolling21')
    reference(contract['rule_reference'])
    for key in ('selection_contract_reference', 'search_budget_reference'):
        if contract[key] is not None:
            reference(contract[key])
    exact(fit_contract, dict(parameters=PARAMETERS, weight_specifications=SPECS), 'Original fit contract')
    # Canonical JSON equality also rejects bool-as-int and int-as-float substitutions.
    source = channels_document
    require(source['schema'] == 'BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1', 'Saved conditional channels schema')
    for key in ('point_in_time_verified', 'execution_authorized', 'promotion_allowed',
                'legal_training_input_admitted', 'fit_performed', 'historical_identity_verified',
                'historical_risk_verified', 'identity_interval_extended', 'future_independent_oos', 'untouched_holdout'):
        require(source[key] is False, 'Source authority changed: ' + key)
    require(source['evaluation_interval_previously_used_for_fitting'] is True, 'Consumed-window disclosure')
    calendar = source['calendar253']
    require(type(calendar) is list and len(calendar) == 253 and calendar == sorted(set(calendar)), 'Complete253 calendar')
    for value in calendar:
        day(value)
    require(type(expected_security_inventory) is list and bool(expected_security_inventory), 'Full explicit inventory')
    inventory = expected_security_inventory
    for row in inventory:
        require(type(row) is dict and set(row) == {'security_id', 'ticker', 'issuer_id'}, 'Inventory identity schema')
        require(all(type(v) is str and bool(v) for v in row.values()), 'Nonempty identities')
    sids = [r['security_id'] for r in inventory]
    require(sids == sorted(set(sids)) and len({r['ticker'] for r in inventory}) == len(inventory), 'Sorted unique SID/ticker inventory')
    rows = source['rows']
    require(type(rows) is list and len(rows) == len(inventory), 'No dropped channel columns')
    coordinates = [r['coordinate'] for r in rows]
    actual_inventory = sorted(({k: c[k] for k in ('security_id', 'ticker', 'issuer_id')} for c in coordinates), key=lambda c: c['security_id'])
    exact(actual_inventory, inventory, 'Entire original inventory differs')
    for c in coordinates:
        require(type(c['risk_chain']) is str and bool(c['risk_chain']), 'Missing risk label cannot silently drop SID')
    for key, value in dict(security_count=len(inventory), issuer_count=len({r['issuer_id'] for r in inventory}),
                           conditional_numeric_channel_count=len(inventory), blocked_price_channel_count=0).items():
        require(type(source[key]) is int and source[key] == value, 'Channel denominator: ' + key)
    provenance = source['original_provenance_and_missing']
    require(type(provenance) is list and type(source['observed_security_count']) is int
            and len(provenance) == source['observed_security_count'], 'Full original provenance denominator')
    require(len({r['ticker'] for r in provenance}) == len(provenance)
            and {r['ticker'] for r in inventory} <= {r['ticker'] for r in provenance}, 'Provenance ticker coverage')
    require(set(source['preserved_evidence_sidecars']) == set(SIDECARS)
            and set(source['preserved_sidecar_references']) == set(SIDECARS), 'All seven sidecars')
    by_sid = {}
    for n, row in enumerate(rows):
        c, channel = row['coordinate'], row['channel']
        require(channel['schema'] == 'BULK_LONG_WINDOW_CONDITIONAL_CHANNEL_V1'
                and channel['ticker'] == c['ticker'] and channel['status'] == 'CONDITIONAL_NUMERIC_RESULT'
                and channel['reasons'] == [], 'Incomplete channel retained as blocking input')
        for key in ('source_bytes_authenticated', 'provider_price_unit_verified', 'identity_interval_verified',
                    'point_in_time_verified', 'legal_training_input_admitted', 'execution_authorized', 'fit_performed'):
            require(channel[key] is False, 'Channel authority upgraded')
        exact(channel['calendar'], calendar, 'Missing price date cannot be compressed')
        exact(row['original_identity_assumed_window'], source['original_identity_assumed_window'], 'Identity window changed')
        rr = channel['return_rows']
        require(type(rr) is list and len(rr) == 252, 'All adjacent saved returns required')
        exact(rr, channel['training_returns'] + channel['evaluation_returns'], 'Saved partition differs')
        require(len(channel['training_returns']) == 126 and len(channel['evaluation_returns']) == 126
            and digest(channel['training_returns']) == channel['training_returns_sha256']
            and digest(channel['evaluation_returns']) == channel['evaluation_returns_sha256'], 'Partition digests')
        for j, item in enumerate(rr):
            require(item['previous_session'] == calendar[j] and item['session'] == calendar[j+1]
                    and item['dividends_included'] is False, 'Return predecessor or date mismatch')
            literal = item['split_only_return_exact']
            require(type(literal) is str and 0 < len(literal) <= 1024, 'Bounded rational literal')
            value = Fraction(literal)
            require(str(value) == literal and value > -1, 'Canonical split-only return')
            f = item['split_only_return_float']
            require(type(f) is float and math.isfinite(f) and f > -1 and f == float(value), 'Exact-to-float boundary')
        by_sid[c['security_id']] = (n, c, rr)
    counts = [1]
    for multiplicity in Counter(r['issuer_id'] for r in inventory).values():
        old = counts
        counts = [old[0]] + [old[k] + multiplicity * old[k-1] for k in range(1, len(old))] + [multiplicity * old[-1]]
    decisions = contract['decisions']
    require(type(decisions) is list and bool(decisions) and type(contract['expected_decision_count']) is int
            and contract['expected_decision_count'] == len(decisions), 'Complete explicit decision denominator')
    positions = {d: i for i, d in enumerate(calendar)}
    first_by_month = {}
    for d in calendar:
        first_by_month.setdefault(d[:7], d)
    prepared = []
    previous = None
    for i, decision in enumerate(decisions):
        require(type(decision) is dict and set(decision) == {'decision_date', 'execution_date'}, 'Exact decision coordinates')
        cutoff, execution = day(decision['decision_date']), day(decision['execution_date'])
        require(cutoff in positions and execution in positions, 'Missing execution/decision session')
        j = positions[cutoff]
        require(j >= 126 and positions[execution] == j+1 and first_by_month[execution[:7]] == execution,
                'Historical month-first execution and full126 predecessor required')
        require(previous is None or cutoff > previous, 'Duplicate/reordered decision')
        previous = cutoff
        columns = sorted(r['ticker'] for r in inventory)
        values, evidence = {}, []
        for sid in sids:
            n, c, rr = by_sid[sid]
            chosen = rr[j-126:j]
            values[c['ticker']] = [v['split_only_return_float'] for v in chosen]
            evidence.append(dict(security_id=sid, rows=[dict(session=v['session'],
                source_reference=dict(channels_reference, json_pointer=f'/rows/{n}/channel/return_rows/{j-126+t}'),
                exact_return=v['split_only_return_exact'], float_hex=v['split_only_return_float'].hex()) for t,v in enumerate(chosen)]))
        frame = dict(type='DataFrame', index_type='DatetimeIndex', index=[d+'T00:00:00' for d in calendar[j-125:j+1]],
            columns=columns, dtypes=['float64']*len(columns), data=[[values[t][r] for t in columns] for r in range(126)])
        prior = dict(status='FIRST_PERIOD_NONE' if i == 0 else 'UNRESOLVED_PREVIOUS_SUCCESSFUL_STRATEGIC_TARGET',
            previous_period_index=None if i == 0 else i-1, previous_target_weights=None,
            dependency_resolved=i == 0, actual_holdings_are_not_prior=True,
            rejected_execution_does_not_reset_prior=True)
        prepared.append(dict(period_index=i, **deepcopy(decision), cutoff=cutoff,
            training_price_predecessor=calendar[j-126], training_return_count=126,
            returns=frame, training_frame_sha256=digest(frame), numeric_conversion_evidence=evidence,
            selected_inventory_by_security={sid:{k:by_sid[sid][1][k] for k in ('ticker','issuer_id','risk_chain')} for sid in sids},
            candidate_selection_performed=False, prior_dependency=prior, numerical_task_id=None,
            task_materialization_allowed=False, remaining_saved_path_interval_count=len(calendar)-1-j,
            future_path_reference=dict(channels_reference, json_pointer='/calendar253'),
            future_path_dates=deepcopy(calendar[j+1:]), identity_coverage_not_verified=True))
    blockers = ['DRAFT_DECISION_CONTRACT_NOT_REGISTERED', 'PER_PERIOD_SELECTION_NOT_SUPPLIED',
                'CONDITIONAL_POOL_NOT_COMPLETE_PIT_NDX']
    for key in ('selection_contract_reference', 'search_budget_reference'):
        blockers.append(('MISSING_' if contract[key] is None else 'UNVERIFIED_') + key.upper())
    result = dict(schema=SCHEMA, status='PREPARED_CONDITIONAL_SLICES_NOT_EXECUTABLE',
        periods=prepared, decision_count=len(prepared), explicit_decision_contract=deepcopy(contract),
        input_references=dict(channels=deepcopy(channels_reference), decision_path=deepcopy(decision_path_reference)),
        fit_contract=deepcopy(fit_contract), full_inventory=deepcopy(inventory), security_count=len(inventory),
        issuer_count=len(counts)-1, all_k_issuer_unique_combination_counts=[dict(k=k, combination_count=v) for k,v in enumerate(counts) if k],
        full_combination_count=sum(counts[1:]), pool_scope='CONDITIONAL_SUPPLIED_POOL_NOT_CERTIFIED_FULL_NDX',
        evaluation_tracks=['continuous', 'whole_lot'], research_blockers=blockers,
        original_coordinate_evidence=deepcopy(coordinates), original_provenance_and_missing=deepcopy(provenance),
        original_channel_evidence=[dict(source_reference=dict(channels_reference, json_pointer=f'/rows/{n}'),
            row_metadata={k:deepcopy(v) for k,v in row.items() if k != 'channel'},
            channel_metadata={k:deepcopy(v) for k,v in row['channel'].items()
                if k not in ('quote_rows','return_rows','training_returns','evaluation_returns')},
            saved_numeric_payload_references={k:dict(channels_reference,json_pointer=f'/rows/{n}/channel/{k}',
                saved_payload_sha256=digest(row['channel'][k]))
                for k in ('quote_rows','return_rows','training_returns','evaluation_returns') if k in row['channel']})
            for n,row in enumerate(rows)],
        preserved_evidence_sidecars=deepcopy(source['preserved_evidence_sidecars']),
        preserved_sidecar_references=deepcopy(source['preserved_sidecar_references']),
        original_identity_assumed_window=deepcopy(source['original_identity_assumed_window']),
        evaluation_prior_fit_overlap_evidence=deepcopy(source['evaluation_prior_fit_overlap_evidence']),
        historical_retrospective_only=True, source_metadata_preserved={k:deepcopy(v) for k,v in source.items() if k != 'rows'},
        **FLAGS)
    result['content_sha256'] = digest(result)
    return result

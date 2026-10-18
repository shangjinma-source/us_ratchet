"""Independent complete daily-chain projection check; no producer calls."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from fractions import Fraction
import json
import math
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def same(left, right):
    require(encode(left) == encode(right), 'Independent exact chain projection mismatch')


def rational(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def original_weight_sum(session, weights, chains, dates):
    require(type(weights) is dict and type(chains) is dict and type(dates) is dict, 'Saved mappings required')
    require(weights.keys() == chains.keys() == dates.keys(), 'Independent exact SID coverage')
    sums = {}
    for sid in weights:
        number, label, observed = weights[sid], chains[sid], dates[sid]
        require(type(sid) is str and bool(sid), 'Original SID')
        require(type(number) in (int, float) and (type(number) is int or math.isfinite(number)), 'Finite saved numeric weight')
        weight = Fraction(Decimal(repr(number)))
        require(0 <= weight <= 1, 'Saved weight unit interval')
        require(type(label) is str and bool(label), 'Saved chain identity')
        require(type(observed) is str and date.fromisoformat(observed).isoformat() == observed and observed <= session, 'Saved nonfuture chain date')
        sums[label] = sums.get(label, Fraction()) + weight
    total = sum(sums.values(), Fraction())
    require(not weights or total > 0, 'Nonempty zero sum is not cash')
    result = dict(schema='SAVED_WEIGHT_CHAIN_AGGREGATION_V1', session=session,
                  status='DERIVED_SUM_OF_ORIGINAL_SAVED_WEIGHTS' if weights else 'EMPTY_WEIGHT_SET_UNDEFINED',
                  chain_weights={k: rational(sums[k]) for k in sorted(sums)}, total_saved_weight=rational(total),
                  maximum_chain_weight=rational(max(sums.values())) if sums else None,
                  numeric_basis='EXACT_RATIONAL_SUM_OF_SAVED_JSON_DECIMAL_WEIGHTS')
    result.update(dict.fromkeys(('normalization_performed', 'original_saved_chain_aggregate', 'source_bytes_authenticated',
                                'order_gate_evaluated', 'account_executed', 'point_in_time_verified', 'promotion_allowed'), False))
    return result


def inspect_chain_projection(*, projection, supplement_document, diagnostics_document, references):
    require(set(references) == {'supplement', 'diagnostics'}, 'Two fixed input references')
    for reference in references.values():
        require(type(reference) is dict and set(reference) == {'path', 'sha256'} and
                type(reference['path']) is str and bool(reference['path']) and
                type(reference['sha256']) is str and re.fullmatch('[0-9a-f]{64}', reference['sha256']), 'Input reference')
    require(supplement_document['schema'] == 'MULTIDECISION_HOLDINGS_SUPPLEMENT_DOCUMENT_V1', 'Supplement role')
    require(diagnostics_document['schema'] == 'CANDIDATE_SAVED_RISK_DIAGNOSTIC_DOCUMENT_V1', 'Diagnostic role')
    source = supplement_document['supplement']
    require(source['schema'] == 'MULTIDECISION_SAVED_HOLDINGS_SUPPLEMENT_V1', 'Original supplement body')
    for body in (source, diagnostics_document):
        require(body['point_in_time_verified'] is False and body['promotion_allowed'] is False, 'Original authority boundary')
    same(diagnostics_document['input_references']['inputs'], source['references']['candidate_inputs'])
    same(diagnostics_document['input_references']['execution'], source['references']['candidate_execution'])
    calendar = source['calendar']
    require(len(calendar) == 120 and calendar == sorted(set(calendar)), 'Complete calendar')
    require(all(type(d) is str and date.fromisoformat(d).isoformat() == d for d in calendar), 'ISO dates')
    same([x['track_index'] for x in diagnostics_document['paths']], [8, 10, 12, 14])
    same(diagnostics_document['blocked_track_indices'], list(range(8)))
    blocked = source['tables'][5]
    require(blocked['name'] == '未执行阻断轨道' and len(blocked['rows']) == 8, 'Original blocked table')
    same([r[1] for r in blocked['rows']], list(range(8)))
    paths, days, chains_table, evidence_table, counts = [], [], [], [], {}
    for role in ('candidate', 'control'):
        bundles = source['original_raw_bundles_preserved'][role]
        require(len(bundles) == 16, 'All sixteen original slots')
        for index, bundle in enumerate(bundles):
            coordinate = [('STRICT_SAME_SESSION_FX', 'BACKWARD_LATEST_VALID_FX')[index // 8],
                          ('RETURN', 'BAD_TAIL', 'DRAWDOWN', 'TARGET_ENVELOPE')[(index % 8) // 2],
                          ('CONTINUOUS', 'WHOLE_LOT')[index % 2]]
            if role == 'candidate' and index < 8:
                require(bundle is None, 'No synthetic blocked RAW')
                paths.append(dict(role=role, track_index=index, coordinate=coordinate,
                                  status='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT', rows=None,
                                  original_blocked_row=deepcopy(blocked['rows'][index])))
                continue
            require(type(bundle) is dict, 'Returned original RAW')
            raw = bundle['document']
            require(raw['returned'] is True and raw['error'] is None, 'Successful saved result')
            daily = raw['result']['daily']
            same([r['session'] for r in daily], calendar)
            diagnostic_path = None
            if role == 'candidate' and index % 2 == 0:
                diagnostic_path = diagnostics_document['paths'][(index - 8) // 2]
                same(diagnostic_path['coordinate'], coordinate)
                same(diagnostic_path['raw_reference'], bundle['reference'])
                same([r['daily_index'] for r in diagnostic_path['projection']['rows']], list(range(120)))
            count = counts.setdefault(role + '_' + coordinate[-1], dict(days=0, numeric=0, undefined=0))
            rows = []
            for number, original in enumerate(daily):
                locator = dict(reference=deepcopy(bundle['reference']), json_pointer=f'/result/daily/{number}')
                aggregate = None
                if index % 2:
                    basis = 'DERIVED_SUM_OF_SAVED_WHOLE_SID_WEIGHTS_NO_RENORMALIZATION'
                    shares = original['shares']
                    require(type(shares) is dict and all(type(q) is int and q >= 0 for q in shares.values()), 'Original integer shares')
                    held = {sid for sid, quantity in shares.items() if quantity > 0}
                    weights = original['risk']['actual_weights'] if held else original['risk'].get('actual_weights', {})
                    labels, observed = original['risk_chains'], original['risk_chain_observation_dates']
                    require(bool(weights) == bool(held) and held <= set(weights), 'Whole saved holding coverage')
                    evidence = dict(weights=deepcopy(weights), chains=deepcopy(labels), observation_dates=deepcopy(observed))
                    if weights:
                        aggregate = original_weight_sum(original['session'], weights, labels, observed)
                        values = aggregate['chain_weights']
                    else:
                        require(not labels and not observed, 'No labels fabricated for empty holdings')
                        values = None
                elif role == 'control':
                    basis = 'ORIGINAL_SAVED_CONTROL_CONTINUOUS_CHAIN_WEIGHTS'
                    weights = original['risk']['actual_weights']
                    require(bool(weights) == bool(original['holdings']), 'Control original empty state')
                    values = deepcopy(original['risk'].get('risk_chain_weights'))
                    require((type(values) is dict and bool(values)) if weights else values is None, 'Original control risk availability')
                    evidence = dict(risk=deepcopy(original['risk']))
                else:
                    basis = 'PREVIOUSLY_AUDITED_CANDIDATE_CONTINUOUS_DERIVED_CHAIN_WEIGHTS'
                    saved = diagnostic_path['projection']['rows'][number]
                    diagnostic = saved['diagnostic']
                    same(diagnostic['session'], original['session'])
                    require((diagnostic['metrics'] is not None) == bool(original['holdings']), 'Candidate original empty state')
                    values = deepcopy(diagnostic['chain_weights']) if diagnostic['metrics'] is not None else None
                    if values is None:
                        same(diagnostic['chain_weights'], {})
                    evidence = deepcopy(saved)
                    locator['diagnostic_locator'] = dict(reference=deepcopy(references['diagnostics']),
                                                        json_pointer=f'/paths/{(index - 8) // 2}/projection/rows/{number}')
                status = 'EMPTY_HOLDINGS_UNDEFINED' if values is None else 'DEFINED'
                count['days'] += 1
                count['undefined' if values is None else 'numeric'] += 1
                rows.append(dict(session=original['session'], daily_index=number, status=status, basis=basis,
                                 chain_weights=values, original_evidence=evidence, new_aggregation=aggregate, source_locator=locator))
                prefix = [role, index] + coordinate + [original['session']]
                days.append(prefix + [status, basis, None if values is None else encode(values), encode(locator)])
                if values is None:
                    chains_table.append(prefix + [status, basis, None, None, encode(locator)])
                else:
                    for label, weight in values.items():
                        chains_table.append(prefix + [status, basis, label, encode(weight), encode(locator)])
                evidence_table.append(prefix + [encode(evidence), None if aggregate is None else encode(aggregate), encode(locator)])
            paths.append(dict(role=role, track_index=index, coordinate=coordinate, status='RETURNED',
                              raw_reference=deepcopy(bundle['reference']), rows=rows))
    expected_counts = {'candidate_CONTINUOUS': dict(days=480, numeric=476, undefined=4),
                       'candidate_WHOLE_LOT': dict(days=480, numeric=392, undefined=88),
                       'control_CONTINUOUS': dict(days=960, numeric=952, undefined=8),
                       'control_WHOLE_LOT': dict(days=960, numeric=952, undefined=8)}
    same(counts, expected_counts)
    headers = ['角色', '轨道序号', 'FX', 'lane', '账户轨', '日期']
    tables = [dict(name='全部每日链口径', headers=headers + ['状态', '数值来源口径', '链权重原值JSON', '来源'], rows=days),
              dict(name='逐链每日权重', headers=headers + ['状态', '数值来源口径', '风险链', '权重精确原文', '来源'], rows=chains_table),
              dict(name='链投影原证据', headers=headers + ['原证据JSON', '新聚合JSON', '来源'], rows=evidence_table), deepcopy(blocked)]
    expected = dict(schema='MULTIDECISION_DAILY_CHAIN_PROJECTION_V1', calendar=deepcopy(calendar), paths=paths,
                    counts_by_role_track=counts, day_count=2880, numeric_day_count=2772, undefined_day_count=108,
                    blocked_path_count=8, tables=tables, references=deepcopy(references),
                    new_saved_weight_chain_addition_performed=True, original_saved_chain_aggregate_for_all_rows=False,
                    remaining_gaps=['WORKBOOK_EXPORT_AND_FULL_CELL_READBACK', 'FORMAL_VISUAL_ACCEPTANCE_NOT_YET_PERFORMED'])
    expected.update(dict.fromkeys(('account_executed', 'risk_gate_recomputed', 'normalization_performed', 'point_in_time_verified',
                                   'promotion_allowed', 'source_bytes_authenticated', 'historical_label_validity_verified', 'full_h_delivery_complete'), False))
    same(projection, expected)
    return dict(status='PASS_COMPLETE_DAILY_CHAIN_PROJECTION', day_count=2880, numeric_day_count=2772,
                undefined_day_count=108, blocked_path_count=8, counts_by_role_track=counts,
                account_executed=False, risk_gate_recomputed=False, normalization_performed=False,
                point_in_time_verified=False, promotion_allowed=False)

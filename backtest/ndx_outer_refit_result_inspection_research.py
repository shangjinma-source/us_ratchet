"""Independent saved outer-result arithmetic; no fitter, IO or source authentication."""
from datetime import date
import hashlib
import json
import math


PARAMETERS = dict(fit_days=126, shrinkage_intensity=.35, turnover_anchor_strength=.25,
                  max_single_weight=.45, min_single_weight=.05, top_weight_cap=.8,
                  minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def same(actual, expected, label):
    if encoded(actual) != encoded(expected):
        raise ValueError(label)


def require(condition, label):
    if not condition:
        raise ValueError(label)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'Finite nonboolean number')
    return float(value)


def inspect_saved_outer_result(*, request, result, fitter_contract):
    """Check a returned result, including honest risk failures, without reoptimizing."""
    identity = request['numerical_identity']
    same(identity['parameters'], PARAMETERS, 'Frozen eight parameters')
    same(fitter_contract['parameters'], PARAMETERS, 'Fitter parameters')
    require(identity['schema'] == 'ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1', 'Identity schema')
    require(request['numerical_task_id'] == hashlib.sha256(encoded(identity)).hexdigest(), 'Numerical identity digest')
    selected = identity['selected']; securities = sorted(selected)
    require(bool(securities), 'Nonempty selected identities')
    for security in securities:
        require(type(security) is str and security == security.strip() and bool(security), 'Canonical SID')
        require(set(selected[security]) == {'ticker', 'issuer_id', 'risk_chain'}, 'Exact selected fields')
        for value in selected[security].values():
            require(type(value) is str and value == value.strip() and bool(value), 'Canonical identity')
    tickers = [selected[s]['ticker'] for s in securities]
    require(all(t == t.upper() for t in tickers) and len(set(tickers)) == len(tickers), 'Unique uppercase tickers')
    require(len({selected[s]['issuer_id'] for s in securities}) == len(securities), 'One security per issuer')
    same(identity['holding_count'], len(securities), 'Holding count')
    matrix = request['fit_matrix']
    require(set(matrix) == {'dates', 'tickers', 'returns'}, 'Exact matrix schema')
    same(matrix['tickers'], tickers, 'Sorted SID column order')
    dates = matrix['dates']
    require(len(dates) == 126 and dates == sorted(set(dates)), '126 unique ascending dates')
    require(all(type(d) is str and date.fromisoformat(d).isoformat() == d for d in dates), 'Canonical dates')
    same(dates[-1], identity['cutoff'], 'Exact cutoff')
    require(len(matrix['returns']) == 126, '126 return slots')
    for row in matrix['returns']:
        require(len(row) == len(securities), 'Complete return columns')
        for value in row:
            require(type(value) is float and number(value) > -1., 'Original binary64 returns')
    matrix_hash = hashlib.sha256(encoded(matrix)).hexdigest()
    same(identity['fit_data_sha256'], matrix_hash, 'Identity matrix hash')
    require(result['schema'] == 'ndx_dynamic_cutoff_refit_research_v2', 'Frozen v2 result')
    for key, expected in dict(cutoff=dates[-1], fit_start=dates[0], fit_end=dates[-1],
                              fit_row_count=126, fit_data_sha256=matrix_hash,
                              weight_spec=identity['weight_spec']).items():
        same(result[key], expected, key)
    require(identity['weight_spec'] in {'equal_weight', 'constrained_fixed_shrinkage',
                                      'constrained_fixed_shrinkage_turnover_anchor'}, 'Weight specification')
    same(result['declared_parameters'], {k:v for k,v in PARAMETERS.items() if k != 'fit_days'}, 'Seven declared bounds')
    same(result['source_hashes'], fitter_contract['source_hashes'], 'Source declarations')
    same(identity['fitter_source_fingerprint'], hashlib.sha256(encoded(fitter_contract['source_hashes'])).hexdigest(), 'Source fingerprint')
    previous = identity['requested_previous_target_weights']
    if previous is None:
        previous = {}
    else:
        require(type(previous) is dict and bool(previous), 'Prior None or nonempty mapping')
        require(all(type(s) is str and bool(s) and s == s.strip() for s in previous), 'Canonical prior SID keys')
        require(all(number(v) >= 0 for v in previous.values()) and math.isclose(sum(previous.values()), 1., abs_tol=1e-12, rel_tol=0), 'Original prior simplex')
    same(result['previous_target_weights'], previous, 'Requested prior preserved')
    mass = sum(previous.get(s, 0.) for s in securities)
    anchor = {s:previous.get(s, 0.)/mass if mass > 0 else 0. for s in securities}
    same(result['surviving_anchor_mass'], mass, 'Ordered surviving mass')
    same(result['anchor_by_security'], anchor, 'Normalized surviving anchor')
    same(result['effective_anchor_strength'], .25 if mass > 0 and identity['weight_spec'] == 'constrained_fixed_shrinkage_turnover_anchor' else 0., 'Effective anchor')
    same(result['anchor_policy'], 'SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED', 'Anchor policy')
    require(set(result['targets']) == set(securities), 'Complete target set')
    weights = {}; groups = {}
    for security in securities:
        target = result['targets'][security]
        require(set(target) == {'ticker', 'issuer_id', 'target_weight'}, 'Target schema')
        for key in ('ticker', 'issuer_id'):
            same(target[key], selected[security][key], 'Target identity')
        weights[security] = number(target['target_weight'])
        require(weights[security] >= 0, 'Nonnegative fitted target')
        chain = selected[security]['risk_chain']
        groups[chain] = groups.get(chain, 0.) + weights[security]
    total = sum(weights.values())
    require(math.isclose(total, 1., abs_tol=1e-9, rel_tol=0), 'Original returned simplex')
    if identity['weight_spec'] == 'equal_weight':
        same(weights, {s:1./len(securities) for s in securities}, 'Equal weight arithmetic')
    ordered = sorted(weights.values(), reverse=True)
    checks = dict(MAX_SINGLE_WEIGHT=ordered[0] <= .45+1e-9,
                  MIN_SINGLE_WEIGHT=ordered[-1] >= .05-1e-9,
                  SECURITY_TOP3_WEIGHT=sum(ordered[:3]) <= .8+1e-9,
                  MINIMUM_EFFECTIVE_N=1./sum(v*v for v in weights.values()) >= len(weights)*.7-1e-9,
                  RISK_CHAIN_TOP1_WEIGHT=max(groups.values()) <= .55+1e-9)
    same(result['declared_constraint_checks'], checks, 'Five original risk observations')
    same(result['declared_constraints_passed'], all(checks.values()), 'Risk outcome')
    same(result['risk_chains_by_security'], {s:selected[s]['risk_chain'] for s in securities}, 'Original risk chain mapping')
    require(type(result['risk_chain_projection_relaxed']) is bool, 'Retained solver diagnostic')
    constrained = identity['weight_spec'] != 'equal_weight'
    same(result['single_name_projection_relaxed'], constrained and .45 < 1./len(weights), 'Single-name relaxation diagnostic')
    same(result['top3_projection_semantics_relaxed'], constrained and (len(weights) <= 3 or .8 < min(3,len(weights)-1)/len(weights)), 'Top3 relaxation diagnostic')
    same(result['numerical_projection'], 'V3_CERTIFIED_RECOVERY_ORIGINAL_PROBE_CLOSURE', 'Projection version')
    recovery = result['projection_reconstruction_audit']
    same(recovery['schema'], 'ndx_projection_reconstruction_audit_v1', 'Recovery schema')
    same(recovery['scope'], 'NUMERICAL_PROJECTION_RECOVERY_NOT_ECONOMIC_QUALIFICATION', 'Recovery scope')
    require(type(recovery['attempts']) is list, 'Saved recovery attempts')
    same(recovery['attempt_count'], len(recovery['attempts']), 'Recovery attempt count')
    require(recovery['prior_results_reused'] is False and recovery['promotion_allowed'] is False, 'Recovery permissions')
    for key in ('checkpoint_weights_used', 'point_in_time_verified', 'source_authenticity_verified',
                'promotion_allowed', 'historical_task_evaluation_performed', 'order_generation_allowed'):
        require(result[key] is False, 'Research permission '+key)
    return dict(schema='OUTER_REFIT_SAVED_RESULT_ARITHMETIC_INSPECTION_V1',
                status='PASS_SAVED_ARITHMETIC', numerical_task_id=request['numerical_task_id'],
                fit_data_sha256=matrix_hash, risk_checks=checks, declared_risks_passed=all(checks.values()),
                next_prior_simplex_eligible=math.isclose(total, 1., abs_tol=1e-12, rel_tol=0),
                reconstruction_attempt_details_verified=False,
                numerical_optimality_verified=False, source_bytes_authenticated=False,
                fit_performed=False, promotion_allowed=False, order_generation_allowed=False)

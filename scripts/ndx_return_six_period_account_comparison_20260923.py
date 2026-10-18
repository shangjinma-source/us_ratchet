"""Independent new-account readback only; no producer, engine, or old identity import."""
import argparse
from copy import deepcopy
from decimal import Context, Decimal, localcontext
import hashlib
from importlib.metadata import version
from importlib.util import find_spec
import json
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_frozen_accounting_independent_audit_research as accounting
from backtest import ndx_frozen_target_normalization_audit_research as normalization
from backtest import ndx_root_price_archive_contract_research as archive

BASE = ROOT / 'data/cache/research'
SOURCE = Path(__file__).resolve()
PRODUCER = ROOT / 'scripts/ndx_return_six_period_conditional_execution_v2_20260923.py'
PRODUCER_SHA = '836a271ae0c7fd6d6fceb35d686736319625786cf7ca34bb60d56725e1e5d8e3'
PRIOR_PRODUCER = ROOT / 'scripts/ndx_return_six_period_conditional_execution_20260923.py'
PRIOR_PRODUCER_SHA = '103cbf56bf665a54a942257ffc28f542121ae0777d6ce2b988146ad08715f0d4'
ACCOUNT_DIRECTORY = BASE / 'return_six_period_conditional_execution_20260923_v2'
CANDIDATE_SHA = 'ed69a9de921d94f9a186d59a6ef16c09f46544ede388e4fff271c10a77f433e2'
BOUND = {
    'v1_started': ('return_six_period_conditional_execution_20260923_v1/started.json', 'dd2ad9f804eca0cbf6bc866b68eb21d645dad38e33e611d1bd6d7ace2d23b886'),
    'v1_failure': ('return_six_period_conditional_execution_20260923_v1/failure.json', '6a594080e9dfb35584b11a22aa00513eaf049d564d42bdf27f42e65e693550f3'),
    'schedule': ('return_lane_targets_20260923_v1/schedule.json', 'f5ee54df3651882791e4e6ecac548d0ec7847c44a9c551938d20c17c2cb23c70'),
    'audit': ('return_lane_targets_20260923_v1/completed6_independent_readback.json', 'ca8bf38f5090c9703da2ed8094421d3abae4324fd7837097f82ef0546b94778f'),
    'linkage': ('return_lane_targets_20260923_v1/schedule_independent_linkage.json', 'f1529817338a022bb9831de9e4d08407a7eb7015098e085e43ea37506ac8ed0b'),
    'price': ('return_eight_price_only_20260923_v1/raw_assembly.json', 'e1f00af594bfcb9a9c75b02493cf62fc64622e0b280ba2774346832b530b7336'),
    'price_final': ('return_eight_price_only_20260923_v1/finalization.json', '5f5714e66b906d02c33006e7b556177cd20945c0afca0a4d400df4e2073e2b9a'),
    'identity': ('return_eight_conditional_identity_20260923_v1/identities.json', '5f5bcbad2f5a3a340e0b3449b4b78ed55a44941d6402a4ee067dd779a4abaa6e'),
    'benchmark': ('return_six_period_benchmarks_20260923_v1/benchmarks.json', 'ef7ccdbe45a95fdf616d1b681bf9cd5c431db01585d30cf979e5cd4f2d45b423'),
}
INPUT_ROLES = tuple(k for k in BOUND if k != 'benchmark')
CLOCK = [['2023-03-31', '2023-04-03'], ['2023-04-28', '2023-05-01'],
         ['2023-05-31', '2023-06-01'], ['2023-06-30', '2023-07-03'],
         ['2023-07-31', '2023-08-01'], ['2023-08-31', '2023-09-01']]
CONTRACT = dict(initial_cash_usd=25000, minimum_cash_buffer_usd=100, transaction_cost_bps=10,
                max_single_weight=.45, min_single_weight=.05, top_weight_cap=.8,
                minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55)
SCHEMA = 'RETURN_SIX_PERIOD_CONDITIONAL_ACCOUNT_V2'
CANDIDATE_FALSE = ('fit_performed', 'point_in_time_verified', 'promotion_allowed', 'live_execution_authorized',
                   'provider_binding_verified', 'continuous_identity_interval_verified',
                   'corporate_action_completeness_verified', 'dividend_cash_flows_modelled',
                   'additional_cash_flows_supported', 'historical_full_source_closure_recovered')
FALSE = CANDIDATE_FALSE + ('execution_rerun', 'winner_selected', 'formal_eight_dimension_evaluation',
                         'out_of_sample_evaluation', 'nav_publication_time_verified',
                         'currency_fx_equivalence_verified', 'subscription_redemption_fee_equivalence_verified')
LOADED = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
          (SOURCE, Path(accounting.__file__).resolve(), Path(normalization.__file__).resolve(),
           archive.SOURCE, Path(archive.drift.__file__).resolve())}
FROZEN = {
    str(Path(accounting.__file__).resolve()): '3fb63dbf58e94eb92fd93bf39cca8fdefe52fdb4853bf9abd7d63a0a391fe7dc',
    str(Path(normalization.__file__).resolve()): '32c9fd773a35465152f567ca1f3c314d3663191f2a8e53a41a1ce6dafe39ce2f',
}
ENGINE_SOURCES = {str(ROOT / 'backtest' / name): sha for name, sha in {
    'ndx_dynamic_frozen_execution_research.py': '69d2bf761eac32edd8c39a9fdbffed300ba7cb4740771fbd008b4f09b204813b',
    'ndx_dynamic_whole_lot_path.py': '3ad63f1e59baaa14c32eceddd32340755a516c1022077bd802763d10ef360a95',
    'ndx_dynamic_whole_lot_repair_path.py': 'e614be1a2fe461e483e17413af03153f9a2fe99c31e0412b5daa8954c53d3f34',
    'ndx_whole_lot_repair_diagnostic.py': 'e2f00388b92c88588acaff51c30c608830bf93a00cfc6a84ad8e20a9470381bf',
    'ndx_split_accounting_research.py': '11bb5225e90c76fe303e90fa9f639e34c3978fd922d230bb2a45f8f9ad24877c',
}.items()}
RUNTIME_LOADED = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  [Path(sys.executable).resolve(), *[Path(find_spec(name).origin).resolve()
                                                    for name in ('numpy', 'pandas', 'scipy')]]}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def exact(left, right):
    return encode(left) == encode(right)


def reference(role):
    path, sha = BOUND[role]
    return dict(path=str(BASE / path), sha256=sha)


def runtime():
    archive.strict(RUNTIME_LOADED)
    return dict(python=platform.python_version(), executable=str(Path(sys.executable).resolve()),
                **{name: version(name) for name in ('numpy', 'pandas', 'scipy')},
                runtime_entry_file_hashes=RUNTIME_LOADED, full_binary_dependency_closure_verified=False)


def number(value):
    require(type(value) in (str, int, float, Decimal), 'Nonboolean number required')
    result = Decimal(str(value))
    require(result.is_finite(), 'Finite number required')
    return result


def metrics(values):
    require(len(values) == 107, '107 observations and 106 intervals required')
    with localcontext(Context(prec=60)):
        values = [number(v) for v in values]
        require(all(v > 0 for v in values), 'Positive equity required')
        ratio = values[-1] / values[0]
        peak, drawdown = values[0], Decimal(0)
        for value in values:
            peak = max(peak, value)
            drawdown = max(drawdown, 1 - value / peak)
        return dict(path_return=str(ratio - 1), path_max_drawdown=str(drawdown),
                    annualized_return_252_over_106=str(ratio ** (Decimal(252) / 106) - 1),
                    observation_count=107, return_interval_count=106,
                    annualization_is_historical_window_diagnostic=True)


def audit_raw(candidate, started, raw, identities):
    require(candidate['schema'] == SCHEMA and candidate['status'] == 'INDEPENDENT_ACCOUNTING_PASSED', 'Final schema/status differs')
    require(started['schema'] == SCHEMA + '_STARTED' and raw['schema'] == SCHEMA + '_RAW', 'Attempt schema differs')
    for document in (candidate, started, raw):
        require(all(document[k] is False for k in CANDIDATE_FALSE), 'Conditional scope upgraded')
        require(exact(document['source_hashes'], started['source_hashes']) and
                exact(document['runtime'], started['runtime']), 'Attempt source/runtime mismatch')
    require(started['automatic_retry_allowed'] is False and candidate['execution_performed'] is True,
            'Saved single-attempt execution required')
    require(type(candidate['engine_call_count']) is int and candidate['engine_call_count'] == 1 and
            type(raw['engine_call_count']) is int and raw['engine_call_count'] == 1, 'Exactly one saved engine call required')
    require(raw['started_reference'] == candidate['started_reference'], 'Raw attempt reference differs')
    require(started['input_references'] == {role: reference(role) for role in INPUT_ROLES}, 'Exact inputs and historical failure references required')
    validation = dict(frozen_price_index_validators_called=True, frozen_schedule_and_contract_validators_called=True,
                      normalized_copy_discarded=True, submitted_schedule_modified=False, simulate_called=False,
                      session_count=107, security_column_count=8, decision_count=6)
    for document in (started, candidate):
        require(exact(document['engine_input_validation'], validation) and
                type(document['historical_v1_engine_attempt_count']) is int and document['historical_v1_engine_attempt_count'] == 1 and
                type(document['historical_v1_complete_ledger_count']) is int and document['historical_v1_complete_ledger_count'] == 0,
                'Historical failure or validation evidence differs')
    for key in ('calendar', 'schedule', 'internal_columns', 'execution_contract', 'normalization_evidence', 'price_conversion_evidence', 'engine_input_validation'):
        require(exact(started[key], candidate[key]), 'Started input changed: ' + key)
    labels = {r['security_id']: r['ticker'] for r in identities['rows']}
    columns = {sid: 'SID_' + sid.split(':')[1] + '_' + sid.split(':')[2] for sid in labels}
    require(candidate['internal_columns'] == columns, 'SID column map differs')
    restored = deepcopy(raw['execution'])
    for row in restored['decisions']:
        for sid, target in row['targets'].items():
            require(target['ticker'] == columns[sid], 'Raw decision column differs')
            target['ticker'] = labels[sid]
    for row in restored['trades']:
        sid = row['security_id']
        require(row['ticker'] == columns[sid], 'Raw trade column differs')
        row['ticker'] = labels[sid]
    for row in restored['daily']:
        require(row['tickers'] == {sid: columns[sid] for sid in row['shares']}, 'Raw daily columns differ')
        row['tickers'] = {sid: labels[sid] for sid in row['shares']}
    require(exact(restored, candidate['execution']), 'Ledger changed beyond label restoration')


def share_class_transition(execution):
    old = 'security:0001652044:02079K107'
    new = 'security:0001652044:02079K305'
    fills = [r for r in execution['executions'] if r['session'] == '2023-09-01']
    require(len(fills) <= 1, 'Duplicate transition execution')
    if not fills:
        return dict(status='NO_FROZEN_EXECUTION', class_conversion_inferred=False)
    fill = fills[0]
    trades = [r for r in execution['trades'] if r['session'] == fill['session'] and r['security_id'] in (old, new)]
    if fill['status'] == 'REJECTED':
        require(not trades and fill['shares_before'] == fill['shares_after'], 'Rejected transition altered holdings')
    else:
        require(fill['status'] == 'FILLED' and fill['shares_after'].get(old, 0) == 0, 'Old Class C position not closed')
        for sid in (old, new):
            delta = fill['shares_after'].get(sid, 0) - fill['shares_before'].get(sid, 0)
            observed = [r for r in trades if r['security_id'] == sid]
            require(len(observed) == (1 if delta else 0), 'Separate SID trade missing')
            if delta:
                require(observed[0]['share_delta'] == delta and number(observed[0]['transaction_cost_usd']) > 0,
                        'Complete separate buy/sell with fees required')
    return dict(status=fill['status'], class_c_shares_before=fill['shares_before'].get(old, 0),
                class_c_shares_after=fill['shares_after'].get(old, 0),
                class_a_shares_before=fill['shares_before'].get(new, 0),
                class_a_shares_after=fill['shares_after'].get(new, 0), separate_trade_count=len(trades),
                class_conversion_inferred=False)


def audit_candidate(candidate, schedule, price, identities):
    calendar = price['calendar']
    require(len(calendar) == 107 and calendar == sorted(set(calendar)) and
            calendar[0] == '2023-03-31' and calendar[-1] == '2023-09-01', 'Exact calendar required')
    require(candidate['calendar'] == calendar == [d for d in schedule['calendar'] if calendar[0] <= d <= calendar[-1]], 'Calendar linkage differs')
    require(exact(candidate['schedule'], schedule['schedule']) and
            [[r['decision_date'], r['execution_date']] for r in candidate['schedule']] == CLOCK, 'Exact six-decision clock required')
    require(identities['conditional_window'] == dict(start=calendar[0], end=calendar[-1]), 'Identity window differs')
    labels = {r['security_id']: r for r in identities['rows']}
    require(type(candidate['security_count']) is int and candidate['security_count'] == 8 and
            type(candidate['distinct_issuer_count']) is int and candidate['distinct_issuer_count'] == 7 and
            candidate['fixed_four_security_policy'] is False and
            candidate['per_decision_target_counts'] == [len(r['targets']) for r in candidate['schedule']] and
            candidate['goog_googl_relationship'] == 'DIFFERENT_SECURITY_IDS_SAME_ISSUER_NOT_A_RENAME', 'Candidate security semantics differ')
    require(len(labels) == len(identities['rows']) == 8 and len({r['issuer_id'] for r in labels.values()}) == 7, '8 SID / 7 issuer denominator required')
    require(set(price['tickers']) == {r['ticker'] for r in labels.values()} and len(price['tickers']) == 8, 'Price identity union differs')
    require(set().union(*(r['targets'] for r in candidate['schedule'])) == set(labels), 'Target union differs')
    for decision in candidate['schedule']:
        require(calendar[calendar.index(decision['decision_date']) + 1] == decision['execution_date'], 'Next observed session differs')
        require(len({v['issuer_id'] for v in decision['targets'].values()}) == len(decision['targets']), 'Duplicate issuer within decision')
        for sid, target in decision['targets'].items():
            require(all(target[k] == labels[sid][k] for k in ('ticker', 'issuer_id')), 'Target identity mismatch')
    require(set(candidate['execution_contract']) == set(CONTRACT) and
            all(number(candidate['execution_contract'][k]) == number(v) for k, v in CONTRACT.items()), 'Fixed capital/risk/fee contract differs')
    normalized, evidence = normalization.normalized_schedule(candidate['schedule'])
    require(exact(normalized, candidate['normalized_schedule']) and exact(evidence, candidate['normalization_evidence']), 'Single normalization differs')
    marks = {day: {} for day in calendar}
    conversion = []
    for kind in ('open', 'close'):
        require(set(price['matrices'][kind]) == set(calendar), 'Price day denominator differs')
        for day in calendar:
            require(set(price['matrices'][kind][day]) == set(price['tickers']), 'Price ticker denominator differs')
            for sid, label in labels.items():
                value = price['matrices'][kind][day][label['ticker']]
                require(type(value) is str and number(value) > 0, 'Exact nominal Decimal price required')
                marks[day].setdefault(sid, dict(ticker=label['ticker']))[kind] = number(value)
                with localcontext(Context(prec=160)):
                    converted = float(Decimal(value))
                    error = abs(Decimal.from_float(converted) - Decimal(value))
                conversion.append(dict(session=day, security_id=sid, field=kind, original_decimal=value,
                                       execution_float=converted, absolute_binary_float_error=str(error)))
    require(exact(candidate['price_conversion_evidence'], dict(
        policy='EXPLICIT_FLOAT_ONLY_AT_FROZEN_ENGINE_BOUNDARY_DECIMAL_MARKS_RETAINED_FOR_INDEPENDENT_AUDIT',
        cell_count=1712, cells=conversion)), 'Decimal to engine-float conversion evidence differs')
    with localcontext(Context(prec=80)):
        result = accounting.audit(execution=candidate['execution'], calendar=calendar, schedule=normalized,
                                  prices=marks, risk_chains_by_decision=schedule['risk_chains_by_decision'], contract=CONTRACT)
    require(exact(result, candidate['independent_decimal_accounting']), 'Embedded accounting differs from independent audit')
    return result, metrics([r['total_value_usd'] for r in candidate['execution']['daily']]), share_class_transition(candidate['execution'])


def compare(benchmark, calendar, candidate_metrics):
    require(benchmark['calendar'] == calendar and benchmark['decision_clock'] == CLOCK, 'Benchmark clock differs')
    for key in ('execution_rerun', 'fitter_called', 'old_control_accounting_repeated', 'risk_projection_recomputed',
                'cash_dividends_modelled', 'historical_full_source_closure_verified', 'point_in_time_verified',
                'formal_dual_benchmark_admission', 'promotion_allowed'):
        require(benchmark[key] is False, 'Benchmark scope upgraded')
    nav, control = benchmark['nav'], benchmark['incumbent']
    require(all(nav[k] is False for k in ('publication_time_verified', 'currency_fx_equivalence_verified',
                                         'subscription_redemption_fee_equivalence_verified')), 'NAV scope upgraded')
    require([r['session'] for r in control['daily']] == calendar == [r['session'] for r in nav['rows']], 'Reference days differ')
    require(all(r['nav_date'] <= r['session'] for r in nav['rows']), 'Future NAV date')
    references = {'original_incumbent': metrics([r['total_value_usd'] for r in control['daily']]),
                  '012922_native_currency_nav': metrics([r['nav'] for r in nav['rows']])}
    require(exact(references['original_incumbent'], control['metrics']) and
            exact(references['012922_native_currency_nav'], nav['metrics']), 'Sealed benchmark metric differs')
    with localcontext(Context(prec=60)):
        differences = {role: {key: str(number(candidate_metrics[key]) - number(value[key]))
                             for key in ('path_return', 'path_max_drawdown', 'annualized_return_252_over_106')}
                       for role, value in references.items()}
    return dict(candidate=candidate_metrics, references=references, candidate_minus_reference=differences,
                difference_semantics='RETURN_POSITIVE_IS_HIGHER_DRAWDOWN_POSITIVE_IS_WORSE_NO_WINNER_OR_ADMISSION')


def build(candidate_path, candidate_sha256, producer_sha256):
    require(PRODUCER_SHA is not None and producer_sha256 == PRODUCER_SHA, 'Externally supplied producer SHA differs from reviewed producer')
    require(candidate_sha256 == CANDIDATE_SHA, 'External candidate SHA differs from the single completed account')
    require(all(LOADED[p] == h for p, h in FROZEN.items()), 'Frozen audit/normalization module differs')
    archive.strict(LOADED)
    sources = dict(LOADED)
    def read(ref):
        path = Path(ref['path']).resolve()
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'Externally bound artifact differs')
        archive.merge(sources, {str(path): ref['sha256']})
        return json.loads(raw, object_pairs_hook=unique)
    docs = {role: read(reference(role)) for role in BOUND}
    candidate_ref = dict(path=str(Path(candidate_path).resolve()), sha256=candidate_sha256)
    require(candidate_ref['path'] == str(ACCOUNT_DIRECTORY / 'account.json'), 'Only the bounded account namespace allowed')
    candidate = read(candidate_ref)
    started = read(candidate['started_reference'])
    raw = read(candidate['raw_reference'])
    require(candidate['runtime'] == runtime(), 'Numerical runtime differs')
    candidate_sources = candidate['source_hashes']
    required = {str(PRODUCER): producer_sha256, str(PRIOR_PRODUCER): PRIOR_PRODUCER_SHA, **FROZEN, **ENGINE_SOURCES,
                str(archive.SOURCE): LOADED[str(archive.SOURCE)],
                str(Path(archive.drift.__file__).resolve()): LOADED[str(Path(archive.drift.__file__).resolve())],
                **{reference(role)['path']: reference(role)['sha256'] for role in INPUT_ROLES}}
    for role in INPUT_ROLES:
        for field in ('source_hashes', 'historical_expected_source_hashes'):
            if field in docs[role]: archive.merge(required, docs[role][field])
    require(exact(candidate_sources, required), 'Candidate source closure differs from independently reconstructed closure')
    archive.merge(sources, RUNTIME_LOADED)
    historical_failure = docs['v1_failure']
    require(historical_failure['schema'] == 'RETURN_SIX_PERIOD_CONDITIONAL_ACCOUNT_V1_FAILURE' and
            historical_failure['started_reference'] == reference('v1_started') and historical_failure['raw_reference'] is None and
            historical_failure['engine_call_started'] is True and historical_failure['automatic_retry_allowed'] is False and
            historical_failure['numerical_failure_is_economic_infeasibility'] is False and
            docs['v1_started']['source_hashes'].get(str(PRIOR_PRODUCER)) == PRIOR_PRODUCER_SHA,
            'Sealed prior failure lineage differs')
    require({p.name for p in (BASE / BOUND['v1_started'][0]).parent.iterdir()} == {'started.json', 'failure.json'},
            'Historical failed attempt unexpectedly contains new evidence')
    failure_ref = candidate['recovered_failure_reference']
    require(candidate['started_reference']['path'] == str(ACCOUNT_DIRECTORY / 'started.json') and
            candidate['raw_reference']['path'] == str(ACCOUNT_DIRECTORY / 'raw_execution.json'), 'Attempt files outside namespace')
    names = {'account.json', 'started.json', 'raw_execution.json'}
    if failure_ref is not None:
        require(failure_ref['path'] == str(ACCOUNT_DIRECTORY / 'failure.json'), 'Failure outside namespace')
        failure = read(failure_ref)
        require(failure['schema'] == SCHEMA + '_FAILURE' and failure['started_reference'] == candidate['started_reference'] and
                failure['raw_reference'] == candidate['raw_reference'] and failure['engine_call_started'] is True and
                failure['automatic_retry_allowed'] is False and failure['numerical_failure_is_economic_infeasibility'] is False and
                all(failure[k] is False for k in CANDIDATE_FALSE), 'Recovery failure linkage differs')
        names.add('failure.json')
    require({p.name for p in ACCOUNT_DIRECTORY.iterdir()} == names and
            all((ACCOUNT_DIRECTORY / name).is_file() for name in names), 'Unexpected attempt evidence/orphans')
    for doc in [candidate, *docs.values()]:
        for field in ('source_hashes', 'historical_expected_source_hashes'):
            if field in doc:
                archive.merge(sources, doc[field])
    require(docs['price_final']['raw_reference'] == reference('price'), 'Price final/raw linkage differs')
    linkage = docs['linkage']
    require(linkage['exact_schedule_reconstruction'] is True and linkage['schedule_reference'] == reference('schedule') and
            linkage['independent_target_audit_reference'] == reference('audit'), 'Schedule independent linkage differs')
    require(docs['audit']['status'] == 'PASSED' and docs['audit']['completed_prefix_count'] == 6, 'Complete six target audit required')
    contract = archive.load_contract()
    resolution = archive.verify_expected_sources(sources, contract)
    require(archive.verify_expected_sources(candidate_sources, contract) == candidate['archive_resolution'], 'Candidate archive partition differs')
    audit_raw(candidate, started, raw, docs['identity'])
    audit, measures, transition = audit_candidate(candidate, docs['schedule'], docs['price'], docs['identity'])
    comparison = compare(docs['benchmark'], candidate['calendar'], measures)
    require(archive.verify_expected_sources(sources, contract) == resolution, 'Sources changed during readback')
    require({p.name for p in ACCOUNT_DIRECTORY.iterdir()} == names, 'Attempt directory changed during readback')
    return dict(schema='RETURN_SIX_PERIOD_CONDITIONAL_COMPARISON_INDEPENDENT_V2', candidate_reference=candidate_ref,
                producer_reference=dict(path=str(PRODUCER), sha256=producer_sha256), calendar=candidate['calendar'],
                decision_clock=CLOCK, independent_accounting=audit, comparison=comparison,
                share_class_transition=transition, normalization_call_count=1, candidate_accounting_audit_call_count=1,
                old_control_accounting_audit_call_count=0, saved_candidate_execution_performed=True,
                attempt_directory_entries=sorted(names), runtime=candidate['runtime'],
                historical_expected_source_hashes=sources, archive_resolution=resolution, **dict.fromkeys(FALSE, False))


def publish(value, output):
    require(Path(output).resolve().parent != ACCOUNT_DIRECTORY, 'Readback must not alter attempt directory')
    contract = archive.load_contract()
    def verify():
        require(archive.verify_expected_sources(value['historical_expected_source_hashes'], contract) == value['archive_resolution'], 'Publication source drift')
        require({p.name for p in ACCOUNT_DIRECTORY.iterdir()} == set(value['attempt_directory_entries']), 'Attempt directory changed')
    verify()
    raw = encode(value)
    with Path(output).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    verify()
    require(Path(output).read_bytes() == raw, 'Published readback differs')
    return dict(path=str(Path(output).resolve()), sha256=hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for key in ('candidate-path', 'candidate-sha256', 'producer-sha256', 'output'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    print(json.dumps(publish(build(args.candidate_path, args.candidate_sha256, args.producer_sha256), args.output)))

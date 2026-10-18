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
PRODUCER = ROOT / 'scripts/ndx_bad_tail_six_period_conditional_execution_20260923.py'
PRODUCER_SHA = 'd9102b873bea5505befcf48eb715ae0fba5b2db80315392f935269367752d0f7'
ACCOUNT_DIRECTORY = BASE / 'bad_tail_six_period_conditional_execution_20260923_v1'
CANDIDATE_SHA='b5135462b51f95510aea2f97e5786fde011d843cfee2891be2661b38a497ff6c'
BOUND = {
    'schedule': ('bad_tail_lane_targets_20260923_v1/schedule.json', '677adb274064b963cfb87290a6d0120a9970e73e65a00d644a9ba8a84d78271e'),
    'audit': ('bad_tail_lane_targets_20260923_v1/completed6_independent_readback.json', '4ef1744ed3ddb8737617ce05847b128fbe873b4c48312bcd8d3fbd8398e798c4'),
    'linkage': ('bad_tail_lane_targets_20260923_v1/schedule_independent_linkage.json', '49b468c4432d7e746c7f02d1d7c5f5b9a07d75fd7be14c7fdffde58726a63c3c'),
    'projection': ('bad_tail_five_input_projection_20260923_v1/projection.json', '77d03b11751322158158b66a18ecf19fd669cacfa730b99c3dbda1139b25e6be'),
    'benchmark': ('return_six_period_benchmarks_20260923_v1/benchmarks.json', 'ef7ccdbe45a95fdf616d1b681bf9cd5c431db01585d30cf979e5cd4f2d45b423'),
}
INPUT_ROLES = tuple(BOUND)
CLOCK = [['2023-03-31', '2023-04-03'], ['2023-04-28', '2023-05-01'],
         ['2023-05-31', '2023-06-01'], ['2023-06-30', '2023-07-03'],
         ['2023-07-31', '2023-08-01'], ['2023-08-31', '2023-09-01']]
CONTRACT = dict(initial_cash_usd=25000, minimum_cash_buffer_usd=100, transaction_cost_bps=10,
                max_single_weight=.45, min_single_weight=.05, top_weight_cap=.8,
                minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55)
SCHEMA = 'BAD_TAIL_SIX_PERIOD_CONDITIONAL_ACCOUNT_V1'
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
    require(started['input_references'] == {role: reference(role) for role in INPUT_ROLES}, 'Exact five input references required')
    validation = dict(frozen_price_index_validators_called=True, frozen_schedule_and_contract_validators_called=True,
                      normalized_copy_discarded=True, submitted_schedule_modified=False, simulate_called=False,
                      session_count=107, security_column_count=5, decision_count=6)
    for document in (started, candidate):
        require(exact(document['engine_input_validation'], validation), 'Frozen input validation evidence differs')
    for key in ('calendar', 'schedule', 'internal_columns', 'execution_contract', 'normalization_evidence', 'price_conversion_evidence', 'engine_input_validation', 'risk_chain_evidence'):
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


def independent_risk_history(schedule,projection,execution):
    """Derive last-selected observations by time lookup, separately from holdings."""
    rows=schedule['schedule'];choices=projection['saved_lane_choices']
    require([[x['decision_date'],x['execution_date']] for x in rows]==CLOCK and
        [[x['decision_date'],x['execution_date']] for x in choices]==CLOCK,'Exact six observation clocks required')
    selected_maps=projection['selected_risk_chains_by_decision']
    require(set(selected_maps)==set(schedule['risk_chains_by_decision'])=={d for d,e in CLOCK},'Risk observation dates differ')
    observations={};expected_evidence={};previous_selected=set()
    def at(day):
        seen={sid:[event for event in events if event[0]<=day] for sid,events in observations.items()}
        seen={sid:events[-1] for sid,events in seen.items() if events}
        return {sid:event[1] for sid,event in seen.items()},{sid:event[0] for sid,event in seen.items()}
    for row,choice in zip(rows,choices,strict=True):
        day=row['decision_date'];selected=choice['saved_candidate']['selected']
        require(set(selected)==set(row['targets']),'Saved lane selection differs from final targets')
        current={sid:v['risk_chain'] for sid,v in selected.items()}
        require(current==selected_maps[day] and all(type(v) is str and v and v.strip()==v for v in current.values()),'Selected risk observations differ')
        for sid,value in selected.items():
            require(all(row['targets'][sid][k]==value[k] for k in ('ticker','issuer_id')),'Selected identity differs')
            observations.setdefault(sid,[]).append((day,value['risk_chain']))
        chains,dates=at(day);provided=schedule['risk_chains_by_decision'][day]
        require(set(provided)==set(selected)|previous_selected and all(provided[sid]==chains[sid] for sid in provided),
            'Schedule union is missing, future or contradicts observed labels')
        expected_evidence[day]=dict(chains=chains,observation_dates=dates,newly_observed_selected_sids=sorted(selected),
            historical_validity_interval_certified=False)
        previous_selected=set(selected)
    decisions=execution['decisions'];fills=execution['executions'];daily=execution['daily']
    require([[d['decision_date'],d['execution_date']] for d in decisions]==CLOCK,'Six actual decisions required')
    expected_fill_dates=[row['execution_date'] for row in decisions if row['status']=='FROZEN']
    require(all(row['status'] in ('FROZEN','NO_PLAN') for row in decisions) and
        [fill['session'] for fill in fills]==expected_fill_dates,'Only frozen decisions produce execution events')
    trades=execution['trades'];decision_summary=[]
    for row,source in zip(decisions,rows,strict=True):
        day=row['decision_date'];chains,dates=at(day)
        require(set(row['targets'])==set(source['targets']),'Actual decision target set differs')
        actual=set(row['shares_before'])|set(source['targets'])
        require(actual<=set(chains) and row['risk_chains']=={sid:chains[sid] for sid in actual} and
            row['risk_chain_observation_dates']=={sid:dates[sid] for sid in actual},'Decision old holdings use missing/future risk observations')
        matched=[fill for fill in fills if fill['session']==row['execution_date']]
        if row['status']=='NO_PLAN':
            require(not matched and not any(t['session']==row['execution_date'] for t in trades),'NO_PLAN cannot be a fill or rejection')
            status='NO_PLAN'
        else:
            require(len(matched)==1,'One frozen basket execution required');fill=matched[0];status=fill['status']
            require(status in ('FILLED','REJECTED'),'Unexpected action-free execution status')
            if status=='REJECTED':
                require(fill['shares_before']==fill['shares_after'] and number(fill['cash_before_usd'])==number(fill['cash_after_usd']) and
                    not any(t['session']==fill['session'] for t in trades),'Rejected basket changed holdings/cash or produced trades')
        decision_summary.append(dict(decision_date=day,execution_date=row['execution_date'],decision_status=row['status'],
            execution_outcome=status,held_sids_outside_current_target=sorted(set(row['shares_before'])-set(source['targets']))))
    for row in daily:
        chains,dates=at(row['session']);held=set(row['shares'])
        require(held<=set(chains) and row['risk_chains']=={sid:chains[sid] for sid in held} and
            row['risk_chain_observation_dates']=={sid:dates[sid] for sid in held},'Daily retained holdings use missing/future risk observations')
    return deepcopy(selected_maps),dict(cutoff_evidence=expected_evidence,decision_outcomes=decision_summary,
        decision_count=6,execution_count=len(fills),no_plan_count=sum(r['status']=='NO_PLAN' for r in decisions),
        rejected_execution_count=sum(r['status']=='REJECTED' for r in fills),filled_execution_count=sum(r['status']=='FILLED' for r in fills),
        label_policy='LATEST_SELECTION_OBSERVATION_NOT_LAST_STRATEGIC_TARGET_OR_FULL_INTERVAL_CERTIFICATION',
        no_plan_is_global_economic_infeasibility=False,future_observations_used=False,risk_label_validity_interval_certified=False)


def audit_candidate(candidate, schedule, projection):
    require(projection['schema']=='BAD_TAIL_FIVE_SECURITY_107_SESSION_INPUT_PROJECTION_V1' and
        all(projection[key] is False for key in ('point_in_time_verified','promotion_allowed','execution_risk_chain_union_verified','target_schedule_validity_verified')),
        'Conditional projection scope differs')
    price=dict(projection['price_projection'],calendar=projection['calendar'])
    identities=projection['identity_projection']
    calendar = price['calendar']
    require(len(calendar) == 107 and calendar == sorted(set(calendar)) and
            calendar[0] == '2023-03-31' and calendar[-1] == '2023-09-01', 'Exact calendar required')
    require(candidate['calendar'] == calendar == [d for d in schedule['calendar'] if calendar[0] <= d <= calendar[-1]], 'Calendar linkage differs')
    require(exact(candidate['schedule'], schedule['schedule']) and
            [[r['decision_date'], r['execution_date']] for r in candidate['schedule']] == CLOCK, 'Exact six-decision clock required')
    require(identities['conditional_window'] == dict(start=calendar[0], end=calendar[-1]), 'Identity window differs')
    require(identities['parent_schedule_binding_reused_as_bad_tail_admission'] is False,'Parent identity binding cannot grant lane admission')
    labels = {r['security_id']: r for r in identities['rows']}
    require(type(candidate['security_count']) is int and candidate['security_count'] == 5 and
            type(candidate['distinct_issuer_count']) is int and candidate['distinct_issuer_count'] == 5 and
            candidate['fixed_four_security_policy'] is False and
            candidate['per_decision_target_counts'] == [len(r['targets']) for r in candidate['schedule']], 'Candidate security semantics differ')
    require(len(labels) == len(identities['rows']) == 5 and len({r['issuer_id'] for r in labels.values()}) == 5, '5 SID / 5 issuer denominator required')
    require(set(price['tickers']) == {r['ticker'] for r in labels.values()} and len(price['tickers']) == 5, 'Price identity union differs')
    require(set().union(*(r['targets'] for r in candidate['schedule'])) == set(labels), 'Target union differs')
    for decision in candidate['schedule']:
        require(calendar[calendar.index(decision['decision_date']) + 1] == decision['execution_date'], 'Next observed session differs')
        require(len({v['issuer_id'] for v in decision['targets'].values()}) == len(decision['targets']), 'Duplicate issuer within decision')
        for sid, target in decision['targets'].items():
            require(all(target[k] == labels[sid][k] for k in ('ticker', 'issuer_id')), 'Target identity mismatch')
    require(set(candidate['execution_contract']) == set(CONTRACT) and
            all(number(candidate['execution_contract'][k]) == number(v) for k, v in CONTRACT.items()), 'Fixed capital/risk/fee contract differs')
    selected_chains, risk_report = independent_risk_history(schedule, projection, candidate['execution'])
    require(exact(candidate['risk_chain_evidence'], risk_report['cutoff_evidence']), 'Causal chain evidence differs')
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
        cell_count=1070, cells=conversion)), 'Decimal to engine-float conversion evidence differs')
    with localcontext(Context(prec=80)):
        result = accounting.audit(execution=candidate['execution'], calendar=calendar, schedule=normalized,
                                  prices=marks, risk_chains_by_decision=selected_chains, contract=CONTRACT)
    require(exact(result, candidate['independent_decimal_accounting']), 'Embedded accounting differs from independent audit')
    return result, metrics([r['total_value_usd'] for r in candidate['execution']['daily']]), risk_report


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
    require(candidate_sha256==CANDIDATE_SHA, 'External candidate SHA differs from the unique completed account')
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
    required = {str(PRODUCER): producer_sha256, **FROZEN, **ENGINE_SOURCES,
                str(archive.SOURCE): LOADED[str(archive.SOURCE)],
                str(Path(archive.drift.__file__).resolve()): LOADED[str(Path(archive.drift.__file__).resolve())],
                **{reference(role)['path']: reference(role)['sha256'] for role in INPUT_ROLES}}
    for role in INPUT_ROLES:
        for field in ('source_hashes', 'historical_expected_source_hashes'):
            if field in docs[role]: archive.merge(required, docs[role][field])
    require(exact(candidate_sources, required), 'Candidate source closure differs from independently reconstructed closure')
    archive.merge(sources, RUNTIME_LOADED)
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
    linkage = docs['linkage']
    require(linkage['exact_schedule_reconstruction'] is True and linkage['schedule_reference'] == reference('schedule') and
            linkage['independent_target_audit_reference'] == reference('audit'), 'Schedule independent linkage differs')
    require(docs['audit']['status'] == 'PASSED' and docs['audit']['completed_prefix_count'] == 6, 'Complete six target audit required')
    contract = archive.load_contract()
    resolution = archive.verify_expected_sources(sources, contract)
    require(archive.verify_expected_sources(candidate_sources, contract) == candidate['archive_resolution'], 'Candidate archive partition differs')
    audit_raw(candidate, started, raw, docs['projection']['identity_projection'])
    audit, measures, risk_history = audit_candidate(candidate, docs['schedule'], docs['projection'])
    comparison = compare(docs['benchmark'], candidate['calendar'], measures)
    require(archive.verify_expected_sources(sources, contract) == resolution, 'Sources changed during readback')
    require({p.name for p in ACCOUNT_DIRECTORY.iterdir()} == names, 'Attempt directory changed during readback')
    return dict(schema='BAD_TAIL_SIX_PERIOD_CONDITIONAL_COMPARISON_INDEPENDENT_V1', candidate_reference=candidate_ref,
                producer_reference=dict(path=str(PRODUCER), sha256=producer_sha256), calendar=candidate['calendar'],
                decision_clock=CLOCK, independent_accounting=audit, comparison=comparison,
                causal_risk_history=risk_history, normalization_call_count=1, candidate_accounting_audit_call_count=1,
                old_control_accounting_audit_call_count=0, saved_candidate_execution_performed=True,
                attempt_directory_entries=sorted(names), runtime=candidate['runtime'],
                historical_expected_source_hashes=sources, archive_resolution=resolution, **dict.fromkeys(FALSE, False))


def publish(value, output):
    require(not Path(output).resolve().is_relative_to(ACCOUNT_DIRECTORY), 'Readback must not alter attempt directory')
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

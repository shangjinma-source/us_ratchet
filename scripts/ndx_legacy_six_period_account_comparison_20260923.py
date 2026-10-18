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
PRODUCER = ROOT / 'scripts/ndx_legacy_six_period_conditional_execution_20260923.py'
PRODUCER_SHA = 'd9cd0806f028aeb887c17a667205b55a0fec102aa4830e629d20c24c1fc987cf'
ACCOUNT_DIRECTORY = BASE / 'legacy_six_period_conditional_execution_20260923_v1'
CANDIDATE_SHA='cbdae21a46a25dd88ff3c060005f210c333884d2e6ae1ac2a10405b2f1e53797'
BOUND = {
 'schedule':('legacy_target_distance_targets_20260923_v1/schedule.json','7fa92ff703d94fc5ff0dcdb5595ea903ac72c5c36b2c76dfd36da77caaa1e5e2'),
 'audit':('legacy_target_distance_targets_20260923_v1/completed6_independent_readback.json','279d9ec7814011d10e3c02554863ac417ce02914401444e2ac991e6e2f05b955'),
 'linkage':('legacy_target_distance_targets_20260923_v1/schedule_independent_linkage.json','02eb08cdd6acc8166d8d58bf5ae5e09c6b1314897d8743cd511d6e98a7ce5951'),
 'identity':('legacy_twelve_conditional_identity_20260923_v1/identities.json','82ad1d271f3bd0fb3906647f808c0a9c9f81270ab7e29f7f6c626fbf8e9db8db'),
 'price':('legacy_twelve_price_only_20260923_v1/prices.json','a50c4fd387f10262527e82ad0edd2bae7b799b67e2d08cff2e4a47030a64b342'),
 'lane':('cutoff_training_lanes_20260923_v2/prepare.json','b7eaff190f3b2225db87d14fd0f7afc0cd9420536e9a4661f986f8ac319a96ba'),
 'benchmark':('return_six_period_benchmarks_20260923_v1/benchmarks.json','ef7ccdbe45a95fdf616d1b681bf9cd5c431db01585d30cf979e5cd4f2d45b423'),
}
INPUT_ROLES = tuple(BOUND)
OUTPUT = BASE / 'legacy_six_period_comparison_20260923_v1/comparison.json'
TARGET_COUNTS=[4,4,4,4,6,4]
EXPECTED={
 'security:0000796343:00724F101':('ADBE','issuer:0000796343','cloud_application_software'),
 'security:0000006281:032654105':('ADI','issuer:0000006281','analog_power'),
 'security:0001730168:11135F101':('AVGO','issuer:0001730168','diversified_technology'),
 'security:0001701605:05722G100':('BKR','issuer:0001701605','energy_technology'),
 'security:0001561550:23804L103':('DDOG','issuer:0001561550','cloud_application_software'),
 'security:0001463101:29355A107':('ENPH','issuer:0001463101','energy_technology'),
 'security:0001262039:34959E109':('FTNT','issuer:0001262039','cybersecurity'),
 'security:0001652044:02079K107':('GOOG','issuer:0001652044','platform_advertising'),
 'security:0001652044:02079K305':('GOOGL','issuer:0001652044','platform_advertising'),
 'security:0000804328:747525103':('QCOM','issuer:0000804328','wireless_semiconductor'),
 'security:0001650372:049468101':('TEAM','issuer:0001650372','cloud_application_software'),
 'security:0000097476:882508104':('TXN','issuer:0000097476','analog_power'),
}
CLOCK = [['2023-03-31', '2023-04-03'], ['2023-04-28', '2023-05-01'],
         ['2023-05-31', '2023-06-01'], ['2023-06-30', '2023-07-03'],
         ['2023-07-31', '2023-08-01'], ['2023-08-31', '2023-09-01']]
CONTRACT = dict(initial_cash_usd=25000, minimum_cash_buffer_usd=100, transaction_cost_bps=10,
                max_single_weight=.45, min_single_weight=.05, top_weight_cap=.8,
                minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55)
SCHEMA = 'LEGACY_SIX_PERIOD_CONDITIONAL_ACCOUNT_V1'
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
    require(type(sha) is str and len(sha)==64 and set(sha)<=set('0123456789abcdef'),'Final hard input SHA required')
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


def current_source_guard():
    archive.strict({**LOADED,**FROZEN,**ENGINE_SOURCES,str(PRODUCER):PRODUCER_SHA})


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
    require(started['input_references'] == {role: reference(role) for role in INPUT_ROLES}, 'Exact seven input references required')
    validation = dict(frozen_price_index_validators_called=True, frozen_schedule_and_contract_validators_called=True,
                      normalized_copy_discarded=True, submitted_schedule_modified=False, simulate_called=False,
                      session_count=107, security_column_count=12, decision_count=6)
    for document in (started, candidate):
        require(exact(document['engine_input_validation'], validation), 'Frozen input validation evidence differs')
    for key in ('calendar', 'schedule', 'internal_columns', 'execution_contract', 'normalization_evidence', 'price_conversion_evidence', 'engine_input_validation', 'risk_chain_evidence', 'action_free_assumption'):
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


def audit_candidate(candidate, schedule, price, identities, lane):
    require(schedule['schema']=='LEGACY_TARGET_DISTANCE_SIX_PERIOD_STRATEGIC_TARGET_SCHEDULE_V1' and
        price['schema']=='LEGACY_TWELVE_107_OBSERVED_SESSION_CONDITIONAL_PRICE_ONLY_V1' and
        identities['schema']=='LEGACY_TWELVE_CONDITIONAL_IDENTITY_ASSEMBLY_V1','Exact LEGACY source schemas required')
    require(all(document[key] is False for document in (price,identities) for key in
        ('point_in_time_verified','promotion_allowed','execution_risk_chain_union_verified','target_schedule_validity_verified',
         'provider_binding_verified','continuous_identity_interval_verified')),'Conditional input scope differs')
    require(price['dividend_cash_flows_modelled'] is False and price['corporate_action_completeness_verified'] is False and
        price['inherited_split_factors_reapplied'] is False and price['adjusted_close_used'] is False and
        price['nominal_price_status']=='CONDITIONAL_RECONSTRUCTION_NOT_AUTHENTICATED','Conditional price action scope differs')
    calendar = price['calendar']
    require(len(calendar)==107 and calendar==sorted(set(calendar)) and calendar[0]=='2023-03-31' and calendar[-1]=='2023-09-01',
        'Exact 107 observed calendar required')
    require(candidate['calendar']==identities['calendar']==calendar==[d for d in schedule['calendar'] if calendar[0]<=d<=calendar[-1]],
        'Calendar linkage differs')
    require(exact(candidate['schedule'],schedule['schedule']) and
        [[r['decision_date'],r['execution_date']] for r in candidate['schedule']]==CLOCK,'Exact six-decision clock required')
    require(identities['conditional_window']==dict(start=calendar[0],end=calendar[-1]) and
        identities['enph_original_interval_certification_extended'] is False and
        identities['enph_original_conditional_window']==dict(start='2023-03-31',end='2023-05-01') and
        identities['interval_stability_assumption']=='NEW_EXPLICIT_107_DAY_STABILITY_ASSUMPTION_USING_DATED_FACTS_NOT_INTERVAL_CERTIFICATION' and
        identities['goog_googl_relationship']=='DIFFERENT_SECURITY_IDS_SAME_ISSUER_NOT_A_RENAME' and
        identities['team_old_issuer_or_class_conversion_verified'] is False and identities['dated_fact_availability_backdated'] is False,
        'Dated identity must not become interval or class-conversion certification')
    labels={r['security_id']:r for r in identities['rows']}
    require(set(labels)==set(EXPECTED) and all((labels[sid]['ticker'],labels[sid]['issuer_id'])==row[:2]
        for sid,row in EXPECTED.items()),'Exact twelve security identity coordinates required')
    require(all(row[key] is False for row in labels.values() for key in
        ('continuous_interval_verified','provider_binding_verified','point_in_time_verified')),'Identity row scope differs')
    for ticker,title in (('GOOG','Class C'),('GOOGL','Class A'),('TEAM','Class A')):
        require(title in next(row['security_class'] for row in labels.values() if row['ticker']==ticker),'Security class differs')
    require(lane['schema']=='CUTOFF_TRAINING_LANE_DEPENDENCY_PREPARE_V1' and lane['promotion_allowed'] is False and
        lane['member_point_in_time_verified'] is False and [[d['cutoff'],d['execution_date']] for d in lane['decisions']]==CLOCK,
        'Hard training lane scope differs')
    require(identities['observed_decision_clock']==CLOCK and len(identities['saved_lane_choices'])==6,'Identity six-choice clock differs')
    for index,(choice,decision) in enumerate(zip(identities['saved_lane_choices'],lane['decisions'],strict=True)):
        candidates=decision['lanes']['LEGACY_TARGET_DISTANCE'];observed=choice['saved_candidate']['selected']
        require(len(candidates)==1 and exact(choice['saved_candidate'],candidates[0]) and len(observed)==TARGET_COUNTS[index] and
            all(tuple(row[key] for key in ('ticker','issuer_id','risk_chain'))==EXPECTED[sid] for sid,row in observed.items()),
            'Exact saved lane choice and risk observations required')
    require(price['ticker_count']==12 and price['session_count']==107 and price['price_cell_count']==2568,
        'Exact price cell denominator required')
    expected_action=dict(dividend_events_retained_in_price_source=True,dividends_added_to_cash=False,
        identity_class_conversion_assumed=False,description='CONDITIONAL_ACTION_FREE_LEDGER_DESPITE_RETURNED_DIVIDEND_EVENTS',
        price_reference=reference('price'))
    require(exact(candidate['action_free_assumption'],expected_action),'Action-free assumption differs')
    require(candidate['execution']['corporate_actions']==[] and candidate['execution']['identity_events']==[] and
        candidate['execution']['dividend_modelled'] is False,'Dividend/identity event ledger not supported by this comparison')
    require(type(candidate['security_count']) is int and candidate['security_count'] == 12 and
            type(candidate['distinct_issuer_count']) is int and candidate['distinct_issuer_count'] == 11 and
            candidate['fixed_security_count_policy'] is False and
            candidate['per_decision_target_counts'] == [len(r['targets']) for r in candidate['schedule']] == TARGET_COUNTS, 'Candidate security semantics differ')
    require(len(labels) == len(identities['rows']) == 12 and len({r['issuer_id'] for r in labels.values()}) == 11, '12 SID / 11 issuer denominator required')
    require(set(price['tickers']) == {r['ticker'] for r in labels.values()} and len(price['tickers']) == 12, 'Price identity union differs')
    require(set().union(*(r['targets'] for r in candidate['schedule'])) == set(labels), 'Target union differs')
    for decision in candidate['schedule']:
        require(calendar[calendar.index(decision['decision_date']) + 1] == decision['execution_date'], 'Next observed session differs')
        require(len({v['issuer_id'] for v in decision['targets'].values()}) == len(decision['targets']), 'Duplicate issuer within decision')
        for sid, target in decision['targets'].items():
            require(all(target[k] == labels[sid][k] for k in ('ticker', 'issuer_id')), 'Target identity mismatch')
    require(set(candidate['execution_contract']) == set(CONTRACT) and
            all(number(candidate['execution_contract'][k]) == number(v) for k, v in CONTRACT.items()), 'Fixed capital/risk/fee contract differs')
    selected_chains, risk_report = independent_risk_history(schedule, identities, candidate['execution'])
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
        cell_count=2568, cells=conversion)), 'Decimal to engine-float conversion evidence differs')
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
    require(all(type(value) is str and len(value)==64 and set(value)<=set('0123456789abcdef') for value in
        (PRODUCER_SHA,CANDIDATE_SHA)), 'Completed hard producer and candidate SHA required')
    require(PRODUCER_SHA is not None and producer_sha256 == PRODUCER_SHA, 'Externally supplied producer SHA differs from reviewed producer')
    require(candidate_sha256==CANDIDATE_SHA, 'External candidate SHA differs from the unique completed account')
    require(all(LOADED[p] == h for p, h in FROZEN.items()), 'Frozen audit/normalization module differs')
    current_source_guard()
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
        for field in ('source_hashes', 'historical_expected_source_hashes', 'prepare_source_hashes'):
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
        for field in ('source_hashes', 'historical_expected_source_hashes', 'prepare_source_hashes'):
            if field in doc:
                archive.merge(sources, doc[field])
    linkage = docs['linkage']
    require(linkage['exact_schedule_reconstruction'] is True and linkage['schedule_reference'] == reference('schedule') and
            linkage['independent_target_audit_reference'] == reference('audit'), 'Schedule independent linkage differs')
    require(docs['audit']['status'] == 'PASSED' and docs['audit']['completed_prefix_count'] == 6, 'Complete six target audit required')
    contract = archive.load_contract()
    resolution = archive.verify_expected_sources(sources, contract)
    require(archive.verify_expected_sources(candidate_sources, contract) == candidate['archive_resolution'], 'Candidate archive partition differs')
    audit_raw(candidate, started, raw, docs['identity'])
    audit, measures, risk_history = audit_candidate(candidate, docs['schedule'], docs['price'], docs['identity'], docs['lane'])
    comparison = compare(docs['benchmark'], candidate['calendar'], measures)
    current_source_guard();require(candidate['runtime']==runtime(),'Runtime changed during independent readback')
    require(archive.verify_expected_sources(sources, contract) == resolution, 'Sources changed during readback')
    require({p.name for p in ACCOUNT_DIRECTORY.iterdir()} == names, 'Attempt directory changed during readback')
    return dict(schema='LEGACY_SIX_PERIOD_CONDITIONAL_COMPARISON_INDEPENDENT_V1', candidate_reference=candidate_ref,
                producer_reference=dict(path=str(PRODUCER), sha256=producer_sha256), calendar=candidate['calendar'],
                decision_clock=CLOCK, independent_accounting=audit, comparison=comparison,
                causal_risk_history=risk_history, normalization_call_count=1, candidate_accounting_audit_call_count=1,
                old_control_accounting_audit_call_count=0, saved_candidate_execution_performed=True,
                attempt_directory_entries=sorted(names), runtime=candidate['runtime'],
                historical_expected_source_hashes=sources, archive_resolution=resolution, **dict.fromkeys(FALSE, False))


def publish(value, output):
    require(Path(output).resolve()==OUTPUT.resolve() and not OUTPUT.parent.exists(),'Fresh fixed comparison namespace required')
    require(not Path(output).resolve().is_relative_to(ACCOUNT_DIRECTORY), 'Readback must not alter attempt directory')
    contract = archive.load_contract()
    def verify():
        current_source_guard();require(value['runtime']==runtime(),'Runtime changed before publication')
        require(archive.verify_expected_sources(value['historical_expected_source_hashes'], contract) == value['archive_resolution'], 'Publication source drift')
        require({p.name for p in ACCOUNT_DIRECTORY.iterdir()} == set(value['attempt_directory_entries']), 'Attempt directory changed')
    verify()
    raw = encode(value)
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
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

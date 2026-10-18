"""Extend sealed fixed incumbent control to the explicit fifteen-session clock."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.ndx_dynamic_frozen_control_input import prepare_control
from scripts.ndx_dynamic_frozen_input_probe import _check_sources
from backtest.ndx_incumbent_risk_overlay_research import load_incumbent_risk_overlay

SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CONTROL = ROOT / 'data/cache/research/dynamic_frozen_v2/strict_return_control_20260911.json'
CONTROL_SHA = '87b081061374a368c0c7d1b6a3d953ba964c3ac2e30d56f3a7173e21d1c3b58b'
REFERENCE = ROOT / 'data/cache/research/dynamic_frozen_v2/preference_refit_schedule_20260912.json'
REFERENCE_SHA = '4325a37801e915179bd0c428b132be56d5c2e6273524c6e2ad1101741587b559'
OVERLAY = ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay/reviewed/manifest.json'
OVERLAY_SHA = '8ab02a983a5b316b0da053d3f97dd87f87b863a36a4f359a5ab23b74700b384b'


def _extend(*, prior_schedule, reference_schedule, calendar, original_weights):
    if (len(prior_schedule) != 14 or len(reference_schedule) != 15 or len(calendar) != 295
            or calendar != sorted(set(calendar)) or calendar[0] != '2023-03-31' or calendar[-1] != '2024-06-03'):
        raise ValueError('Exact historical 14-to-15 period and 295 session denominator required')
    targets = prior_schedule[0]['targets']
    if len(targets) != 8 or any(row['targets'] != targets for row in prior_schedule):
        raise ValueError('Original eight fixed targets must remain unchanged')
    if {value['ticker']: value['target_weight'] for value in targets.values()} != original_weights:
        raise ValueError('Captured original incumbent weight vector differs')
    def clock(rows):
        return [(row['decision_date'], row['execution_date']) for row in rows]
    if clock(prior_schedule) != clock(reference_schedule[:14]):
        raise ValueError('New clock does not preserve all fourteen original coordinates')
    if clock(reference_schedule)[-1] != ('2024-05-31', '2024-06-03'):
        raise ValueError('Explicit fifteenth decision/fill required')
    seen = set()
    for decision, execution in clock(reference_schedule):
        if decision in seen or decision not in calendar or execution not in calendar:
            raise ValueError('Duplicate or missing decision/fill session')
        if calendar.index(execution) != calendar.index(decision) + 1:
            raise ValueError('Execution must be the next supplied session')
        seen.add(decision)
    return [dict(decision_date=row['decision_date'], execution_date=row['execution_date'],
                 targets=deepcopy(targets)) for row in reference_schedule]


def build_report():
    sources = {str(CONTROL): CONTROL_SHA, str(REFERENCE): REFERENCE_SHA, str(SOURCE): LOADED_SHA}
    _check_sources(sources)
    prior, reference = json.loads(CONTROL.read_bytes()), json.loads(REFERENCE.read_bytes())
    _check_sources(prior['source_hashes'])
    prepared = prepare_control(prior['lane_key'])
    if (prepared['original_weights'] != prior['original_weights'] or prior['promotion_allowed'] is not False
            or prior['execution']['risk_is_order_gate'] is not False
            or prior['execution']['original_target_weights_modified'] is not False):
        raise ValueError('Sealed original control semantics differ')
    sealed = [dict(decision_date=row['decision_date'], execution_date=row['execution_date'], targets=row['targets'])
              for row in prior['execution']['decisions']]
    if sealed != prepared['schedule']:
        raise ValueError('Archived input trace and sealed actual decision targets differ')
    clock = reference['schedule_result']
    schedule = _extend(prior_schedule=prepared['schedule'], reference_schedule=clock['schedule'],
                       calendar=clock['calendar'], original_weights=prepared['original_weights'])
    risk = load_incumbent_risk_overlay(reviewed_manifest_path=OVERLAY, expected_manifest_sha256=OVERLAY_SHA,
        tickers=sorted(prepared['original_weights']), date_start=clock['calendar'][0], date_end=clock['calendar'][-1])
    targets = schedule[0]['targets']
    labels = {sid: risk['risk_chain_by_ticker'][value['ticker']] for sid, value in targets.items()}
    if any(row != labels for row in prepared['risk_chains'].values()):
        raise ValueError('Original incumbent risk labels changed')
    for mapping in (prior['source_hashes'], prepared['source_hashes'], risk['provenance']['source_hashes']):
        for path, digest in mapping.items():
            if path in sources and sources[path] != digest:
                raise ValueError('Conflicting fixed control source closure')
            sources[path] = digest
    _check_sources(sources)
    return dict(schema='ndx_incumbent_fixed_schedule_research_v1',
        role='ORIGINAL_FIXED_INCUMBENT_CONTROL_NOT_CANDIDATE', original_control_sha256=CONTROL_SHA,
        reference_clock_sha256=REFERENCE_SHA, original_weights=prepared['original_weights'],
        calendar=clock['calendar'], calendar_count=295, schedule=schedule, decision_count=15,
        original_fourteen_decisions_preserved=True, original_targets_and_weights_unchanged=True,
        extension_rule='SAME_DISCLOSED_FIXED_TARGET_ON_EXPLICIT_FIFTEENTH_CLOCK',
        initial_cash_usd=prepared['capital_usd'], minimum_cash_buffer_usd=prepared['minimum_cash_buffer_usd'],
        transaction_cost_bps=prepared['transaction_cost_bps'], valuation_end_date=clock['calendar'][-1],
        risk_chains_by_decision={row['decision_date']: deepcopy(labels) for row in schedule},
        risk_provenance=risk['provenance'], source_hashes=sources,
        identity_scope=prepared['identity_scope'], overlay_security_ids=[sid for sid in targets if 'incumbent_overlay' in sid],
        risk_is_order_gate=False, risk_projection_performed=False, weights_refitted=False,
        current_configuration_read=False, target_portfolio_optimization_performed=False,
        corporate_action_coverage_verified=False, price_identity_binding_verified=False,
        point_in_time_verified=False, execution_performed=False, promotion_allowed=False)


def save_report(output):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'data/cache/research').resolve()):
        raise ValueError('Research output directory required')
    report = build_report()
    raw = (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    _check_sources(report['source_hashes'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        handle.write(raw)
    _check_sources(report['source_hashes'])
    if output.read_bytes() != raw:
        raise ValueError('Saved control schedule differs')
    return dict(path=str(output), sha256=hashlib.sha256(raw).hexdigest(), decisions=report['decision_count'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    print(json.dumps(save_report(arguments.output)))

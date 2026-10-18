"""Original fixed incumbent control with independently scoped conditional quotes."""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtest import ndx_nominal_quote_reconstruction_research as nominal
from backtest import ndx_dynamic_frozen_incumbent_control as control
from scripts import ndx_incumbent_fixed_schedule_research as fixed

SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BOUND = {
    'data/cache/research/incumbent_price_source_probe_20260912_v1/manifest.json':
        '4e30f0f7e48b157eb4a5f60cd5d6531b097d2a276f977444838778411e30d77e',
    'data/cache/research/incumbent_price_source_probe_20260912_v1/incumbent_price_basis_review_20260912.json':
        '6565e1cc5233f148d683d134ca95a29886530f8ab25cf48e3c839aa21864293f'}


def _merge(*mappings):
    result = {}
    for mapping in mappings:
        for path, digest in mapping.items():
            if path in result and result[path] != digest:
                raise ValueError('Conflicting control input source closure')
            result[path] = digest
    nominal.verify(result)
    return result


def prepare_inputs():
    sources = {str(ROOT / path): digest for path, digest in BOUND.items()}
    sources[str(SOURCE)] = LOADED_SHA
    nominal.verify(sources)
    manifest, basis = [json.loads((ROOT / path).read_bytes()) for path in BOUND]
    schedule = fixed.build_report()
    tickers = sorted(schedule['original_weights'])
    if (basis['quote_field_basis'] != nominal.BASIS or basis['basis_status'] != 'CONDITIONAL_RESEARCH_ONLY'
            or basis['quote_basis_review_independently_scoped_to_eight_controls'] is not True
            or sorted(basis['tickers']) != tickers or basis['calendar'] != schedule['calendar']
            or basis['current_to_historical_security_binding_verified'] is not False
            or basis['strategy_information_pit_verified'] is not False):
        raise ValueError('Separate conditional eight-incumbent basis decision required')
    sources = _merge(sources, schedule['source_hashes'], basis['source_hashes'], manifest['source_hashes'])
    probes = {}
    for ticker in tickers:
        matches = [row for row in manifest['probes'] if row['name'] == 'yahoo_' + ticker.lower() + '_through_received_daily_events']
        decisions = [row for row in basis['rows'] if row['ticker'] == ticker]
        if len(matches) != 1 or len(decisions) != 1:
            raise ValueError('Unique control probe and basis row required')
        if (matches[0]['response_path'] != decisions[0]['price_response_path']
                or matches[0]['response_sha256'] != decisions[0]['price_response_sha256']):
            raise ValueError('Control basis and raw quote source mismatch')
        probes[ticker] = matches[0]
    quotes = nominal.build_nominal_quote_research(calendar=schedule['calendar'], probes=probes,
        quote_field_basis=basis['quote_field_basis'], source_hashes=sources)
    if quotes['total_rows'] != 2360:
        raise ValueError('Complete 8x295 quote denominator required')
    for row in quotes['by_ticker'].values():
        if any(schedule['calendar'][0] <= event['effective_session'] <= schedule['calendar'][-1]
               for event in row['provider_split_events']):
            raise ValueError('An in-window split requires explicit accounting action input')
    opens = pd.DataFrame({ticker: [row['nominal_open'] for row in quotes['by_ticker'][ticker]['rows']]
                          for ticker in tickers}, index=pd.to_datetime(schedule['calendar']))
    closes = pd.DataFrame({ticker: [row['nominal_close'] for row in quotes['by_ticker'][ticker]['rows']]
                           for ticker in tickers}, index=opens.index)
    # The sealed old control caller omitted these five arguments, so the frozen
    # control function defaults are its actual original contract, not live config.
    signature = inspect.signature(control.simulate_dynamic_frozen_incumbent_control)
    risk = {key: signature.parameters[key].default for key in ('max_single_weight', 'min_single_weight',
        'top_weight_cap', 'minimum_effective_n_ratio', 'risk_chain_top1_cap')}
    sources = _merge(quotes['source_hashes'], schedule['source_hashes'])
    return dict(schedule=schedule, quotes=quotes, opens=opens, closes=closes,
        original_risk_parameters=risk, basis=basis, source_hashes=sources)


def run():
    prepared = prepare_inputs()
    schedule = prepared['schedule']
    result = control.simulate_dynamic_frozen_incumbent_control(opens=prepared['opens'], closes=prepared['closes'],
        schedule=schedule['schedule'], risk_chains_by_decision=schedule['risk_chains_by_decision'],
        corporate_actions=[], initial_cash_usd=schedule['initial_cash_usd'],
        minimum_cash_buffer_usd=schedule['minimum_cash_buffer_usd'],
        valuation_end_date=schedule['valuation_end_date'], transaction_cost_bps=schedule['transaction_cost_bps'],
        **prepared['original_risk_parameters'])
    if (result['risk_is_order_gate'] is not False or result['original_target_weights_modified'] is not False
            or result['candidate_eligibility_claimed'] is not False or len(result['daily']) != 295
            or len(result['decisions']) != 15
            or any(row['targets'] != schedule['schedule'][0]['targets'] for row in result['decisions'])):
        raise ValueError('Original fixed control execution semantics changed')
    sources = _merge(prepared['source_hashes'], result['source_hashes'])
    return dict(schema='ndx_incumbent_nominal_control_research_v1',
        scope='CONDITIONAL_PROVIDER_PRICE_ORIGINAL_FIXED_INCUMBENT_CONTROL',
        execution=result, original_fixed_schedule=schedule, nominal_quotes=prepared['quotes'],
        source_hashes=sources, original_risk_parameters=prepared['original_risk_parameters'],
        price_basis_review_sha256=list(BOUND.values())[1],
        archived_price_differences=prepared['basis']['unresolved_difference'],
        old_economic_results_equivalent=False, risk_is_order_gate=False,
        original_target_weights_modified=False, ticker_to_legacy_sid_attribution_only=True,
        price_identity_binding_verified=False, official_split_event_completeness_verified=False,
        dividends_modelled=False, point_in_time_verified=False, candidate_selected=False,
        live_execution_performed=False, research_execution_performed=True, promotion_allowed=False)


def save_report(output):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'data/cache/research').resolve()):
        raise ValueError('Research output directory required')
    if output.exists():
        raise FileExistsError('Existing control artifact; do not repeat execution')
    report = run()
    encoded = (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')
    nominal.verify(report['source_hashes'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        handle.write(encoded)
    nominal.verify(report['source_hashes'])
    if output.read_bytes() != encoded:
        raise ValueError('Saved control result differs')
    return dict(path=str(output), sha256=hashlib.sha256(encoded).hexdigest(), decision_count=15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    print(json.dumps(save_report(arguments.output)))

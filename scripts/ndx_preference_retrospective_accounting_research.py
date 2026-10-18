"""Fixed-schedule conditional accounting from external quotes and dated identities.

This is a retrospective experiment, conditional on the absence of unobserved
security changes. Dated identity snapshots do not certify an entire interval.
The frozen execution engine and its ticker-change guard remain unchanged.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_dynamic_frozen_execution_research as engine
from scripts import ndx_preference_nominal_quote_research as nominal_inputs

SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BOUND = {
    'data/cache/research/dynamic_frozen_v2/preference_refit_schedule_20260912.json':
        '4325a37801e915179bd0c428b132be56d5c2e6273524c6e2ad1101741587b559',
    'data/cache/research/dynamic_frozen_v2/strict_user_preference_20260911.json':
        'e5f4919f2819404d26e8148c995e34de611d26463f93e3d0689a224b5b545892',
    'data/cache/research/four_issuer_filing_identity_20260912_v1/dated_identity_adjudication.json':
        'a70551b92c2154b9b1efe5eadb35b1f3c0f34b1c9a858506e3a2085df888d8a4',
    'data/cache/research/four_issuer_filing_identity_20260912_v1/receipt_closure.json':
        '59aa08a03b1ff8faec04b22266c1340e85fca0af3606c6fc2baa3bf3269b6a64'}


def verify(sources):
    for path, expected in sources.items():
        if not Path(path).is_absolute() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Retrospective accounting source differs: ' + path)


def merge(sources, additional):
    for path, digest in additional.items():
        if path in sources and sources[path] != digest:
            raise ValueError('Conflicting accounting source')
        sources[path] = digest


def prepare_inputs(nominal_path, nominal_sha256):
    sources = {str(ROOT / path): digest for path, digest in BOUND.items()}
    sources[str(SOURCE)] = LOADED_SHA
    nominal_path = Path(nominal_path).resolve()
    merge(sources, {str(nominal_path): nominal_sha256})
    verify(sources)
    schedule_report, historical, identities, receipts = [json.loads((ROOT / path).read_bytes()) for path in BOUND]
    nominal = json.loads(nominal_path.read_bytes())
    # Recheck raw quote arithmetic and bound basis, not just caller-supplied flags.
    if nominal != nominal_inputs.build_report():
        raise ValueError('Nominal report differs from independently rebuilt bound quote inputs')
    for report in (schedule_report, historical, identities, receipts, nominal):
        merge(sources, report['source_hashes'])
    verify(sources)
    built = schedule_report['schedule_result']
    calendar = built['calendar']
    schedule = deepcopy(built['schedule'])
    names = {'AMAT', 'AVGO', 'CDNS', 'GOOG'}
    if (nominal['schema'] != 'ndx_nominal_quote_reconstruction_research_v1'
            or nominal['calendar'] != calendar or len(calendar) != 295
            or nominal['total_rows'] != 1180 or set(nominal['tickers']) != names
            or nominal['schedule_sha256'] != next(iter(BOUND.values()))
            or nominal['basis_review_status'] != 'CONDITIONAL_RESEARCH_ONLY'
            or any(report['promotion_allowed'] is not False for report in (schedule_report, historical, identities, nominal))
            or len(schedule) != 15 or identities['continuous_identity_interval_verified'] is not False):
        raise ValueError('Expected complete conditional research inputs required')
    by_sid = {row['security_id']: row for row in identities['rows']}
    if len(by_sid) != 4 or len(identities['rows']) != 4 or {row['ticker'] for row in by_sid.values()} != names:
        raise ValueError('Exactly four dated primary-source security links required')
    for sid, row in by_sid.items():
        if (sid != 'security:' + row['issuer_cik'] + ':' + row['cusip']
                or row['dated_cusip_to_subject_cik_field_link_verified'] is not True
                or row['dated_ticker_to_cik_and_class_cover_link_verified'] is not True
                or row['cross_document_same_issuer_class_adjudication'] != 'MATCH'):
            raise ValueError('Dated source field identity link differs')
    for decision in schedule:
        if set(decision['targets']) != set(by_sid):
            raise ValueError('Fixed reference composition differs')
        for sid, target in decision['targets'].items():
            identity = by_sid[sid]
            if target['ticker'] != identity['ticker'] or target['issuer_id'] != 'issuer:' + identity['issuer_cik']:
                raise ValueError('Decision SID/issuer/ticker contradicts dated source link')
    opens, closes = {}, {}
    for ticker in sorted(names):
        data = nominal['by_ticker'][ticker]
        if [row['session'] for row in data['rows']] != calendar or data['adjclose_used'] is not False:
            raise ValueError('Exact daily quote coordinate required')
        if any(calendar[0] <= event['effective_session'] <= calendar[-1] for event in data['provider_split_events']):
            raise ValueError('This fixed experiment has no in-window split accounting input')
        if any(row['ticker'] != ticker or row['currency'] != 'USD' for row in data['rows']):
            raise ValueError('Ticker or currency differs within price table')
        opens[ticker] = [row['nominal_open'] for row in data['rows']]
        closes[ticker] = [row['nominal_close'] for row in data['rows']]
    old = historical['input']
    if old['capital_usd'] != 25000 or old['minimum_cash_buffer_usd'] != 100 or old['transaction_cost_bps'] != 10:
        raise ValueError('Historical execution capital/cost contract differs')
    arguments = dict(opens=pd.DataFrame(opens, index=pd.DatetimeIndex(calendar)),
        closes=pd.DataFrame(closes, index=pd.DatetimeIndex(calendar)), schedule=schedule,
        risk_chains_by_decision=deepcopy(built['risk_chains_by_decision']), corporate_actions=[],
        initial_cash_usd=old['capital_usd'], minimum_cash_buffer_usd=old['minimum_cash_buffer_usd'],
        transaction_cost_bps=old['transaction_cost_bps'], valuation_end_date=calendar[-1],
        max_repair_evaluations=262144, **built['fixed_risk_parameters'])
    verify(sources)
    return arguments, sources


def build_report(nominal_path, nominal_sha256):
    arguments, sources = prepare_inputs(nominal_path, nominal_sha256)
    fixed = deepcopy(arguments['schedule'])
    execution = engine.simulate_dynamic_frozen_execution_research(**arguments)
    if arguments['schedule'] != fixed or len(execution['daily']) != 295 or len(execution['decisions']) != 15:
        raise ValueError('Fixed complete schedule changed or execution truncated')
    merge(sources, execution['source_hashes'])
    verify(sources)
    return dict(schema='ndx_preference_retrospective_accounting_research_v1', execution=execution,
        source_hashes=sources, reference_role='USER_PREFERENCE_NOT_SELECTED_WINNER',
        scope='FIXED_SCHEDULE_CONDITIONAL_RETROSPECTIVE_ACCOUNTING',
        dated_primary_source_identity_links_checked=True, real_external_quote_artifacts_used=True,
        conditioned_on_no_unobserved_security_identity_changes=True,
        conditional_provider_split_only_price_basis=True, dividend_cash_flows_modelled=False,
        continuous_identity_interval_certified=False, historical_provider_binding_certified=False,
        fixed_schedule_unchanged=True, historical_execution_capital_usd=25000,
        latest_user_account_data_used=False, original_frozen_ticker_change_guard_retained=True,
        execution_performed=True, training_rerun=False, refit_rerun=False,
        full_ndx_search_performed=False, dual_benchmark_completed=False,
        point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nominal-path', required=True)
    parser.add_argument('--nominal-sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if not output.is_relative_to((ROOT / 'data/cache/research').resolve()) or output.exists():
        raise ValueError('New research output path required')
    report = build_report(args.nominal_path, args.nominal_sha256)
    encoded = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    verify(report['source_hashes'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(encoded)
    verify(report['source_hashes'])
    print(json.dumps({'path': str(output), 'sha256': hashlib.sha256(encoded).hexdigest(),
                      'summary': report['execution']['summary']}))

"""Inventory existing data for two complete 101-security proxy cohorts; no fetch or training."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COVERAGE = ROOT / 'data/cache/research/dynamic_frozen_v2/full_membership_coverage_20260912_v2.json'
COVERAGE_SHA = 'eb15d117e6b3c07a41decf1666b5dfbcfda2fd25ee00ea05b5df680d7473dd64'


def build_report():
    sources = {}
    def read(path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and expected != digest:
            raise ValueError('Required source drift: ' + str(path))
        if str(path) in sources and sources[str(path)] != digest:
            raise ValueError('Source changed during inventory')
        sources[str(path)] = digest
        return raw
    read(__file__)
    coverage = json.loads(read(COVERAGE, COVERAGE_SHA))
    for path, digest in coverage['source_hashes'].items():
        read(path, digest)
    for name in ('data/providers.py', 'data/fetch.py'):
        read(ROOT / name)
    cohorts = [coverage['dates'][0], coverage['dates'][-1]]
    for cohort in cohorts:
        if len(cohort['candidates']) != 101 or len({row['cusip'] for row in cohort['candidates']}) != 101:
            raise ValueError('Complete unique 101-CUSIP cohort required')
    tickers = {row['ticker'] for cohort in cohorts for row in cohort['candidates']}
    listing = subprocess.check_output(['rg', '--files', '--no-ignore', 'data/cache'], cwd=ROOT, encoding='utf-8').splitlines()
    paths = sorted((ROOT / path).resolve() for path in listing if Path(path).suffix.lower() == '.csv' and Path(path).stem in tickers)
    indexed, tables = {}, {}
    for path in paths:
        raw = read(path)
        table = pd.read_csv(io.BytesIO(raw))
        if not {'Date', 'Close'} <= set(table):
            continue
        table['Date'] = table['Date'].astype(str)
        sidecar_path = path.with_suffix('.csv.manifest.json')
        sidecar = json.loads(read(sidecar_path)) if sidecar_path.exists() else None
        own_sha = sources[str(path)]
        close = pd.to_numeric(table['Close'], errors='coerce')
        open_values = pd.to_numeric(table['Open'], errors='coerce') if 'Open' in table else None
        indexed[str(path)] = dict(ticker_filename=path.stem, path=str(path), sha256=own_sha,
            columns=list(table.columns), row_count=len(table), date_start=table['Date'].min(), date_end=table['Date'].max(),
            duplicate_dates=int(table['Date'].duplicated().sum()), dates_sorted=table['Date'].tolist() == sorted(table['Date']),
            missing_or_nonpositive_close=int((close.isna() | close.le(0)).sum()),
            missing_or_nonpositive_open=None if open_values is None else int((open_values.isna() | open_values.le(0)).sum()),
            storage_role='MUTABLE_RETURN_ENGINE_CACHE' if path.parent == (ROOT / 'data/cache').resolve() else 'SEPARATE_RESEARCH_PRICE_CACHE',
            source=sidecar.get('source') if sidecar else None,
            declared_price_basis=sidecar.get('price_basis') if sidecar else None,
            declared_adjustment=sidecar.get('corporate_action_adjustment') if sidecar else None,
            source_request_mode=sidecar.get('source_request_mode') if sidecar else None,
            dataset_type=sidecar.get('dataset_type') if sidecar else None,
            valuation_use_only=sidecar.get('valuation_use_only') if sidecar else None,
            whole_lot_execution_use_only=sidecar.get('whole_lot_execution_use_only') if sidecar else None,
            declared_return_usage_allowed=sidecar.get('return_usage_allowed') if sidecar else None,
            manifest_path=str(sidecar_path) if sidecar else None,
            manifest_content_sha256_matches=sidecar.get('content_sha256') == own_sha if sidecar else None,
            manifest_declared_data_end=sidecar.get('data_end') if sidecar else None,
            received_at_utc=sidecar.get('fetched_at') if sidecar else None,
            provider_history_identity_binding_verified=False)
        tables[str(path)] = table
    identity_path = ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv'
    taxonomy_path = ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/taxonomy_records.csv'
    identities = pd.read_csv(io.BytesIO(read(identity_path)), dtype=str).fillna('')
    taxonomy = pd.read_csv(io.BytesIO(read(taxonomy_path)), dtype=str).fillna('')
    output_cohorts = []
    for cohort in cohorts:
        cutoff = cohort['decision_cutoff']
        matching_context = [Path(path) for path, digest in coverage['source_hashes'].items()
            if Path(path).name == 'context.json' and digest == cohort['old_context_sha256']]
        if len(matching_context) != 1:
            raise ValueError('Original cutoff context ambiguous')
        context = json.loads(read(matching_context[0], cohort['old_context_sha256']))
        prepared = context['prepared_inputs']
        fit_days = prepared['contract']['payload']['mapping']['fit_days']
        original_sessions = [row['timestamp'][:10] for row in prepared['returns']['payload']['mapping']['index']['items']]
        original_sessions = [day for day in original_sessions if day <= cutoff]
        close_reference = original_sessions[-(fit_days + 1):]
        if len(close_reference) != fit_days + 1 or close_reference[-1] != cutoff:
            raise ValueError('Original fit window plus prior close not explicit')
        rows = []
        for candidate in cohort['candidates']:
            ticker, cusip = candidate['ticker'], candidate['cusip']
            assets = []
            for path, descriptor in indexed.items():
                if descriptor['ticker_filename'] != ticker:
                    continue
                table = tables[path]
                before = table.loc[table['Date'] <= cutoff]
                dates = set(table['Date'])
                absent = [day for day in close_reference if day not in dates]
                relevant = before.loc[before['Date'].isin(close_reference)]
                prices = pd.to_numeric(relevant['Close'], errors='coerce')
                assets.append(dict(path=path, rows_at_or_before_cutoff=len(before),
                    last_row_at_or_before_cutoff=before['Date'].max() if len(before) else None,
                    cutoff_session_present=cutoff in dates, original_reference_close_dates=len(close_reference),
                    missing_original_reference_close_dates=absent,
                    original_reference_close_values_complete=not absent and bool(prices.notna().all() and prices.gt(0).all()),
                    not_return_or_execution_admission=True))
            local_identity = identities.loc[identities['cusip'].eq(cusip)].to_dict('records')
            local_taxonomy = taxonomy.loc[taxonomy['cusip'].eq(cusip)].to_dict('records')
            rows.append(dict(candidate= candidate, local_price_assets=assets,
                exact_ticker_filename_match_only=True, ticker_aliases_joined=False,
                local_identity_records=local_identity, local_taxonomy_records=local_taxonomy,
                evidence_paths=dict(identity=str(identity_path), risk=str(taxonomy_path)),
                return_cache_present=any(indexed[row['path']]['storage_role']=='MUTABLE_RETURN_ENGINE_CACHE' for row in assets),
                declared_nominal_cache_present=any(indexed[row['path']]['declared_price_basis']=='unadjusted_nominal_trade_price' for row in assets),
                existing_complete_reference_close_asset_count=sum(row['original_reference_close_values_complete'] for row in assets),
                new_scope_eligibility_decision='PROXY_COHORT_MEMBER_NOT_EXACT_DAILY_INDEX_ADMISSION',
                strategy_information_pit_verified=False, source_coordinate_adjudication_required=True))
        output_cohorts.append(dict(coordinate=cohort['coordinate'], decision_cutoff=cutoff,
            proxy_report_date=cohort['proxy_report_date'], proxy_available_date=cohort['proxy_available_date'],
            original_fit_days=fit_days, original_reference_close_dates=close_reference,
            candidate_count=len(rows), unique_cusip_count=len({row['candidate']['cusip'] for row in rows}), rows=rows,
            return_cache_present_count=sum(row['return_cache_present'] for row in rows),
            declared_nominal_cache_present_count=sum(row['declared_nominal_cache_present'] for row in rows),
            at_least_one_complete_reference_close_asset_count=sum(row['existing_complete_reference_close_asset_count']>0 for row in rows)))
    for path, digest in list(sources.items()):
        read(path, digest)
    return dict(schema='ndx_full_pool_local_data_matrix_v1', scope='LOCAL_AVAILABILITY_NOT_DATA_AUTHENTICITY_OR_MEMBERSHIP_ADMISSION',
        coverage_sha256=COVERAGE_SHA, cohorts=output_cohorts, assets=indexed, source_hashes=sources,
        discovered_cache_file_count=len(listing), examined_exact_ticker_csv_count=len(paths),
        candidate_union_cusip_count=len({row['cusip'] for cohort in cohorts for row in cohort['candidates']}),
        candidate_union_ticker_count=len(tickers), observed_at_utc=datetime.now(timezone.utc).isoformat(),
        inventory_discovery_method='rg --files --no-ignore data/cache; exact candidate ticker CSV basenames only',
        discovery_limit='Lists existing per-ticker CSV sources and formal identity/risk records; not all arbitrary embedded JSON price panels.',
        return_basis_limit='Root cache is used by LocalCacheProvider but has no per-file basis provenance here. Current provider source permits different adjustment paths; do not infer realized provider or historic adjustment from ticker filename.',
        nominal_usage_limit='Valuation-only raw nominal sources need separately approved provenance and usage contract before returns or execution use; do not mix nominal prices across splits.',
        next_safe_development='Freeze chosen existing source bytes for a new all-NDX proxy diagnostic delta, independently specify return adjustment and identity contracts, preserve missing/conflicting cases and old training evidence.',
        fetched_new_data=False, training_performed=False, old_training_rerun=False,
        exact_daily_membership_verified=False, price_identity_binding_verified=False, point_in_time_verified=False,
        execution_performed=False, promotion_allowed=False)


if __name__ == '__main__':
    report = build_report()
    output = ROOT / 'data/cache/research/dynamic_frozen_v2/full_pool_local_data_matrix_20260912.json'
    encoded = (json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode()
    with output.open('xb') as handle:
        handle.write(encoded)
    print(json.dumps(dict(path=str(output), sha256=hashlib.sha256(encoded).hexdigest(),
        cohorts=[{k:v for k,v in c.items() if k not in ('rows','original_reference_close_dates')} for c in report['cohorts']],
        asset_count=len(report['assets']))))

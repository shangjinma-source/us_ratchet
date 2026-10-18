"""Locate real legacy return differences and full-window availability without retraining."""
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'data/cache/research/root_return_semantics_probe_20260912_v1'


def run():
    sources = {}
    def read(path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and expected != digest:
            raise ValueError('Evidence source drift: ' + str(path))
        if str(path) in sources and sources[str(path)] != digest:
            raise ValueError('Source changed during investigation')
        sources[str(path)] = digest
        return raw
    read(__file__)
    for path in ('data/providers.py','data/fetch.py','data/cn_source.py','backtest/ndx_joint_weight_history_inputs.py',
                 'backtest/ndx_cardinality_discovery.py','backtest/ndx_joint_weight_evaluation.py'):
        read(ROOT / path)
    manifest = json.loads(read(DIRECTORY / 'manifest.json', '6e97c411b418513ce34ada62748eeace843cc6a54e033e68270ec8f6fb09991e'))
    for path, digest in manifest['source_hashes'].items():
        read(path, digest)
    coverage = json.loads(read(ROOT / 'data/cache/research/dynamic_frozen_v2/full_membership_coverage_20260912_v2.json',
        'eb15d117e6b3c07a41decf1666b5dfbcfda2fd25ee00ea05b5df680d7473dd64'))
    for path, digest in coverage['source_hashes'].items():
        read(path, digest)
    root_prices = {}
    def root_price(ticker):
        if ticker not in root_prices:
            table = pd.read_csv(io.BytesIO(read(ROOT / 'data/cache' / (ticker + '.csv'))), index_col='Date')
            if not table.index.is_unique or table.index.tolist() != sorted(table.index):
                raise ValueError('Invalid root date index')
            root_prices[ticker] = table.Close.astype(float)
        return root_prices[ticker]
    samples, known_errors = [], []
    for probe in manifest['probes']:
        if probe['http_status'] != 200:
            raise ValueError('Sample raw response missing')
        response, = json.loads(read(probe['response_path'], probe['response_sha256']))['chart']['result']
        ticker = response['meta']['symbol']
        dates = [datetime.fromtimestamp(value, ZoneInfo('America/New_York')).date().isoformat() for value in response['timestamp']]
        quote = pd.Series(response['indicators']['quote'][0]['close'], index=dates, dtype=float)
        adjusted = pd.Series(response['indicators']['adjclose'][0]['adjclose'], index=dates, dtype=float)
        root = root_price(ticker)
        series = pd.concat([root.rename('root'), quote.rename('quote'), adjusted.rename('adjclose')], axis=1).dropna()
        returns = series.pct_change(fill_method=None).dropna()
        window = returns.loc['2023-04-03':'2024-06-03']
        splits = []
        for event in response.get('events',{}).get('splits',{}).values():
            day = datetime.fromtimestamp(event['date'],ZoneInfo('America/New_York')).date().isoformat()
            position = dates.index(day)
            fact = dict(ticker=ticker, session=day, previous_session=dates[position-1],
                provider_quote_previous=float(quote.iloc[position-1]), provider_quote=float(quote.iloc[position]),
                split_numerator=event['numerator'], split_denominator=event['denominator'],
                provider_split_adjusted_price_return=float(returns.loc[day,'quote']),
                legacy_root_return=float(returns.loc[day,'root']),
                root_close_previous=float(root.loc[dates[position-1]]), root_close=float(root.loc[day]),
                raw_response_path=probe['response_path'], raw_response_sha256=probe['response_sha256'])
            splits.append(fact)
            if fact['legacy_root_return'] == 0 and abs(fact['provider_split_adjusted_price_return']) > .001:
                known_errors.append(fact)
        dividend_rows = []
        for event in response.get('events',{}).get('dividends',{}).values():
            day = datetime.fromtimestamp(event['date'],ZoneInfo('America/New_York')).date().isoformat()
            if day in returns.index and '2023-03-31' <= day <= '2024-06-03':
                dividend_rows.append(dict(session=day, provider_dividend_amount=event['amount'],
                    legacy_root_return=float(returns.loc[day,'root']), quote_return=float(returns.loc[day,'quote']),
                    adjclose_return=float(returns.loc[day,'adjclose'])))
        samples.append(dict(ticker=ticker, raw_response_path=probe['response_path'],
            max_target_window_root_vs_quote_return_difference=float((window.root-window.quote).abs().max()),
            max_target_window_root_vs_adjclose_return_difference=float((window.root-window.adjclose).abs().max()),
            observed_dividend_return_comparisons=dividend_rows, observed_split_comparisons=splits,
            inference='Evidence supports legacy price-return semantics with heuristic split-boundary distortion; not dividend total return. Individual provider revisions remain possible.'))
    locations, comparisons, full_coverage = [], [], []
    for number, cohort in enumerate(coverage['dates']):
        digest = cohort['old_context_sha256']
        context_path, = [Path(path) for path, expected in coverage['source_hashes'].items() if expected == digest and Path(path).name == 'context.json']
        context = json.loads(read(context_path,digest))
        panel = context['prepared_inputs']['returns']['payload']['mapping']
        dates = [value['timestamp'][:10] for value in panel['index']['items']]
        columns = panel['columns']['items']
        contract = context['prepared_inputs']['contract']['payload']['mapping']
        fit, forward, step = contract['fit_days'], contract['window_days'], contract['step_days']
        windows = []
        for ordinal, start in enumerate(range(fit, len(dates)-forward+1, step)):
            training, evaluation = dates[start-fit:start], dates[start:start+forward]
            windows.append(dict(window_ordinal=ordinal, fit_start=training[0],fit_end=training[-1],
                forward_start=evaluation[0],forward_end=evaluation[-1],
                known_errors_in_fit=[event for event in known_errors if event['ticker'] in columns and event['session'] in training],
                known_errors_in_forward=[event for event in known_errors if event['ticker'] in columns and event['session'] in evaluation]))
        locations.append(dict(coordinate=cohort['coordinate'],context_sha256=digest, return_rows=len(dates),
            training_start=dates[0],training_end=dates[-1],fit_days=fit,window_days=forward,step_days=step,windows=windows,
            windows_with_error_in_fit=sum(bool(row['known_errors_in_fit']) for row in windows),
            windows_with_error_in_forward=sum(bool(row['known_errors_in_forward']) for row in windows)))
        for sample in samples:
            ticker=sample['ticker']
            if ticker not in columns:
                continue
            values=[float.fromhex(value['float_hex']) for value in panel['column_values']['items'][columns.index(ticker)]['items']]
            legacy=pd.Series(values,index=dates)
            derived=root_price(ticker).pct_change(fill_method=None).reindex(dates)
            if derived.isna().any():
                raise ValueError('Sample source missing actual legacy training return')
            delta=(legacy-derived).abs()
            comparisons.append(dict(context_sha256=digest,coordinate=cohort['coordinate'],ticker=ticker,
                compared_rows=len(dates),max_absolute_difference=float(delta.max()),exact_float_equal=bool((delta==0).all())))
        if number in (0,len(coverage['dates'])-1):
            rows=[]
            for candidate in cohort['candidates']:
                ticker=candidate['ticker'];series=root_price(ticker)
                absent=[day for day in dates if day not in series.index]
                rows.append(dict(ticker=ticker,cusip=candidate['cusip'],source_path=str(ROOT/'data/cache'/(ticker+'.csv')),
                    source_date_start=series.index[0],source_date_end=series.index[-1],
                    expected_full_training_return_dates=len(dates),missing_full_training_close_dates=absent,
                    prior_close_before_first_return_present=bool((series.index<dates[0]).any()),
                    complete_dates_and_prior_close=not absent and bool((series.index<dates[0]).any()),
                    ticker_history_joined=False))
            full_coverage.append(dict(coordinate=cohort['coordinate'],candidate_count=len(rows),rows=rows,
                complete_full_training_dates_and_prior_close_count=sum(row['complete_dates_and_prior_close'] for row in rows)))
    report=dict(schema='ndx_root_return_semantics_review_v1',source_hashes=sources,samples=samples,
        known_split_day_return_errors=known_errors, actual_context_return_comparisons=comparisons,
        actual_window_error_locations=locations,first_last_full_training_data_coverage=full_coverage,
        implementation_finding='SinaProvider invokes split_adjust; split_adjust multiplies earlier prices by actual adjacent close ratio rather than declared exact share ratio, making detected event-day root return zero. No dividends are added by this branch.',
        lineage_limit='No per-root-file provider or adjustment manifest is written by fetch._write_cache; matching sampled actual training returns proves local lineage, not all-111 provider provenance. Targeted local fetch log search yielded no matching entries.',
        impact_rule='A forward error in a positive-weight incumbent return affects the incumbent comparison even if the candidate excludes that ticker. Fit-only errors affect non-equal candidate weights only if the ticker belongs to that candidate; equal weights do not consume fit covariance. Audit other scorer dependencies before exact reuse.',
        reuse_decision='No blanket rejection or rerun of 351255 records. Preserve old evidence; use per-window candidate/incumbent dependency masks to identify affected metrics. New scope needs explicitly corrected split-neutral price returns and full history/alias resolution.',
        all_root_cache_returns_authorized_for_new_scope=False, current_cache_modified=False,
        training_performed=False, old_records_invalidated_or_rerun=False, point_in_time_verified=False,promotion_allowed=False)
    for path,digest in list(sources.items()):read(path,digest)
    output=DIRECTORY/'root_return_semantics_review_20260912.json'
    raw=(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n').encode()
    with output.open('xb') as handle:handle.write(raw)
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(raw).hexdigest(),
        known_error_count=len(known_errors),contexts=len(locations),comparisons=len(comparisons),
        all_compared_returns_exact=all(row['exact_float_equal'] for row in comparisons),
        window_counts=[(row['coordinate']['selection_date'],row['windows_with_error_in_fit'],row['windows_with_error_in_forward']) for row in locations])))


if __name__=='__main__':run()

"""Read-only 15-proxy-date provider inventory; no ticker history is inferred."""
from collections import Counter,defaultdict
from datetime import datetime
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
from urllib.parse import urlparse,parse_qs,unquote
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=ROOT/'data/cache/research'
COVERAGE=RESEARCH/'dynamic_frozen_v2/full_membership_coverage_20260912_v2.json'
COVERAGE_SHA='eb15d117e6b3c07a41decf1666b5dfbcfda2fd25ee00ea05b5df680d7473dd64'
LOCAL=RESEARCH/'dynamic_frozen_v2/full_pool_local_data_matrix_20260912.json'
LOCAL_SHA='6fa8cc7cb7fea3ced004267f3fccc2085c89d31ce7056d2b3d44d9c9f1e1fdcb'
MANIFEST_NAMES=(
    'identity_public_source_probe_20260912_v1/manifest.json',
    'preference_price_action_source_probe_20260912_v1/manifest.json',
    'preference_price_action_supplement_20260912_v1/manifest.json',
    'incumbent_price_source_probe_20260912_v1/manifest.json',
    'root_return_semantics_probe_20260912_v1/manifest.json',
    'meta_historical_price_source_probe_20260912_v1/manifest.json',
    'legacy_pool_additional_split_probe_20260912_v1/report.json',
    'legacy_pool_remaining_split_probe_20260912_v1/report.json',
    'full_history_gap_source_probe_20260912_v1/manifest.json',
    'full_history_gap_source_probe_20260912_v1/ceg_when_issued_manifest.json')


def build():
    sources={}
    def bind(path,expected=None):
        path=Path(path).resolve();raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if expected is not None and sha!=expected:raise ValueError('Source binding differs: '+str(path))
        if str(path) in sources and sources[str(path)]!=sha:raise ValueError('Source drift/conflict')
        sources[str(path)]=sha;return raw
    def load(path,expected=None):return json.loads(bind(path,expected))
    def closure(mapping):
        for path,sha in mapping.items():bind(path,sha)
    membership=load(COVERAGE,COVERAGE_SHA);local=load(LOCAL,LOCAL_SHA)
    closure(membership['source_hashes']);closure(local['source_hashes'])
    if len(membership['dates'])!=15 or any(len(row['candidates'])!=101 for row in membership['dates']):
        raise ValueError('Exact 15 dates x101 proxy securities required')
    candidates=defaultdict(list);calendars={};raw_captures={};provider_failures=[]
    for cohort in membership['dates']:
        date=cohort['coordinate']['selection_date'];sha=cohort['old_context_sha256']
        context_path,=[Path(path) for path,value in membership['source_hashes'].items() if value==sha and Path(path).name=='context.json']
        context=load(context_path,sha)
        days=[row['timestamp'][:10] for row in context['prepared_inputs']['returns']['payload']['mapping']['index']['items']]
        calendars[date]=days
        for row in cohort['candidates']:
            candidates[row['ticker']].append(dict(selection_date=date,decision_cutoff=cohort['decision_cutoff'],**row))
    for name in MANIFEST_NAMES:
        manifest_path=RESEARCH/name;manifest=load(manifest_path);closure(manifest.get('source_hashes',{}))
        for probe in manifest.get('probes',[]):
            url=probe.get('request',{}).get('url',probe.get('requested_channel_url',''))
            parsed=urlparse(url)
            if parsed.hostname not in ('query1.finance.yahoo.com','query2.finance.yahoo.com') or '/v8/finance/chart/' not in parsed.path:continue
            ticker=unquote(parsed.path.split('/v8/finance/chart/',1)[1])
            if probe.get('http_status')!=200 or not probe.get('response_path'):
                provider_failures.append(dict(ticker=ticker,manifest_path=str(manifest_path),probe=probe));continue
            path=Path(probe['response_path']).resolve();raw=bind(path,probe['response_sha256'])
            if len(raw)!=probe['response_bytes']:raise ValueError('Capture byte denominator differs')
            reference=dict(manifest_path=str(manifest_path),manifest_sha256=sources[str(manifest_path.resolve())],
                probe_name=probe['name'],request_url=url,received_at_utc=probe.get('received_at_utc'),
                response_saved_at_utc=probe.get('response_saved_at_utc'),
                exact_request_url_recovered=not probe.get('request_url_exact_not_recovered',False),
                http_status=probe['http_status'],http_status_evidence=probe.get('http_status_evidence','CAPTURE_METADATA'))
            if str(path) in raw_captures:
                if raw_captures[str(path)]['provider_request_ticker']!=ticker:raise ValueError('Same raw path conflicting provider ticker')
                raw_captures[str(path)]['manifest_references'].append(reference);continue
            chart,=json.loads(raw)['chart']['result'];quotes,=chart['indicators']['quote']
            if chart['meta'].get('exchangeTimezoneName')!='America/New_York':raise ValueError('Unexpected raw session timezone')
            if chart['meta']['symbol']!=ticker:raise ValueError('Provider response symbol differs')
            timestamps=chart['timestamp'];days=[datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for t in timestamps]
            if len(days)!=len(set(days)) or days!=sorted(days):raise ValueError('Nonunique/unordered raw sessions')
            valid_close=[];valid_open=[]
            for field,valid in [('close',valid_close),('open',valid_open)]:
                if len(quotes[field])!=len(days):raise ValueError('Raw quote array denominator differs')
                for day,value in zip(days,quotes[field]):
                    if type(value) in (int,float) and math.isfinite(value) and value>0:valid.append(day)
            receipt=probe.get('received_at_utc');saved=probe.get('response_saved_at_utc')
            conservative_date=(datetime.fromisoformat((receipt or saved).replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                if receipt or saved else None)
            complete=[day for day in valid_close if conservative_date is not None and day<conservative_date]
            capture=dict(provider_request_ticker=ticker,response_symbol=chart['meta']['symbol'],path=str(path),sha256=probe['response_sha256'],
                bytes=len(raw),currency=chart['meta'].get('currency'),observed_row_count=len(days),date_start=days[0],date_end=days[-1],
                raw_close_valid_count=len(valid_close),raw_open_valid_count=len(valid_open),session_dates=days,
                valid_close_dates=valid_close,valid_open_dates=valid_open,conservatively_completed_close_dates=complete,
                unfinalized_or_same_day_sessions=[day for day in days if conservative_date is None or day>=conservative_date],
                completion_cutoff_source='EXACT_RECEIPT_NEW_YORK_DATE' if receipt else 'SAVED_TIME_ONLY_RECEIPT_UNKNOWN',
                exact_receipt_available=receipt is not None,request_parameters=parse_qs(parsed.query,keep_blank_values=True),
                adjclose_is_separate_field=bool(chart['indicators'].get('adjclose')),split_events=chart.get('events',{}).get('splits',{}),
                dividend_event_count=len(chart.get('events',{}).get('dividends',{})),manifest_references=[reference],
                request_symbol_is_not_historical_ticker_identity=True,nominal_quote_basis_adjudicated=False,
                full_provider_event_completeness_certified=False,historical_price_security_binding_verified=False)
            raw_captures[str(path)]=capture
    captures_by_ticker=defaultdict(list)
    for path,capture in raw_captures.items():captures_by_ticker[capture['provider_request_ticker']].append(path)
    meta_reference=[row for row in raw_captures.values() if row['provider_request_ticker']=='META' and row['date_start']=='2022-01-03']
    if len(meta_reference)!=1:raise ValueError('Unique observed complete reference calendar required')
    reference_dates=[day for day in meta_reference[0]['session_dates'] if '2022-01-03'<=day<='2024-05-31']
    previous_by_date={day:reference_dates[index-1] for index,day in enumerate(reference_dates) if index>0}
    # Original first/last-only matrix omitted SPLK. Inspect its exact two local paths without fetching.
    assets=dict(local['assets'])
    discovered=subprocess.check_output(['rg','--files','--no-ignore','data/cache'],cwd=ROOT,text=True,encoding='utf8').splitlines()
    for relative in discovered:
        path=(ROOT/relative).resolve()
        if path.name!='SPLK.csv':continue
        raw=bind(path);rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        dates=[row['Date'][:10] for row in rows]
        sidecar=Path(str(path)+'.manifest.json');manifest=load(sidecar) if sidecar.exists() else {}
        if manifest and manifest.get('content_sha256')!=sources[str(path)]:raise ValueError('SPLK sidecar differs')
        assets[str(path)]=dict(path=str(path),sha256=sources[str(path)],ticker_filename='SPLK',date_start=min(dates),date_end=max(dates),
            row_count=len(rows),manifest_path=str(sidecar) if manifest else None,
            storage_role='VALUATION_ONLY_DECLARED_NOMINAL' if manifest.get('valuation_use_only') else 'MUTABLE_RETURN_ENGINE_CACHE',
            declared_adjustment=manifest.get('adjustment'),valuation_use_only=manifest.get('valuation_use_only'),
            provider_history_identity_binding_verified=False)
    gap=load(RESEARCH/'full_history_gap_source_probe_20260912_v1/gap_review_20260912.json');closure(gap['source_hashes'])
    meta_identity=load(RESEARCH/'meta_historical_price_source_probe_20260912_v1/retrospective_identity_scenarios_20260912.json')
    closure(meta_identity['source_hashes'])
    csv_valid_dates={}
    for path,asset in assets.items():
        records=list(csv.DictReader(io.StringIO(bind(path,asset['sha256']).decode('utf-8-sig'))))
        valid=set()
        for record in records:
            day=record.get('Date',record.get('date',''))[:10]
            try:value=float(record.get('Close',record.get('close','')))
            except (ValueError,TypeError):continue
            if len(day)==10 and math.isfinite(value) and value>0:valid.add(day)
        csv_valid_dates[path]=valid
    rows=[];date_stats=defaultdict(Counter)
    for ticker,appearances in sorted(candidates.items()):
        identities={(row['security_id'],row['issuer_id'],row['cusip']) for row in appearances}
        paths=captures_by_ticker.get(ticker,[]);variants=[raw_captures[path] for path in paths]
        matching_assets=[asset for asset in assets.values() if asset['ticker_filename']==ticker]
        supported=[]
        for item in appearances:
            days=calendars[item['selection_date']]
            if any(day not in previous_by_date for day in days):raise ValueError('Original training calendar outside observed reference')
            required=set(days)|{previous_by_date[day] for day in days}
            complete=[variant['path'] for variant in variants if required<=set(variant['conservatively_completed_close_dates'])]
            nominal=[variant['path'] for variant in variants if required<=set(variant['valid_open_dates'])&set(variant['conservatively_completed_close_dates'])]
            supported.append(dict(selection_date=item['selection_date'],original_return_date_count=len(days),
                required_close_date_count=len(required),single_capture_complete_training_close_paths=complete,
                single_capture_complete_training_open_close_paths=nominal,
                local_csv_close_coverage=[dict(path=asset['path'],sha256=asset['sha256'],
                    required_close_count=len(required),missing_close_count=len(required-csv_valid_dates[asset['path']]),
                    complete_dates_do_not_authorize_return_or_execution_use=True) for asset in matching_assets],
                provider_missing_close_counts={variant['path']:len(required-set(variant['conservatively_completed_close_dates'])) for variant in variants}))
            date_stats[item['selection_date']]['proxy_count']+=1
            date_stats[item['selection_date']]['with_provider_capture']+=bool(paths)
            date_stats[item['selection_date']]['single_capture_complete_training']+=bool(complete)
        full2022=[variant['path'] for variant in variants if set(reference_dates)<=set(variant['conservatively_completed_close_dates'])]
        if not paths:status='NO_SEALED_RAW_PROVIDER_CAPTURE_LOCAL_CSV_SOURCES_ONLY'
        elif all(row['single_capture_complete_training_close_paths'] for row in supported):status='CAPTURE_COVERS_ALL_APPLICABLE_ORIGINAL_TRAINING_CALENDARS'
        else:status='CAPTURE_PRESENT_BUT_SOME_ORIGINAL_TRAINING_DATES_MISSING'
        identity_notes=[]
        if ticker=='META':identity_notes.append('BOUNDED_RETROSPECTIVE_FB_TO_META_20220609_PROJECTION_AVAILABLE_NOT_PIT')
        if ticker in gap.get('corporate_event_facts',{}):identity_notes.append(gap['corporate_event_facts'][ticker])
        if ticker=='SPLK':identity_notes.append('MIDDLE_PROXY_DATES_ONLY_NOT_IN_PRIOR_FIRST_LAST_MATRIX;PROXY_LAG_NOT_OFFICIAL_CURRENT_MEMBERSHIP')
        rows.append(dict(ticker=ticker,identity_coordinates=[dict(security_id=sid,issuer_id=issuer,cusip=cusip) for sid,issuer,cusip in sorted(identities)],
            date_appearances=[dict(selection_date=item['selection_date'],decision_cutoff=item['decision_cutoff'],
                local_risk_chain_evidence=item['local_risk_chain_evidence'],unambiguous_local_risk_evidence=item['unambiguous_local_risk_evidence']) for item in appearances],
            provider_capture_paths=paths,raw_capture_status=status,original_training_date_support=supported,
            single_capture_complete_observed_2022_start_to_20240531_paths=full2022,
            local_csv_assets=matching_assets,known_identity_evidence_or_gaps=identity_notes,
            only_root_unmanifested_or_valuation_only_csvs=all(asset.get('valuation_use_only') is True
                or asset['storage_role']=='MUTABLE_RETURN_ENGINE_CACHE' for asset in matching_assets),
            old_execution_only_csv_paths=[asset['path'] for asset in matching_assets if asset.get('whole_lot_execution_use_only') is True],
            historical_ticker_continuity_certified=False,provider_channel_to_security_identity_certified=False,
            next_required_work='OBTAIN_MISSING_RAW_SOURCE_AND_HISTORICAL_IDENTITY' if not paths else
                'REVIEW_EXISTENCE_PREDECESSOR_AND_MISSING_SESSIONS_WITHOUT_ZERO_FILL' if status.endswith('MISSING') else
                'ADJUDICATE_PRICE_BASIS_AND_HISTORICAL_IDENTITY_FOR_NEW_SCOPE_INPUT'))
    counts=dict(Counter(row['raw_capture_status'] for row in rows))
    source=Path(__file__).resolve();bind(source)
    for path,sha in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Source drift during provider inventory')
    return dict(schema='ndx_full_proxy_provider_capture_inventory_v1',candidate_rows=rows,raw_captures=raw_captures,
        source_hashes=sources,status_counts=counts,date_count=15,proxy_rows=1515,union_ticker_count=len(rows),
        union_security_count=len({item['security_id'] for group in candidates.values() for item in group}),
        union_issuer_count=len({item['issuer_id'] for group in candidates.values() for item in group}),
        middle_dates_not_in_prior_first_last_asset_matrix=sorted(set(candidates)-{row['ticker_filename'] for row in local['assets'].values()}),
        candidate_tickers_with_raw_capture=[row['ticker'] for row in rows if row['provider_capture_paths']],
        no_raw_provider_capture_tickers=[row['ticker'] for row in rows if not row['provider_capture_paths']],
        no_raw_and_only_root_or_valuation_csv_tickers=[row['ticker'] for row in rows
            if not row['provider_capture_paths'] and row['only_root_unmanifested_or_valuation_only_csvs']],
        no_raw_but_old_execution_csv_tickers=[row['ticker'] for row in rows
            if not row['provider_capture_paths'] and row['old_execution_only_csv_paths']],
        complete_observed_2022_start_raw_tickers=[row['ticker'] for row in rows
            if row['single_capture_complete_observed_2022_start_to_20240531_paths']],
        provider_channels_outside_proxy_union=sorted(set(captures_by_ticker)-set(candidates)),
        raw_response_file_count=len(raw_captures),provider_failure_records=provider_failures,
        date_coverage=[dict(selection_date=day,**dict(count)) for day,count in sorted(date_stats.items())],
        coverage_reference='UNION_OF_ACTUAL_OLD_RETURN_DATES_PLUS_ADJACENT_META_PROVIDER_OBSERVED_CLOSE_NOT_EXCHANGE_CALENDAR_CERTIFICATION',
        source_discovery_scope=list(MANIFEST_NAMES),source_capture_selection_uses_returns=False,
        no_capture_variants_stitched=True,classification_based_on_raw_availability_not_candidate_admission=True,
        proxy_membership_is_not_official_ndx_membership=True,all_historical_ticker_continuity_still_uncertified=True,
        new_network_requests_performed=False,old_cache_modified=False,training_performed=False,
        point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    output=RESEARCH/'dynamic_frozen_v2/full_proxy_provider_capture_inventory_20260912.json'
    if output.exists():raise FileExistsError(output)
    report=build();raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with output.open('xb') as stream:stream.write(raw)
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(raw).hexdigest(),counts=report['status_counts'],
        union_tickers=report['union_ticker_count'],union_issuers=report['union_issuer_count'],
        captured_tickers=report['candidate_tickers_with_raw_capture'],outside_proxy=report['provider_channels_outside_proxy_union'])))

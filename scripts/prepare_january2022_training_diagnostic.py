"""Build a real 101-member compiler-shaped draft and retain explicit rejections."""
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import gzip

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtest.return_priority_monthly_training_inputs import compile_monthly_training_window

OUT = ROOT / 'tmp/qqq_20201231_anchor_20261025'


def prepare():
    hashes = {}
    def read(path):
        raw = path.read_bytes()
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(raw).hexdigest()
        return raw
    domain = json.loads(read(OUT/'monthly_member_domain_v1.json'))
    window = next(row for row in domain['decisions'] if row['decision_cutoff']=='2021-12-31')
    routes = json.loads(read(OUT/'monthly_price_routes_v5_fields.json'))
    coordinate = json.loads(read(OUT/'local_split_coordinate_review.json'))
    anchor = json.loads(read(OUT/'nominal_anchor_quote_diagnostic.json'))
    official = json.loads(read(OUT/'official_split_semantics_batch1.json'))
    completed_splits = json.loads(read(ROOT/'tmp/official_splits_2021_20261026/evidence.json'))
    eight_anchor = json.loads(read(ROOT/'tmp/qqq_20211231_eight_anchor_20261026/eight_nominal_anchor_review.json'))
    if eight_anchor['date'] != window['decision_cutoff']:
        raise ValueError('DECISION_ANCHOR_DATE_MISMATCH')
    eight_by_ticker = {row['ticker']:row for row in eight_anchor['rows']}
    for path,digest in completed_splits['files'].items():
        content = read(ROOT/path)
        if hashlib.sha256(content).hexdigest()!=digest:
            raise ValueError('COMPLETED_SPLIT_EVIDENCE_HASH_MISMATCH:'+path)
    holdings = json.loads(read(OUT/'holdings_identity_comparison.json'))
    events = json.loads(read(OUT/'recent_member_event_review.json'))
    read(ROOT/'docs/free_history_alias_review_20261025.md')
    identity_by_ticker = {}
    primary_anchor = 'https://www.sec.gov/Archives/edgar/data/1067839/000175272421043706/edgar.htm'
    for row in holdings['rows']:
        identity_by_ticker[row['candidate_ticker']] = dict(name=row['company_and_class'],
            source_references=[primary_anchor,'tmp/qqq_20201231_anchor_20261025/holdings_identity_comparison.json'],
            evidence_role='DATED_20201231_PRIMARY_HOLDING_NAME_WITH_EXPLICIT_TICKER_CROSSWALK')
    entrant_names = {'HON':'Honeywell International Inc.','CRWD':'CrowdStrike Holdings, Inc.',
        'ABNB':'Airbnb, Inc.','DDOG':'Datadog, Inc.','FTNT':'Fortinet, Inc.',
        'LCID':'Lucid Group, Inc.','PANW':'Palo Alto Networks, Inc.','ZS':'Zscaler, Inc.'}
    for event in events['records']:
        if event['official_effective_date'] > window['decision_cutoff']:
            continue
        for ticker in event['official_added']:
            if ticker in entrant_names:
                identity_by_ticker[ticker] = dict(name=entrant_names[ticker],
                    source_references=[event['source_url'],'tmp/qqq_20201231_anchor_20261025/recent_member_event_review.json'],
                    evidence_role='OFFICIAL_NAMED_MEMBER_ENTRY',valid_from=event['official_effective_date'])
    by_ticker = {row['ticker']:row for row in routes['matrix'] if row['decision_cutoff']==window['decision_cutoff']}
    coords = {row['ticker']:row for row in coordinate['rows']}
    anchors = {row['ticker']:row for row in anchor['rows']}
    holding_values = {row['candidate_ticker']:row for row in holdings['rows']}
    read(ROOT/'backtest/return_priority_monthly_training_inputs.py')
    rows, diagnostics, identity_bindings, unit_diagnostics = [], [], [], []
    for ticker in window['full_members']:
        candidates = [item['path'] for item in by_ticker[ticker]['sources']]
        preferred = {
            'ATVI':'tmp/modern_archive_inventory_20261025/ATVI_price_candidate_2020_2023.csv',
            'XLNX':'tmp/chartexchange_gap_20261025/XLNX_price_candidate.csv',
            'ANSS':'tmp/andrewmvd_inventory_20261025/ANSS_stocks.csv',
            'EA':'tmp/andrewmvd_inventory_20261025/EA_stocks.csv'}
        source = preferred.get(ticker)
        if source is None:
            source = next((p for p in candidates if p.endswith('.response')), candidates[0] if candidates else None)
        closes = {}
        if source:
            raw = read(ROOT/source)
            if source.endswith('.response'):
                result = json.loads(raw)['chart']['result'][0]
                closes = {datetime.fromtimestamp(t,timezone.utc).date().isoformat():v for t,v in zip(result['timestamp'],result['indicators']['quote'][0]['close'])}
            else:
                for quote in csv.DictReader(raw.decode('utf-8-sig').splitlines()):
                    day = quote.get('date',quote.get('Date'))
                    if day[4:5]!='-':
                        day = datetime.strptime(day,'%d-%m-%Y').date().isoformat()
                    closes[day] = quote.get('close',quote.get('Close'))
        def valid(value):
            try:
                return value is not None and not isinstance(value,bool) and Fraction(str(value))>0
            except (ValueError,ZeroDivisionError):
                return False
        missing = [day for day in window['training_dates'] if not valid(closes.get(day))]
        identity = identity_by_ticker.get(ticker)
        issuer_key = {'GOOG':'alphabet','GOOGL':'alphabet','FOX':'fox-corporation','FOXA':'fox-corporation',
                      'FB':'meta-platforms','META':'meta-platforms','CTRP':'trip-com','TCOM':'trip-com'}.get(ticker,ticker.lower())
        security_key = {'GOOG':'alphabet-class-c','GOOGL':'alphabet-class-a','FOX':'fox-class-b','FOXA':'fox-class-a',
                        'FB':'meta-platforms-class-a','META':'meta-platforms-class-a','CTRP':'trip-com-ads','TCOM':'trip-com-ads'}.get(ticker,ticker.lower())
        issuer_id = 'research:issuer:'+issuer_key if identity else None
        security_id = 'research:security:'+security_key if identity else None
        blockers = ['TRAINING_COORDINATE_REVIEW_MISSING','DECISION_NOMINAL_COST_REVIEW_MISSING']
        if not identity:
            blockers.append('SECURITY_AND_ISSUER_ID_ADMISSION_MISSING')
        else:
            binding = dict(ticker=ticker,issuer_id=issuer_id,security_id=security_id,**identity,
                binding_scope='2021-12-31_DECISION_AND_2022JAN_RESEARCH_DOMAIN',
                status='RESEARCH_IDS_BOUND_TO_DATED_EVIDENCE_NOT_VENDOR_PERMANENT_IDS')
            if ticker=='FB':
                binding['dated_aliases']=[dict(ticker='FB',through='2022-06-08'),dict(ticker='META',valid_from='2022-06-09')]
                binding['source_references'].append('https://investor.atmeta.com/investor-news/press-release-details/2022/Meta-Platforms-Inc.-to-Change-Ticker-Symbol-to-META-on-June-9/default.aspx')
            identity_bindings.append(binding)
        if missing:
            blockers.append('ACTUAL_TRAINING_CLOSE_GAPS')
        # Constant post-cutoff coordinate factors cancel in every training ratio.
        # They affect the nominal per-share decision cost, which is restored once.
        factor = Fraction(1)
        within = []
        for event in coords.get(ticker,{}).get('events',[]):
            a,b = event['ratio'].split(':')
            if event['date'] > window['decision_cutoff']:
                factor *= Fraction(a)/Fraction(b)
            elif window['training_dates'][0] < event['date'] <= window['decision_cutoff']:
                within.append(event)
        anchor_factor = Fraction(str(coords.get(ticker,{}).get('provider_factor_product',1)))
        holding = holding_values.get(ticker)
        anchor_error = None
        if holding and valid(closes.get('2020-12-31')):
            expected = Fraction(holding['value_usd'])/Fraction(holding['shares'])
            anchor_error = float(abs(Fraction(str(closes['2020-12-31']))*anchor_factor-expected))
        confirmed = {(r['ticker'],r['ex_date']) for r in official['records']}
        for split in completed_splits['events']:
            if split['security_id']==ticker:
                matching = [event for event in within if event['date']==split['split_adjusted_trading_date']]
                if len(matching)!=1 or Fraction(matching[0]['ratio'].replace(':','/'))!=Fraction(split['ratio']):
                    raise ValueError('OFFICIAL_PROVIDER_SPLIT_MISMATCH:'+ticker)
                confirmed.add((ticker,split['split_adjusted_trading_date']))
        unresolved_inside = [event for event in within if (ticker,event['date']) not in confirmed]
        conditional_unit = anchor_error is not None and anchor_error <= 0.02 and not unresolved_inside and not missing
        unit_status = 'CONDITIONAL_ANCHOR_AND_PROVIDER_COORDINATE' if conditional_unit else 'REQUIRES_TARGETED_COORDINATE_REVIEW'
        cost = str(Fraction(str(closes[window['decision_cutoff']]))*factor) if conditional_unit else None
        cost_basis = 'POST_CUTOFF_PROVIDER_CONSTANT_WITH_PRIOR_SEC_NOMINAL_ANCHOR'
        if ticker in eight_by_ticker and not missing and not unresolved_inside:
            evidence = eight_by_ticker[ticker]
            if source != evidence['source'] or hashes[source]!=evidence['quote_source_sha256']:
                raise ValueError('DECISION_ANCHOR_PROVIDER_HASH_MISMATCH:'+ticker)
            # SEC market value is whole USD; recover quoted cents explicitly.
            exact_anchor = Fraction(evidence['value_usd'])/Fraction(evidence['shares'])
            quoted_anchor = Fraction(round(exact_anchor*100),100)
            if abs(exact_anchor-quoted_anchor)>Fraction(1,200):
                raise ValueError('DECISION_ANCHOR_CENT_PRECISION_MISMATCH:'+ticker)
            cost = str(quoted_anchor)
            factor = quoted_anchor/Fraction(str(closes[window['decision_cutoff']]))
            cost_basis = 'SAME_DAY_SEC_VALUE_PER_SHARE_ROUNDED_TO_CENTS_EXPLICITLY'
            conditional_unit = True
            unit_status = 'CONDITIONAL_SAME_DAY_NOMINAL_ANCHOR_CONSTANT_SCALE'
        if conditional_unit:
            blockers = [b for b in blockers if b not in ('TRAINING_COORDINATE_REVIEW_MISSING','DECISION_NOMINAL_COST_REVIEW_MISSING')]
        latest_events = []
        if not holding:
            cache = ROOT/f'data/cache/research/current_raw_capture_20261014_v1/{ticker}.response.bin'
            if cache.exists():
                cached = read(cache)
                cached = gzip.decompress(cached) if cached[:2]==b'\x1f\x8b' else cached
                result = json.loads(cached)['chart']['result'][0]
                latest_events = [dict(date=datetime.fromtimestamp(e['date'],timezone.utc).date().isoformat(),ratio=e['splitRatio']) for e in result.get('events',{}).get('splits',{}).values()]
        unit_diagnostics.append(dict(ticker=ticker,status=unit_status,post_cutoff_constant_factor=str(factor),
            decision_cost_basis=cost_basis,
            factor_is_historical_coordinate_only_not_corporate_action=True,
            nominal_anchor_absolute_error=anchor_error,unresolved_window_actions=unresolved_inside,
            latest_cached_events_for_unanchored_member=latest_events,
            rule='No factor applied to training closes; same post-cutoff factor cancels. Restore decision cost only; do not create future holding actions.'))
        rows.append(dict(ticker=ticker, security_id=security_id, issuer_id=issuer_id, status='READY_CONDITIONAL' if not blockers else 'PENDING_EVIDENCE_REVIEW',
            training_source=source, training_close=[str(closes[day]) if valid(closes.get(day)) else None for day in window['training_dates']],
            missing_training_dates=missing, decision_cost=cost, blockers=blockers))
        diagnostics.append(dict(ticker=ticker, source=source, complete_253_provider_close=not missing,
            decision_provider_close=str(closes[window['decision_cutoff']]) if valid(closes.get(window['decision_cutoff'])) else None,
            blockers=blockers, unit_evidence_tier='PROVIDER_FACTOR_ARITHMETIC_ONLY' if ticker in coords else
                ('SINGLE_2020_ANCHOR_NOT_FULL_COORDINATE_REVIEW' if ticker in anchors else 'NO_2020_ANCHOR_RECORD'),
            coordinate_review=coords.get(ticker), official_split_events=[r for r in official['records'] if r['ticker']==ticker],
            note='Conditionally reviewed constant coordinate factor restores decision_cost; unresolved cases retain null. No future holding action is injected.'))
    draft = dict(decision_cutoff=window['decision_cutoff'],training_dates=window['training_dates'],candidates=rows)
    ready = all(row['status']=='READY_CONDITIONAL' and not row['blockers'] for row in rows)
    admission = dict(status='REVIEWED_CONDITIONAL' if ready else 'PENDING_EVIDENCE_REVIEW',decision_date=window['decision_cutoff'],members=window['full_members'],
                     source_references=list(hashes),training_exclusions={})
    compiled = None
    compiler_rejection = None
    try:
        compiled = compile_monthly_training_window(window=draft,source_hashes=hashes,admission=admission)
    except ValueError as error:
        compiler_rejection = str(error)
    return dict(status='REAL_TRAINING_INPUT_COMPILED_CONDITIONALLY' if compiled else 'REAL_DATA_COMPILER_DRAFT_REJECTED',window=draft,admission=admission,
        compiled_search_arguments=compiled,
        execution_admission=False, economic_run_completed=False,
        execution_remaining=['Apply the same per-security coordinate to 2022 January execution close/open with source provenance.',
                            'Review January actual corporate actions separately; future adjustment constants are never holding events.',
                            'Check restored decision close equals compiled decision_cost exactly before execution assembly.'],
        source_hashes=hashes,per_security_review=diagnostics,identity_bindings=identity_bindings,compiler_rejection=compiler_rejection,
        identity_bound_count=len(identity_bindings), unresolved_identities=[row['ticker'] for row in rows if row['security_id'] is None],
        unit_diagnostics=unit_diagnostics, conditional_unit_ready_count=sum(r['decision_cost'] is not None for r in rows),
        complete_253_provider_close_count=sum(row['complete_253_provider_close'] for row in diagnostics),
        unproven_nominal_cost_count=sum(row['decision_cost'] is None for row in rows),
        source_priority_rule='Explicit reviewed candidates for ATVI/XLNX; fixed v1023 ANSS/EA; otherwise saved Yahoo, else existing archive. No performance selection.',
        next_required_fields=['January execution price-scale consistency and actual in-period actions'],
        search_calls=0,production_changes=False)


if __name__ == '__main__':
    result = prepare()
    (OUT/'january2022_training_diagnostic.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('status','identity_bound_count','unresolved_identities','complete_253_provider_close_count','unproven_nominal_cost_count','compiler_rejection','search_calls')}))

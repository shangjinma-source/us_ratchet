"""Freeze real 2021-2023 monthly compiler inputs; no search or production IO."""
import csv
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_training_inputs import compile_monthly_training_window

OUT=ROOT/'tmp/qqq_20201231_anchor_20261025'
ALIASES={'FB':'META','CTRP':'TCOM'}


def reviewed_coordinate_event(ticker, day, factor):
    """Price signal policy only; never returns an executable share action."""
    if ticker=='MTCH' and day=='2020-07-01' and factor==Fraction(1751,500):
        return dict(interpretation='REJECTED_PROVIDER_FACTOR_UNADJUSTED_MTCH_PRICE_ONLY_IDENTITY_BRIDGE',
                    apply_nominal_scale=False,training_allowed=True,
                    limitation='Old/new MTCH 1:1 price-only chain excludes the $3 cash or optional extra shares.',
                    evidence='tmp/mtch_reorganization_20261026/evidence.json')
    if ticker=='EXC' and day=='2022-02-02' and factor==Fraction(701,500):
        return dict(interpretation='PROVIDER_SPINOFF_ADJUSTED_PRICE_SIGNAL_NOT_TOTAL_RETURN',
                    apply_nominal_scale=True,training_allowed=True,
                    limitation='1.402 restores price units only; signal is not exact EXC plus 1/3 CEG wealth. Parent quantity remains unchanged.',
                    evidence='docs/exc_ceg_distribution_evidence_20261025.md')
    ordinary=factor.numerator<=20 and factor.denominator<=20
    return dict(interpretation='THIRD_PARTY_ORDINARY_SPLIT_CONDITIONAL_TRAINING_PRICE_ONLY' if ordinary else 'COMPLEX_PRICE_COORDINATE_REQUIRES_TRAINING_POLICY_REVIEW',
                apply_nominal_scale=True,training_allowed=ordinary)


def prepare():
    hashes={}
    def read(path):
        raw=path.read_bytes(); hashes[path.relative_to(ROOT).as_posix()]=hashlib.sha256(raw).hexdigest()
        return raw
    def load(path):
        return json.loads(read(path))
    domain=load(OUT/'monthly_member_domain_v1.json')
    inventory=load(OUT/'monthly_price_routes_v5_fields.json')
    single=load(OUT/'january2022_training_diagnostic.json')
    holdings=load(OUT/'holdings_identity_comparison.json')
    exclusions=load(OUT/'regular_way_eligibility_v1.json')
    membership=load(OUT/'recent_member_event_review.json')
    coordinates=load(OUT/'local_split_coordinate_review.json')
    recent_anchor_path=ROOT/'tmp/qqq_20221231_new_member_anchor_20261026/new_member_anchor_review.json'
    recent_anchor=load(recent_anchor_path)
    recent_anchor_rows={row['ticker']:row for row in recent_anchor['rows']}
    additional_anchor=load(ROOT/'tmp/ceg_on_ttd_anchor_20261026/three_anchor_review.json')
    additional_anchor_rows={row['ticker']:row for row in additional_anchor['rows']}
    mtch_evidence=load(ROOT/'tmp/mtch_reorganization_20261026/evidence.json')
    for path,expected in mtch_evidence['files'].items():
        raw=read(ROOT/path)
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('MTCH_EVIDENCE_CHANGED:'+path)
    read(ROOT/'docs/exc_ceg_distribution_evidence_20261025.md')
    read(ROOT/'tmp/exc_ceg_distribution_20261025/web_parsed_evidence.json')
    read(ROOT/'backtest/return_priority_monthly_training_inputs.py')
    exclusion_by_key={(r['ticker'],r['decision_cutoff']):r for r in exclusions['records'] if r['status']=='EXCLUDED_TRAINING_RULE'}
    old_cost={ALIASES.get(r['ticker'],r['ticker']):Fraction(r['decision_cost']) for r in single['window']['candidates']}
    old_id={ALIASES.get(r['ticker'],r['ticker']):dict(security_id=r['security_id'],issuer_id=r['issuer_id']) for r in single['window']['candidates']}
    anchor_2020={r['candidate_ticker']:Fraction(round(Fraction(r['value_usd'],r['shares'])*100),100) for r in holdings['rows']}
    coordinate_by_ticker={r['ticker']:r for r in coordinates['rows']}
    registry={}
    for plan in inventory['fixed_source_plan']:
        ticker=plan['ticker']; source=plan['source']
        raw=read(ROOT/source)
        if hashes[source]!=plan['sha256']:
            raise ValueError('FIXED_SOURCE_HASH_CHANGED:'+ticker)
        prices={}; events={}
        def ingest_events(result):
            for e in result.get('events',{}).get('splits',{}).values():
                day=datetime.fromtimestamp(e['date'],timezone.utc).date().isoformat()
                factor=Fraction(str(e['numerator']))/Fraction(str(e['denominator']))
                if day in events and events[day]!=factor:
                    raise ValueError('PROVIDER_EVENT_FACTOR_CONFLICT:'+ticker+':'+day)
                events[day]=factor
        if source.endswith('.response'):
            result=json.loads(raw)['chart']['result'][0]
            prices={datetime.fromtimestamp(t,timezone.utc).date().isoformat():Fraction(str(v))
                    for t,v in zip(result['timestamp'],result['indicators']['quote'][0]['close']) if v is not None and v>0}
            ingest_events(result)
        else:
            for row in csv.DictReader(raw.decode('utf-8-sig').splitlines()):
                day=row.get('date',row.get('Date'))
                if day[4:5]!='-':
                    day=datetime.strptime(day,'%d-%m-%Y').date().isoformat()
                value=row.get('close',row.get('Close'))
                try:
                    price=Fraction(value)
                    if price>0:prices[day]=price
                except (ValueError,ZeroDivisionError):
                    pass
        for event in coordinate_by_ticker.get(ticker,{}).get('events',[]):
            factor=Fraction(event['ratio'].replace(':','/'))
            if event['date'] in events and events[event['date']]!=factor:
                raise ValueError('LOCAL_PROVIDER_FACTOR_CONFLICT:'+ticker)
            events[event['date']]=factor
        canonical=ALIASES.get(ticker,ticker)
        cache=ROOT/f'data/cache/research/current_raw_capture_20261014_v1/{canonical}.response.bin'
        if cache.exists():
            cached=read(cache)
            cached=gzip.decompress(cached) if cached[:2]==b'\x1f\x8b' else cached
            payload=json.loads(cached)
            if payload.get('chart',{}).get('result'):
                ingest_events(payload['chart']['result'][0])
        identity=old_id.get(canonical)
        if identity is None:
            issuer={'GOOG':'alphabet','GOOGL':'alphabet','FOX':'fox-corporation','FOXA':'fox-corporation'}.get(ticker,canonical.lower())
            security={'FOX':'fox-class-b','FOXA':'fox-class-a','TCOM':'trip-com-ads'}.get(ticker,canonical.lower())
            identity=dict(security_id='research:security:'+security,issuer_id='research:issuer:'+issuer)
        identity_refs=[e['source_url'] for e in membership['records'] if ticker in e['official_added']]
        if ticker in anchor_2020:
            identity_refs.append('https://www.sec.gov/Archives/edgar/data/1067839/000175272421043706/edgar.htm')
        if canonical in old_id:identity_refs.append('tmp/qqq_20201231_anchor_20261025/january2022_training_diagnostic.json')
        if ticker in recent_anchor_rows:identity_refs.append(recent_anchor['source_url'])
        if ticker in additional_anchor_rows:identity_refs.append(additional_anchor_rows[ticker]['source_url'])
        calibration=None
        if canonical in old_cost and '2021-12-31' in prices:
            calibration=dict(date='2021-12-31',cost=old_cost[canonical],factor=old_cost[canonical]/prices['2021-12-31'],basis='REVIEWED_SINGLE_MONTH_NOMINAL_COST')
        elif ticker in anchor_2020 and '2020-12-31' in prices:
            calibration=dict(date='2020-12-31',cost=anchor_2020[ticker],factor=anchor_2020[ticker]/prices['2020-12-31'],basis='SEC_20201231_NOMINAL_ANCHOR_EXPLICIT_CENT_ROUNDING')
        elif ticker in recent_anchor_rows:
            row=recent_anchor_rows[ticker]; anchor_date=recent_anchor['last_trading_date']
            if row['source'].replace('\\','/')!=source or row['source_sha256']!=hashes[source]:
                raise ValueError('NEW_SEC_ANCHOR_FIXED_SOURCE_MISMATCH:'+ticker)
            anchor_cost=Fraction(round(Fraction(row['value_usd'],row['shares'])*100),100)
            calibration=dict(date=anchor_date,cost=anchor_cost,factor=anchor_cost/prices[anchor_date],basis='SEC_20221231_NOMINAL_ANCHOR_LAST_TRADING_DAY_EXPLICIT_CENT_ROUNDING')
        elif ticker in additional_anchor_rows:
            row=additional_anchor_rows[ticker]; anchor_date=row['quote_date']
            if row['price_source'].replace('\\','/')!=source or row['price_source_sha256']!=hashes[source]:
                raise ValueError('ADDITIONAL_SEC_ANCHOR_FIXED_SOURCE_MISMATCH:'+ticker)
            anchor_cost=Fraction(round(Fraction(row['value_usd'],row['shares'])*100),100)
            calibration=dict(date=anchor_date,cost=anchor_cost,factor=anchor_cost/prices[anchor_date],basis='SEC_NOMINAL_ANCHOR_LAST_TRADING_DAY_EXPLICIT_CENT_ROUNDING')
        registry[ticker]=dict(source=source,prices=prices,events=events,identity=identity,
            identity_references=identity_refs,calibration=calibration)
    results=[]
    for month in domain['decisions']:
        day=month['decision_cutoff']
        if day>='2023-12-01':continue
        candidates=[]; rejected=[]; allowed_exclusions={}; window_events=[]
        for ticker in month['full_members']:
            route=registry[ticker]; dates=month['training_dates']; identity=route['identity']
            exclusion=exclusion_by_key.get((ticker,day))
            if exclusion:
                allowed_exclusions[ticker]=dict(reason=exclusion['reason'],known_asof=exclusion['known_asof'],
                    source_references=['tmp/qqq_20201231_anchor_20261025/regular_way_eligibility_v1.json'])
                candidates.append(dict(ticker=ticker,**identity,status='EXCLUDED_TRAINING_RULE',blockers=[]))
                continue
            missing=[d for d in dates if d not in route['prices']]
            blockers=[]
            if missing:blockers.append('MISSING_TRAINING_CLOSE:'+','.join(missing))
            if not route['identity_references']:blockers.append('DATED_IDENTITY_REFERENCE_MISSING')
            calibration=route['calibration']
            factor=None
            if calibration is None:
                blockers.append('NOMINAL_COST_ANCHOR_MISSING:'+ticker)
            else:
                factor=calibration['factor']
                for event_date,event_factor in route['events'].items():
                    if not reviewed_coordinate_event(ticker,event_date,event_factor)['apply_nominal_scale']:continue
                    if day<event_date<=calibration['date']:factor*=event_factor
                    elif calibration['date']<event_date<=day:factor/=event_factor
            for event_date,event_factor in route['events'].items():
                if dates[0]<event_date<=day:
                    review=reviewed_coordinate_event(ticker,event_date,event_factor)
                    window_events.append(dict(ticker=ticker,date=event_date,factor=str(event_factor),**review))
                    if not review['training_allowed']:blockers.append('COMPLEX_TRAINING_COORDINATE_EVENT:'+event_date+':'+str(event_factor))
            cost=str(route['prices'][day]*factor) if factor is not None and day in route['prices'] else None
            candidates.append(dict(ticker=ticker,**identity,status='PENDING_EVIDENCE_REVIEW' if blockers else 'READY_CONDITIONAL',
                training_source=route['source'],training_close=[str(route['prices'][d]) if d in route['prices'] else None for d in dates],
                missing_training_dates=missing,decision_cost=cost,blockers=blockers,
                nominal_scale=str(factor) if factor is not None else None))
            if blockers:rejected.append(dict(ticker=ticker,reasons=blockers))
        window=dict(decision_cutoff=day,training_dates=month['training_dates'],candidates=candidates)
        admission=dict(status='PENDING_EVIDENCE_REVIEW' if rejected else 'REVIEWED_CONDITIONAL',decision_date=day,
            members=month['full_members'],source_references=list(hashes),training_exclusions=allowed_exclusions)
        compiled=None; error=None
        try:compiled=compile_monthly_training_window(window=window,source_hashes=hashes,admission=admission)
        except ValueError as exc:error=str(exc)
        results.append(dict(decision_cutoff=day,status='READY_CONDITIONAL' if compiled else 'SPECIFIC_REVIEW_REQUIRED',
            full_member_count=len(candidates),training_exclusions=list(allowed_exclusions),rejected=rejected,
            window_coordinate_events=window_events,window=window,admission=admission,compiled_search_arguments=compiled,compiler_error=error))
    return dict(status='FIXED_36_MONTH_REAL_TRAINING_PREPARATION_NO_SEARCH',source_hashes=hashes,windows=results,
        fixed_sources=[dict(ticker=ticker,source=route['source'],sha256=hashes[route['source']],**route['identity'],
                           identity_references=route['identity_references'],
                           calibration={k:str(v) for k,v in route['calibration'].items()} if route['calibration'] else None,
                           provider_coordinate_events=[dict(date=day,factor=str(factor),**reviewed_coordinate_event(ticker,day,factor)) for day,factor in sorted(route['events'].items())]) for ticker,route in registry.items()],
        ready_count=sum(r['status']=='READY_CONDITIONAL' for r in results),search_calls=0,
        limitations=['Readiness is conditional third-party training input only, not economic return validation.',
                    'Ordinary rational splits up to 20:20 are accepted as provider-adjusted training-price events; no holding action is simulated here.',
                    'EXC retains the provider spinoff-adjusted price-only signal, not exact parent-plus-child total return; execution must book the actual 1/3 CEG distribution separately.',
                    'MTCH preserves the verified 1:1 old/new price-only chain, excluding the optional cash/extra-share distribution; the unsupported 3.502 provider factor is retained but never applied.',
                    'Constant future coordinate factors cancel in ratios; nominal decision costs retain dated factors.'])


if __name__=='__main__':
    result=prepare()
    (OUT/'recent_training_windows_v1.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(months=len(result['windows']),ready=result['ready_count'],
        ready_dates=[w['decision_cutoff'] for w in result['windows'] if w['status']=='READY_CONDITIONAL'],
        unresolved_tickers=sorted({r['ticker'] for w in result['windows'] for r in w['rejected']}))))

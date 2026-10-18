"""Raw-only provider coverage audit; no network, return generation or training."""
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data/cache/research/provider_gap_batch12_capture_20260912_v1'
NY=ZoneInfo('America/New_York')


def sha(raw):return hashlib.sha256(raw).hexdigest()
def day(timestamp):return datetime.fromtimestamp(timestamp,NY).date().isoformat()


def main():
    sources={}
    def read(path,expected):
        path=Path(path).resolve();raw=path.read_bytes()
        if sha(raw)!=expected:raise ValueError('Hard source SHA mismatch')
        sources[str(path)]=expected;return json.loads(raw)
    coverage=read(FOLDER/'coverage_addendum.json','6fc0d5ee29cecb12ae70433fece84cd43e64ae90030aa92fe00f95880a3b1b22')
    index=read(FOLDER/'completed_queue_sha_event_index.json','5d9d2b55d88441045c3b3c98cfb0c33687a707da030266ff028e151b35357117')
    for document in (coverage,index):
        for path,digest in document['source_hashes'].items():
            if path in sources and sources[path]!=digest:raise ValueError('Source conflict')
            sources[path]=digest
    def verify():
        for path,digest in sources.items():
            if sha(Path(path).read_bytes())!=digest:raise ValueError('Source drift: '+path)
    verify()
    variants={};raw_audits=[]
    for ticker,records in index['provider_channels'].items():
        for record in records:
            path=record['path'];raw=Path(path).read_bytes()
            if sha(raw)!=record['sha256'] or sources.get(path)!=record['sha256']:raise ValueError('Raw capture binding differs')
            decoded=gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
            chart,=json.loads(decoded)['chart']['result'];quote,=chart['indicators']['quote']
            dates=[day(timestamp) for timestamp in chart['timestamp']]
            if dates!=sorted(set(dates)) or chart['meta']!=record['provider_meta']:
                raise ValueError('Raw dates or complete metadata differs')
            if (record['observed_rows']!=len(dates) or record['observed_start']!=dates[0] or record['observed_end']!=dates[-1]):
                raise ValueError('Observed timestamp-slot denominator differs')
            events={kind:[dict(provider_event_key=key,session=day(value['date']),provider_fields=value)
                    for key,value in sorted(chart.get('events',{}).get(kind,{}).items(),key=lambda item:int(item[0]))]
                    for kind in ('splits','dividends')}
            if record['returned_events']!=events:raise ValueError('Returned event dictionary differs')
            receipts=[ref.get('received_at_utc') or ref.get('response_saved_at_utc') for ref in record['references']]
            cutoffs=[datetime.fromisoformat(stamp.replace('Z','+00:00')).astimezone(NY).date().isoformat() for stamp in receipts if stamp]
            cutoff=min(cutoffs) if cutoffs else None
            valid={};observed={}
            for field in ('open','close'):
                if len(quote[field])!=len(dates):raise ValueError('Quote array length differs')
                observed[field]={d for d,v in zip(dates,quote[field]) if type(v) in (int,float) and math.isfinite(v) and v>0}
                valid[field]={d for d in observed[field] if cutoff is not None and d<cutoff}
            if path in variants:raise ValueError('Repeated raw variant path')
            variants[path]=dict(ticker=ticker,dates=dates,valid=valid)
            finite_both=observed['open']&observed['close']
            zero_volume=[d for d,volume in zip(dates,quote.get('volume',[])) if d in finite_both and volume==0]
            raw_audits.append(dict(ticker=ticker,path=path,raw_sha256=record['sha256'],decoded_sha256=sha(decoded),
                observed_timestamp_slots=len(dates),finite_positive_open_close_bars=len(finite_both),
                finite_positive_close_bars=len(observed['close']),completed_positive_open_close_bars=len(valid['open']&valid['close']),
                finite_bar_zero_volume_dates=zero_volume,receipt_cutoff=cutoff,receipt_independently_authenticated=False,
                no_timestamp_slot_is_asserted_to_be_a_trade=True,raw_metadata_events_dates_exact=True))
    if len(index['provider_channels'])!=107 or len(variants)!=121:raise ValueError('107 channels / 121 variants required')
    membership_path=next(path for path in sources if Path(path).name=='full_membership_coverage_20260912_v2.json')
    membership=read(membership_path,sources[membership_path]);appearances={}
    meta_variants=[value for value in variants.values() if value['ticker']=='META' and value['dates'][0]=='2022-01-03']
    reference,=meta_variants
    previous={d:reference['dates'][i-1] for i,d in enumerate(reference['dates']) if i}
    for cohort in membership['dates']:
        date=cohort['coordinate']['selection_date'];requirement=coverage['calendar_requirements'][date]
        context_path,=[path for path,digest in membership['source_hashes'].items() if digest==cohort['old_context_sha256'] and Path(path).name=='context.json']
        context=read(context_path,cohort['old_context_sha256'])
        actual=[item['timestamp'][:10] for item in context['prepared_inputs']['returns']['payload']['mapping']['index']['items']]
        if requirement['return_dates']!=actual or requirement['previous_close_by_return_date']!={d:previous[d] for d in actual}:
            raise ValueError('Original context calendar / observed META previous-session map differs')
        if len(cohort['candidates'])!=101:raise ValueError('Original proxy date denominator differs')
        for candidate in cohort['candidates']:appearances.setdefault(candidate['ticker'],[]).append(date)
    candidates=coverage['candidate_rows']
    if len(candidates)!=112 or {row['ticker'] for row in candidates}!=set(appearances):raise ValueError('Complete proxy union differs')
    totals=dict(captured=0,close_complete=0,open_close_complete=0,periods=0);checks=[]
    for candidate in candidates:
        ticker=candidate['ticker'];available={path:value for path,value in variants.items() if value['ticker']==ticker}
        if candidate['updated_capture_present']!=bool(available):raise ValueError('Captured channel flag differs')
        if [p['selection_date'] for p in candidate['periods']]!=appearances[ticker]:raise ValueError('Complete candidate period coordinate set differs')
        totals['captured']+=bool(available);complete=[];both_complete=[]
        for period in candidate['periods']:
            date=period['selection_date'];requirement=coverage['calendar_requirements'][date]
            required=set(requirement['return_dates'])|set(requirement['previous_close_by_return_date'].values())
            if len(required)!=period['required_close_count'] or len(requirement['return_dates'])!=period['original_return_count']:
                raise ValueError('Required price denominator differs')
            for key,fields in [('updated_complete_paths',('close',)),('updated_complete_open_close_paths',('open','close'))]:
                for path in period.get(key,[]):
                    if path not in available or any(required-available[path]['valid'][field] for field in fields):
                        raise ValueError('Claimed complete raw path missing finite positive required prices')
            close_paths=[path for path,v in available.items() if not required-v['valid']['close']]
            both_paths=[path for path,v in available.items() if not required-(v['valid']['close']&v['valid']['open'])]
            if bool(close_paths)!=bool(period['updated_complete_paths']) or bool(both_paths)!=bool(period['updated_complete_open_close_paths']):
                raise ValueError('Independent complete-path availability differs')
            complete.append(bool(close_paths));both_complete.append(bool(both_paths));totals['periods']+=1
            checks.append(dict(ticker=ticker,selection_date=date,required_prices=len(required),close_complete_paths=close_paths,open_close_complete_paths=both_paths))
        if candidate['updated_all_applicable_training_complete']!=all(complete):raise ValueError('Complete channel count differs')
        totals['close_complete']+=all(complete);totals['open_close_complete']+=all(both_complete)
    if totals!={'captured':107,'close_complete':104,'open_close_complete':104,'periods':1515}:
        raise ValueError('Independent whole coverage differs: '+str(totals))
    ea,=[row for row in raw_audits if row['ticker']=='EA']
    if ea['observed_timestamp_slots']!=40 or ea['finite_positive_open_close_bars']!=6 or len(ea['finite_bar_zero_volume_dates'])!=4:
        raise ValueError('EA finite-bar/placeholder boundary differs')
    sources[str(Path(__file__).resolve())]=sha(Path(__file__).read_bytes());verify()
    report=dict(schema='ndx_provider_full_queue_independent_audit_v1',source_hashes=sources,counts=totals,
        proxy_security_union=112,provider_channels=107,raw_variants=121,raw_variant_audits=raw_audits,period_checks=checks,
        current_provider_ticker_is_not_historical_identity=True,calendar_is_observed_meta_not_exchange_certificate=True,
        finite_price_coverage_is_not_trade_or_liquidity_evidence=True,corporate_action_completeness_verified=False,
        nominal_price_basis_verified=False,new_network_requests=0,returns_generated=False,training_performed=False,
        point_in_time_verified=False,promotion_allowed=False)
    output=FOLDER/'independent_full_queue_raw_audit_20260912.json'
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=sha(output.read_bytes()),sources=len(sources),counts=totals,ea=ea)))


if __name__=='__main__':main()

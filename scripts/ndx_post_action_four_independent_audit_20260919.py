"""Independent raw Decimal readback of four saved post-action quote segments."""
import argparse
import gzip
import hashlib
import html
from html.parser import HTMLParser
import json
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
INDEX=ROOT/'data/cache/research/post_action_quote_archive_probe_20260919_v2/index.json'
INDEX_SHA='877dc14a5d9aaf3baaa30e289369959828236a33c20edc9ddfc9a6c0841fae28'
FLOORS={'EXC':'2022-02-02','HON':'2026-06-29','LRCX':'2024-10-03','WDC':'2025-02-24'}
CUSIPS={'EXC':None,'HON':'438516205','LRCX':'512807306','WDC':'958102105'}
LOADED={str(Path(__file__).resolve()):archive.drift.file_sha(__file__),str(archive.SOURCE):archive.LOADED,
        str(archive.drift.SOURCE):archive.drift.file_sha(archive.drift.SOURCE)}
NY=ZoneInfo('America/New_York')


def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def day(t):return datetime.fromtimestamp(int(t),timezone.utc).astimezone(NY).date().isoformat()
def unique(pairs):
    output={}
    for k,v in pairs:
        if k in output:raise ValueError('Duplicate JSON key')
        output[k]=v
    return output
def load(raw,decimal=False):
    return json.loads(raw,object_pairs_hook=unique,parse_float=Decimal if decimal else float,
                      parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def positive(v):
    if type(v) not in (int,float,Decimal):raise ValueError('Nonboolean numeric quote required')
    number=Decimal(str(v))
    if not number.is_finite() or number<=0:raise ValueError('Finite positive quote required')
    return number


def audit_prices(raw,result,ticker):
    data=load(raw,True)['chart']['result'][0];quoted=data['indicators']['quote'][0]
    dates=[day(t) for t in data['timestamp']]
    if dates!=sorted(set(dates)) or data['meta']['symbol']!=ticker:raise ValueError('Unique source coordinate required')
    cutoff=datetime.fromisoformat(result['received_at_utc']).astimezone(NY).date().isoformat()
    expected=[d for d in dates if FLOORS[ticker]<=d<cutoff]
    rows=result['rows']
    if type(result['row_count']) is not int or result['row_count']!=len(expected) or [r['session'] for r in rows]!=expected:
        raise ValueError('Full post-floor completed provider calendar required')
    maximum=Decimal(0);position={d:i for i,d in enumerate(dates)}
    for row in rows:
        if (row['ticker']!=ticker or row['currency']!='USD' or type(row['factor']) is not int or row['factor']!=1
            or row['factor_numerator']!='1' or row['factor_denominator']!='1' or row['returned_later_split_like_events']!=[]):
            raise ValueError('Strict conditional coordinate and integer factor one required')
        i=position[row['session']]
        if type(row['provider_timestamp']) is not int or row['provider_timestamp']!=data['timestamp'][i]:raise ValueError('Timestamp differs')
        for field in ('open','close'):
            target=positive(quoted[field][i]);actual=positive(row['nominal_'+field])
            if positive(row['quote_'+field])!=actual:raise ValueError('Copied quote differs')
            error=abs(target-actual);maximum=max(maximum,error)
            if error>Decimal('1e-12'):raise ValueError('Independent raw Decimal price differs')
    return dict(ticker=ticker,calendar=expected,row_count=len(expected),cells_checked=2*len(expected),
                first_session=expected[0],last_session=expected[-1],maximum_absolute_decimal_error=str(maximum),
                incomplete_receipt_day_excluded=cutoff)


class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,value):self.parts.append(value)


def build():
    sources=dict(LOADED)
    def read(p,h):
        p=str(Path(p).resolve());raw=Path(p).read_bytes()
        if sha(raw)!=h:raise ValueError('External raw/artifact SHA differs')
        archive.merge(sources,{p:h});return raw
    index=load(read(INDEX,INDEX_SHA))
    if index['schema']!='POST_ACTION_FOUR_ARCHIVE_QUOTE_INDEX_V2' or index['completed']!=4 or [e['ticker'] for e in index['entries']]!=list(FLOORS):raise ValueError('Exact four index required')
    contract=archive.load_contract();reports=[]
    for entry in index['entries']:
        ticker=entry['ticker'];doc=load(read(entry['path'],entry['sha256']))
        if Path(entry['path'])!=INDEX.parent/(ticker+'.json') or doc['schema']!='POST_ACTION_FOUR_ARCHIVE_AUTHORITY_QUOTE_PROBE_V2' or doc['ticker']!=ticker:raise ValueError('Original artifact identity differs')
        for field in ('original_26_observations_asserted_live_unchanged','original_live_root_paths_verified','historical_full_source_closure_recovered',
                      'point_in_time_verified','price_identity_verified','promotion_allowed','returns_generated','training_performed','live_state_modified'):
            if doc[field] is not False:raise ValueError('Unsupported producer scope')
        archive.merge(sources,doc['historical_expected_source_hashes'])
        checked=archive.verify_expected_sources(doc['historical_expected_source_hashes'],contract)
        if canonical(checked)!=canonical(doc['archive_resolution']) or checked['archive_resolutions'] or checked['historical_gap_observations'] or doc['actual_root_price_csv_dependency_count']!=0:
            raise ValueError('Actual source subset must have zero root price dependencies')
        result=doc['result'];origin=doc['original_interval_plan_row'];evidence=doc['raw_decoding_evidence']
        raw=read(evidence['raw_path'],evidence['raw_sha256']);decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
        if sha(decoded)!=evidence['decoded_sha256'] or sha(decoded)!=result['decoded_sha256'] or sha(decoded)!=origin['decoded_sha256']:raise ValueError('Decoded bytes differ')
        body=load(decoded)['chart']['result'][0];events=body.get('events',{})
        if canonical(events)!=canonical(result['returned_events']):raise ValueError('Complete raw events differ')
        if any(day(event['date'])>FLOORS[ticker] for event in events.get('splits',{}).values()):raise ValueError('Later event forbids factor one')
        interval=result['post_action_interval']
        if interval['first_post_action_session']!=FLOORS[ticker] or interval['post_action_cusip']!=CUSIPS[ticker]:raise ValueError('Official boundary coordinate differs')
        official=origin['primary_boundary_evidence'];raw_official=read(official['path'],official['sha256'])
        if raw_official[:2]==b'\x1f\x8b':raw_official=gzip.decompress(raw_official)
        parser=Text();parser.feed(raw_official.decode('utf8',errors='replace'));text=' '.join(html.unescape(' '.join(parser.parts)).split())
        if any(' '.join(fragment.split()) not in text for fragment in official['exact_text_fragments']):raise ValueError('Official boundary fragment missing')
        if any(result[k] is not False for k in ('point_in_time_verified','promotion_allowed','provider_price_identity_bound','complete_corporate_actions_verified',
                'absence_of_later_events_proves_no_actions','quote_basis_independently_authenticated','returns_generated','adjclose_used','dividends_applied')):raise ValueError('Result false claim upgraded')
        audited=audit_prices(decoded,result,ticker)
        if audited['row_count']!=entry['row_count'] or audited['calendar']!=interval['calendar']:raise ValueError('Saved index/interval denominator differs')
        reports.append(dict(audited,official_boundary_evidence=official,returned_event_sha256=sha(canonical(events).encode())))
    checked=archive.verify_expected_sources(sources,contract)
    return dict(schema='POST_ACTION_FOUR_INDEPENDENT_RAW_DECIMAL_AUDIT_V1',index_ref=dict(path=str(INDEX),sha256=INDEX_SHA),rows=reports,
                total_rows=sum(r['row_count'] for r in reports),cells_checked=sum(r['cells_checked'] for r in reports),
                maximum_absolute_decimal_error=str(max(Decimal(r['maximum_absolute_decimal_error']) for r in reports)),
                source_hashes=sources,archive_resolution=checked,actual_root_price_csv_dependencies=0,archive_authority_denominator=111,
                producer_or_old_oracle_called=False,price_identity_verified=False,complete_actions_verified=False,point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();value=build()
    archive.verify_expected_sources(value['source_hashes'],archive.load_contract())
    with Path(args.output).open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
    archive.verify_expected_sources(value['source_hashes'],archive.load_contract())
    print(json.dumps(dict(path=str(Path(args.output).resolve()),sha256=archive.drift.file_sha(args.output),rows=value['total_rows'],decimal_error=value['maximum_absolute_decimal_error'])))

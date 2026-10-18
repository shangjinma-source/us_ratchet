"""Gate every returned provider split against specific externally bound facts."""
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import re
from backtest import ndx_nominal_quote_reconstruction_research as nominal

SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
FACT_PATH=SOURCE.parents[1]/'data/cache/research/standard_split_official_evidence_20260912_v1/specific_split_fact_readback.json'
FACT_SHA='f421d8b95c6542139b016a853c3ab9e7f69d76daaff79e4592918fce8e8e4d55'
BLOCKED=frozenset({'EXC','CMCSA','HON','ILMN','AZN','SIRI'})


def decode_bound_raw(*,raw_path,raw_sha256,content_encoding):
    path=Path(raw_path).resolve();raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=raw_sha256:raise ValueError('Provider raw bytes SHA differs before decoding')
    if content_encoding=='gzip':
        if raw[:2]!=b'\x1f\x8b':raise ValueError('Declared gzip does not match raw bytes')
        decoded=gzip.decompress(raw)
    elif content_encoding in (None,'identity'):
        if raw[:2]==b'\x1f\x8b':raise ValueError('Gzip bytes require explicit gzip encoding')
        decoded=raw
    else:raise ValueError('Unsupported raw content encoding')
    return decoded,dict(raw_path=str(path),raw_sha256=raw_sha256,raw_bytes=len(raw),
        content_encoding=content_encoding,decoded_sha256=hashlib.sha256(decoded).hexdigest(),decoded_bytes=len(decoded))


def load_specific_facts():
    raw=FACT_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=FACT_SHA:raise ValueError('Hard-bound split fact report differs')
    report=json.loads(raw,object_pairs_hook=nominal._unique_pairs)
    if (report['schema']!='NINE_SPECIFIC_EQUITY_SPLIT_EVENTS_EVIDENCED_RESEARCH_ONLY' or
        report['specific_event_count']!=9 or len(report['specific_events'])!=9 or
        report['promotion_allowed'] is not False or report['point_in_time_verified'] is not False):
        raise ValueError('Original specific-event research facts required')
    blocked={row['ticker'] for row in report['simple_split_interface_blocklist'] if row['simple_split_interface_allowed'] is False}
    if blocked!=BLOCKED:raise ValueError('Exact complex-action blocklist required')
    sources=dict(report['source_hashes'])
    for path,sha in {str(FACT_PATH):FACT_SHA,str(SOURCE):LOADED,str(nominal.SOURCE):nominal.LOADED_SHA}.items():
        if path in sources and sources[path]!=sha:raise ValueError('Conflicting guard source SHA')
        sources[path]=sha
    nominal.verify(sources)
    return report,sources


def match_returned_events(*,decoded,ticker,specific_events,blocked_tickers):
    """Pure event matching; its caller must bind the source of specific_events."""
    if ticker in blocked_tickers:raise ValueError('Complex corporate action cannot enter simple-share-split reconstruction')
    document=json.loads(decoded,object_pairs_hook=nominal._unique_pairs);chart=document['chart']
    if chart.get('error') is not None or type(chart.get('result')) is not list or len(chart['result'])!=1:
        raise ValueError('Unique successful provider chart required')
    data=chart['result'][0]
    if data['meta']['symbol']!=ticker:raise ValueError('Provider response ticker differs')
    events=data.get('events',{})
    if type(events) is not dict or type(events.get('splits',{})) is not dict:raise ValueError('Explicit event mapping required')
    supported={}
    for fact in specific_events:
        key=(fact['ticker'],nominal._day(fact['first_adjusted_trading_date']))
        if key in supported or fact['specific_simple_share_split_event_supported'] is not True:
            raise ValueError('Unique positively supported event facts required')
        numerator,denominator=nominal._number(fact['new_shares']),nominal._number(fact['old_shares'])
        supported[key]=Fraction(str(numerator))/Fraction(str(denominator))
    matches=[];seen=set()
    for key,event in events.get('splits',{}).items():
        timestamp=event['date'];day=nominal._timestamp(timestamp).astimezone(nominal.NEW_YORK).date().isoformat()
        if key!=str(timestamp) or day in seen:raise ValueError('Duplicate or inconsistent provider split event date')
        seen.add(day)
        ratio=Fraction(str(nominal._number(event['numerator'])))/Fraction(str(nominal._number(event['denominator'])))
        text=event['splitRatio']
        if type(text) is not str or re.fullmatch(r'[0-9]+(?:\.[0-9]+)?:[0-9]+(?:\.[0-9]+)?',text) is None:
            raise ValueError('Explicit exact split ratio text required')
        first,second=text.split(':')
        if Fraction(second)<=0 or Fraction(first)/Fraction(second)!=ratio:raise ValueError('Split numerical ratio conflicts with text')
        if supported.get((ticker,day))!=ratio:raise ValueError('Returned provider event lacks exact supported share-split fact')
        matches.append(dict(ticker=ticker,first_adjusted_trading_date=day,provider_event_timestamp=timestamp,
            numerator=str(ratio.numerator),denominator=str(ratio.denominator),specific_event_matched=True))
    return matches


def reconstruct_guarded_nominal_quote(*,raw_path,raw_sha256,content_encoding,ticker,calendar,request,received_at_utc,quote_field_basis):
    if quote_field_basis!=nominal.BASIS:raise ValueError('Independent explicit split-only quote basis required')
    report,sources=load_specific_facts()
    decoded,raw_evidence=decode_bound_raw(raw_path=raw_path,raw_sha256=raw_sha256,content_encoding=content_encoding)
    path=raw_evidence['raw_path']
    if path in sources and sources[path]!=raw_sha256:raise ValueError('Conflicting provider raw source')
    sources[path]=raw_sha256
    matches=match_returned_events(decoded=decoded,ticker=ticker,specific_events=report['specific_events'],blocked_tickers=BLOCKED)
    result=nominal.reconstruct_nominal_quote_ticker(raw=decoded,ticker=ticker,calendar=calendar,request=request,
        received_at_utc=received_at_utc,quote_field_basis=quote_field_basis)
    nominal.verify(sources)
    return dict(schema='ndx_simple_split_quote_guard_research_v1',reconstruction=result,source_hashes=sources,
        raw_decoding_evidence=raw_evidence,returned_event_count=len(matches),matched_specific_events=matches,
        all_returned_events_individually_supported=True,no_returned_events_observed=not matches,
        absence_of_returned_events_proves_no_corporate_actions=False,
        complete_corporate_action_history_verified=False,quote_basis_independently_authenticated=False,
        price_identity_verified=False,point_in_time_verified=False,promotion_allowed=False,
        scope='SPECIFIC_RETURNED_SHARE_SPLITS_ONLY_NOT_GLOBAL_CORPORATE_ACTION_NORMALIZATION')

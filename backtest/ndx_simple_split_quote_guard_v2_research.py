"""Manifest-bound quote reconstruction using the explicit 25-event registry."""
from datetime import datetime
import hashlib,json
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from backtest import ndx_nominal_quote_reconstruction_research as nominal
from backtest import ndx_simple_split_quote_guard_research as first_guard
from backtest import ndx_specific_split_registry_v2_research as registry
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
 (Path(__file__).resolve(),Path(first_guard.__file__).resolve(),Path(registry.__file__).resolve(),nominal.SOURCE)}

def load_capture(*,manifest_path,manifest_sha256,capture_name,sources):
    manifest_path=Path(manifest_path).resolve()
    registry.merge_source(sources,manifest_path,manifest_sha256);nominal.verify({str(manifest_path):manifest_sha256})
    report=json.loads(manifest_path.read_bytes(),object_pairs_hook=nominal._unique_pairs)
    arrays=[report[key] for key in ('captures','probes') if key in report]
    if len(arrays)!=1 or type(arrays[0]) is not list:raise ValueError('Unique original capture array required')
    rows=[x for x in arrays[0] if x.get('name')==capture_name]
    if len(rows)!=1:raise ValueError('Unique named original capture required')
    capture=rows[0]
    if capture.get('http_status')!=200:raise ValueError('Successful original provider capture required')
    for p,h in report.get('source_hashes',{}).items():registry.merge_source(sources,p,h)
    path=capture.get('raw_path',capture.get('response_path'));digest=capture.get('raw_sha256',capture.get('response_sha256'))
    if path is None or digest is None:raise ValueError('Original raw file binding required')
    registry.merge_source(sources,path,digest);nominal.verify(sources)
    raw=Path(path).read_bytes()
    count=capture.get('raw_bytes',capture.get('response_bytes'))
    if type(count) is not int or count!=len(raw):raise ValueError('Raw capture byte denominator differs')
    encoding=capture.get('response_headers',{}).get('Content-Encoding')
    inferred_encoding='response_headers' not in capture
    if inferred_encoding:encoding='gzip' if raw[:2]==b'\x1f\x8b' else 'identity'
    decoded,evidence=first_guard.decode_bound_raw(raw_path=path,raw_sha256=digest,content_encoding=encoding)
    if 'decoded_sha256' in capture and capture['decoded_sha256']!=evidence['decoded_sha256']:raise ValueError('Original decoded bytes differ')
    evidence['encoding_inferred_from_bytes_missing_original_header']=inferred_encoding
    if 'request' in capture:request=dict(capture['request'])
    else:request=dict(method=capture.get('request_method'),url=capture.get('request_url'),credentials_sent=capture.get('credentials_sent'))
    if request.get('url') is None or capture.get('received_at_utc') is None:raise ValueError('Original exact request and receipt required; saved time is not receipt')
    return decoded,capture,request,evidence

def validate_known_event_denominator(*,ticker,matches,events,request):
    """A known covered event cannot disappear merely by being omitted from provider response."""
    query=parse_qs(urlparse(request['url']).query,keep_blank_values=True)
    if any(len(query.get(k,[]))!=1 or not query[k][0].isdigit() for k in ('period1','period2')):raise ValueError('Unique request interval required')
    start,end=(nominal._timestamp(int(query[k][0])).astimezone(nominal.NEW_YORK).date().isoformat() for k in ('period1','period2'))
    expected={x['first_adjusted_trading_date'] for x in events if x['ticker']==ticker and start<=x['first_adjusted_trading_date']<=end}
    observed={x['first_adjusted_trading_date'] for x in matches}
    if expected!=observed:raise ValueError('Known in-request split event missing or extra: '+ticker)
    return sorted(expected)

def reconstruct_registry_guarded_nominal_quote(*,provider_manifest_path,provider_manifest_sha256,capture_name,ticker,calendar,quote_field_basis):
    if quote_field_basis!=nominal.BASIS:raise ValueError('Explicit split-adjusted quote basis required; adjclose unsupported')
    nominal.verify(LOADED)
    evidence_registry=registry.load_registry();sources=dict(evidence_registry['source_hashes'])
    for p,h in LOADED.items():registry.merge_source(sources,p,h)
    # A share-count fact is never an authorization to assign a changed CUSIP to earlier shares.
    if ticker in registry.TRANSITIONS:raise ValueError('Explicit historical identity transition is required; this simple-split guard cannot grant it')
    if ticker in registry.BLOCKED:raise ValueError('Complex corporate action is outside simple-split scope')
    decoded,capture,request,raw_evidence=load_capture(manifest_path=provider_manifest_path,manifest_sha256=provider_manifest_sha256,
      capture_name=capture_name,sources=sources)
    received=datetime.fromisoformat(capture['received_at_utc'])
    if received.tzinfo is None or received.utcoffset().total_seconds()!=0:raise ValueError('Exact UTC receipt required')
    if any(nominal._day(day)>=received.astimezone(nominal.NEW_YORK).date().isoformat() for day in calendar):
        raise ValueError('Reception-day bar is not certified finalized; only earlier sessions allowed')
    eligible=[x for x in evidence_registry['events'] if x['simple_split_guard_eligible']]
    matches=first_guard.match_returned_events(decoded=decoded,ticker=ticker,specific_events=eligible,blocked_tickers=registry.BLOCKED|registry.TRANSITIONS)
    expected=validate_known_event_denominator(ticker=ticker,matches=matches,events=eligible,request=request)
    result=nominal.reconstruct_nominal_quote_ticker(raw=decoded,ticker=ticker,calendar=calendar,request=request,
      received_at_utc=capture['received_at_utc'],quote_field_basis=quote_field_basis)
    nominal.verify(sources)
    return dict(schema='ndx_simple_split_quote_guard_research_v2',reconstruction=result,source_hashes=sources,
      original_capture_reference=dict(manifest_path=str(Path(provider_manifest_path).resolve()),manifest_sha256=provider_manifest_sha256,capture_name=capture_name),
      raw_decoding_evidence=raw_evidence,returned_event_count=len(matches),matched_specific_events=matches,known_in_request_event_dates=expected,
      registry_event_count=25,registry_guard_eligible_event_count=23,all_returned_events_individually_supported=True,
      known_in_request_events_all_present=True,no_returned_events_observed=not matches,
      absence_of_returned_events_proves_no_corporate_actions=False,complete_corporate_action_history_verified=False,
      quote_basis_independently_authenticated=False,price_identity_verified=False,point_in_time_verified=False,promotion_allowed=False,
      scope='SPECIFIC_STANDARD_SHARE_SPLITS_ONLY_WITH_IDENTITY_TRANSITIONS_AND_COMPLEX_ACTIONS_BLOCKED')

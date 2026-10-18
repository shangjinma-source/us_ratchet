"""Current 22/79 receipt-native conditional quotes, without synthetic manifests."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from backtest import ndx_simple_split_exact_gap_research as gap

nominal=gap.nominal
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research'
ANCHORS={
 'current_22_price_capture_20260919_v1':('completion_index_22.json','7a41e3f47ecb4ea9fc6757a9e0393993be99ffeaceab8d2b21ea38c83797890d','099f4a363917e43a1b5a625e097365f1b093254ca0829cc36919b2593bb99334',22),
 'current79_new_asof_capture_20260919_v1':('completion_index_79.json','280fd0aecb9c02afe0cfa99fadc3b08a483eff283602f9c341e990d171b1f310','f429cc4fbdf8156c4c1f1aec7cdded86da664b74a6d3874be6f80477cf50cbba',79)}
PARTITION_REQUIRED={'HONA':'WHEN_ISSUED_VERSUS_REGULAR_SECURITY','SNDK':'WHEN_ISSUED_VERSUS_REGULAR_SECURITY','FER':'PRE_US_VERSUS_US_LISTING'}
SEGMENTS=BASE/'current_listing_segments_20260919_v1/listing_segment_facts.json'
SEGMENTS_SHA='b1c814d801eaf7ec00d3cf13a1093fbfb66ac96a4149fee75bdeb0cda07b194d'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(gap.__file__).resolve())}


def read(path,sha,sources):
    path=Path(path).resolve();gap.merge(sources,{str(path):sha})
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Receipt-native external SHA differs')
    return json.loads(raw,object_pairs_hook=nominal._unique_pairs)


def load_capture(*,ticker,raw_path,raw_sha256,sources):
    requested=Path(raw_path)
    if not requested.is_absolute():raise ValueError('Absolute raw address required')
    requested=requested.resolve();matches=[]
    for directory,(indexname,indexsha,plansha,count) in ANCHORS.items():
        folder=BASE/directory
        index=read(folder/indexname,indexsha,sources);plan=read(folder/'plan.json',plansha,sources)
        gap.merge(sources,plan['source_hashes'])
        if index['plan_sha256']!=plansha or index['output_directory']!=str(folder) or plan['output_directory']!=str(folder):raise ValueError('Original plan coordinate differs')
        entries=index['entries'];tickers=[e['ticker'] for e in entries]
        if len(tickers)!=count or len(set(tickers))!=count or tickers!=plan['tickers']:raise ValueError('Complete original queue required')
        for entry in entries:
            if ticker==entry['ticker']:
                if requested!=folder/(ticker+'.response.bin'):raise ValueError('Requested raw is not original ticker address')
                if entry['receipt_path']!=str(folder/(ticker+'.receipt.json')) or entry['decoded_path']!=str(folder/(ticker+'.decoded.json')):raise ValueError('Original receipt/decoded address differs')
                receipt=read(entry['receipt_path'],entry['receipt_sha256'],sources)
                started=read(folder/(ticker+'.started.json'),receipt['started_sha256'],sources)
                parsed=read(entry['decoded_path'],entry['decoded_sha256'],sources)
                if receipt.get('http_status')!=200 or receipt.get('error_type') is not None:raise ValueError('Successful complete response required')
                if any(receipt.get(k)!=v for k,v in started.items()):raise ValueError('Started/receipt content differs')
                if (started['ticker']!=ticker or started['plan_sha256']!=plansha or started['attempt_count']!=1 or
                    receipt['raw_path']!=str(requested) or receipt['raw_sha256']!=raw_sha256 or
                    parsed['ticker']!=ticker or parsed['receipt_sha256']!=entry['receipt_sha256']):raise ValueError('Original raw/receipt/attempt binding differs')
                gap.merge(sources,{str(requested):raw_sha256})
                decoded,evidence=gap.addressed.previous.first_guard.decode_bound_raw(raw_path=requested,raw_sha256=raw_sha256,content_encoding=receipt['response_headers'].get('Content-Encoding'))
                if receipt['raw_bytes']!=evidence['raw_bytes'] or parsed.get('decoded_sha256')!=evidence['decoded_sha256']:raise ValueError('Raw byte/decoded denominator differs')
                request=dict(method=started['request_method'],url=started['request_url'],credentials_sent=started['credentials_sent'])
                query=parse_qs(urlparse(request['url']).query)
                p2=int(query['period2'][0]);start=datetime.fromisoformat(started['started_at_utc']);received=datetime.fromisoformat(receipt['received_at_utc'])
                if (start.tzinfo is None or start.utcoffset().total_seconds()!=0 or received.tzinfo is None or received.utcoffset().total_seconds()!=0 or
                    int(start.timestamp())!=p2 or started['period2_utc_epoch']!=p2 or received<start or
                    receipt['completed_training_excludes_dates_on_or_after']!=received.astimezone(nominal.NEW_YORK).date().isoformat()):raise ValueError('Original UTC request/receipt coordinate differs')
                matches.append((decoded,receipt,request,evidence))
    if len(matches)!=1:raise ValueError('Unique exact original capture required')
    return matches[0]


def reconstruct_current_receipt_quote(*,ticker,raw_path,raw_sha256,calendar,quote_field_basis):
    if ticker in PARTITION_REQUIRED:raise ValueError('PARTITION_REQUIRED: '+PARTITION_REQUIRED[ticker])
    if ticker in gap.original.BLOCKED|gap.original.TRANSITIONS:raise ValueError('Complex action or identity transition blocked')
    if quote_field_basis!=nominal.BASIS:raise ValueError('Explicit conditional split-adjusted quote basis required')
    registry=gap.load_registry();contract=gap.drift.load_contract()
    expected=dict(registry['historical_expected_source_hashes']);gap.merge(expected,LOADED)
    try:
        segments=read(SEGMENTS,SEGMENTS_SHA,expected);gap.merge(expected,segments['source_hashes'])
        gap.partition(expected,contract,require_all=True)
        decoded,receipt,request,evidence=load_capture(ticker=ticker,raw_path=raw_path,raw_sha256=raw_sha256,sources=expected)
        excluded=receipt['completed_training_excludes_dates_on_or_after']
        if any(nominal._day(d)>=excluded for d in calendar):raise ValueError('Receipt-day quote is unfinalized')
        eligible=[e for e in registry['events'] if e['simple_split_guard_eligible']]
        matches=gap.addressed.previous.first_guard.match_returned_events(decoded=decoded,ticker=ticker,specific_events=eligible,blocked_tickers=gap.original.BLOCKED|gap.original.TRANSITIONS|set(PARTITION_REQUIRED))
        known=gap.addressed.previous.validate_known_event_denominator(ticker=ticker,matches=matches,events=eligible,request=request)
        result=nominal.reconstruct_nominal_quote_ticker(raw=decoded,ticker=ticker,calendar=calendar,request=request,received_at_utc=receipt['received_at_utc'],quote_field_basis=quote_field_basis)
        meta=json.loads(decoded,object_pairs_hook=nominal._unique_pairs)['chart']['result'][0]['meta']
        output=dict(schema='CURRENT_RECEIPT_CONDITIONAL_QUOTE_GUARD_V1',reconstruction=result,original_request=request,original_received_at_utc=receipt['received_at_utc'],raw_decoding_evidence=evidence,provider_metadata=meta,receipt_day_excluded=excluded,matched_specific_events=matches,known_in_request_event_dates=known,original_capture_names_synthesized=False,conditional_quote_basis=quote_field_basis,quote_basis_independently_authenticated=False,price_identity_verified=False,complete_corporate_action_history_verified=False,absence_of_returned_events_proves_no_corporate_actions=False,returns_generated=False,training_performed=False,partition_required_channels=dict(PARTITION_REQUIRED))
        output['listing_partition_evidence']=dict(path=str(SEGMENTS),sha256=SEGMENTS_SHA,whole_channel_block_is_interface_limitation_not_no_valid_interval=True)
        return gap.attach_partition(output,expected,gap.partition(expected,contract,require_all=True))
    finally:gap.partition(expected,contract)

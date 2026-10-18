"""External index and all returned events from immutable capture evidence; no requests."""
from collections import defaultdict
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research'
FINAL=BASE/'provider_gap_batch12_capture_20260912_v1/coverage_addendum.json'
FINAL_SHA='6fc0d5ee29cecb12ae70433fece84cd43e64ae90030aa92fe00f95880a3b1b22'
OLD=BASE/'dynamic_frozen_v2/full_proxy_provider_capture_inventory_20260912.json'
OLD_SHA='e23c0c5c61171c07eb7fa48a494b90b8c1ed8915763babf1da6f17899e9a9262'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if sha(FINAL)!=FINAL_SHA or sha(OLD)!=OLD_SHA:
        raise ValueError('Final external SHA differs')
    final=json.loads(FINAL.read_bytes());old=json.loads(OLD.read_bytes())
    sources=dict(final['source_hashes']);sources[str(FINAL)]=FINAL_SHA
    for path,digest in sources.items():
        if sha(path)!=digest:raise ValueError('Source closure differs '+path)
    pool={row['ticker'] for row in final['candidate_rows']}
    raw_refs={path:dict(ticker=capture['provider_request_ticker'],raw_sha256=capture['sha256'],references=capture['manifest_references']) for path,capture in old['raw_captures'].items()}
    index=[];all_attempts=[];http_counts=defaultdict(int)
    for ordinal in range(1,13):
        if ordinal==1:
            directory=BASE/'provider_gap_first8_capture_20260912_v1';coverage=BASE/'dynamic_frozen_v2/first8_provider_coverage_addendum_20260912.json'
        elif ordinal==2:
            directory=BASE/'provider_gap_second8_capture_20260912_v1';coverage=BASE/'dynamic_frozen_v2/second8_provider_coverage_addendum_20260912.json'
        else:
            directory=BASE/('provider_gap_batch%02d_capture_20260912_v1'%ordinal);coverage=directory/'coverage_addendum.json'
        manifest_path=directory/'manifest.json';manifest=json.loads(manifest_path.read_bytes())
        for path in (manifest_path,coverage):
            if str(path) not in sources or sha(path)!=sources[str(path)]:raise ValueError('Batch not bound by final closure')
        coverage_report=json.loads(coverage.read_bytes())
        index.append(dict(batch=ordinal,manifest_path=str(manifest_path),manifest_sha256=sha(manifest_path),coverage_path=str(coverage),coverage_sha256=sha(coverage),
                          execution_digest_evidence='STDOUT_VISIBLE' if ordinal!=5 else 'STDOUT_TRUNCATED_RECOMPUTED_AND_FINAL_CLOSURE_VERIFIED',
                          tickers=manifest['explicit_request_tickers'],counts=coverage_report['counts']))
        for probe in manifest['probes']:
            all_attempts.append(probe['ticker']);http_counts[str(probe.get('http_status'))]+=1
            if probe.get('http_status')!=200 or probe.get('parse_status')!='RAW_QUOTE_CHANNEL_PARSED_NOT_IDENTITY_ADJUDICATION':continue
            path=probe['response_path']
            if path in raw_refs:raise ValueError('Duplicate new raw path')
            raw_refs[path]=dict(ticker=probe['ticker'],raw_sha256=probe['response_sha256'],references=[dict(manifest_path=str(manifest_path),request_url=probe['request']['url'],received_at_utc=probe.get('received_at_utc'),response_saved_at_utc=probe.get('response_saved_at_utc'))])
    if len(all_attempts)!=len(set(all_attempts)) or len(all_attempts)!=90 or final['next_capture_plan']['tickers']:
        raise ValueError('Queue is not unique and exhausted')
    channels=defaultdict(list)
    for path,ref in raw_refs.items():
        if ref['ticker'] not in pool:continue
        if sha(path)!=ref['raw_sha256']:raise ValueError('Raw digest differs')
        raw=Path(path).read_bytes();decoded=gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
        chart,=json.loads(decoded)['chart']['result']
        if chart['meta']['symbol']!=ref['ticker']:raise ValueError('Channel differs')
        days=[datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for t in chart['timestamp']]
        events={}
        for kind in ('splits','dividends'):
            events[kind]=[dict(provider_event_key=key,session=datetime.fromtimestamp(value['date'],ZoneInfo('America/New_York')).date().isoformat(),provider_fields=value)
                          for key,value in sorted(chart.get('events',{}).get(kind,{}).items(),key=lambda kv:int(kv[0]))]
        channels[ref['ticker']].append(dict(path=path,sha256=ref['raw_sha256'],references=ref['references'],provider_meta=chart['meta'],
            observed_start=days[0],observed_end=days[-1],observed_rows=len(days),returned_events=events,
            current_meta_is_not_historical_security_identity=True))
    if len(channels)!=107:raise ValueError('Captured proxy channel denominator differs')
    risk=dict(incomplete_captured_tickers=[row['ticker'] for row in final['candidate_rows'] if row['updated_capture_present'] and not row['updated_all_applicable_training_complete']],
              failed_requests=final['failures_preserved'],ea='Current provider response only 40 sessions from 2026-07-17. Historical 2022-2024 training calendar absent; identity continuity unresolved.',
              ceg_gehc='When-issued versus regular-way dates and preexistence gaps remain; no zero fill.',
              meta='Current META provider channel requires dated FB to META projection for historical sessions.',
              wbd='Merger and predecessor share classes require adjudication, not simple rename.',
              all_channels='Returned split/dividend events are provider observations, not independently certified complete corporate-action histories or nominal price basis.')
    sources[str(Path(__file__).resolve())]=sha(__file__)
    report=dict(schema='COMPLETE_12_BATCH_CAPTURE_EXTERNAL_SHA_AND_PROVIDER_EVENT_INDEX',source_hashes=sources,batches=index,
                unique_new_requests=90,http_status_counts=dict(http_counts),proxy_channel_count=107,full_training_covered_count=104,
                proxy_security_denominator=112,proxy_issuer_denominator=111,provider_channels=dict(sorted(channels.items())),identity_risks=risk,
                event_history_completed_adjudication=False,point_in_time_verified=False,promotion_allowed=False,no_training=True,no_new_requests=True)
    path=BASE/'provider_gap_batch12_capture_20260912_v1/completed_queue_sha_event_index.json'
    with path.open('xb') as stream:stream.write((json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())
    print(json.dumps(dict(path=str(path),sha256=sha(path),unique_requests=90,http_counts=dict(http_counts),channels=len(channels),raw_variants=sum(len(v) for v in channels.values()),incomplete=risk['incomplete_captured_tickers'])))


if __name__=='__main__':main()

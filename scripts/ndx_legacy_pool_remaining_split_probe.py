"""Nine remaining old-pool channels, one capture each; event inventory only."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import gzip
import hashlib
import json
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_identity_source_probe import capture
from scripts.ndx_joint_weight_verify import _restore_input

TICKERS = ('ADBE','ADI','BKR','DDOG','ENPH','QCOM','SNPS','TEAM','TXN')


def main():
    directory = ROOT / 'data/cache/research/legacy_pool_remaining_split_probe_20260912_v1'
    directory.mkdir(exist_ok=True)
    if (directory / 'report.json').exists(): raise FileExistsError('Completed inventory exists')
    sources = {}
    def bind(path, expected=None):
        path=Path(path).resolve();raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if expected is not None and sha!=expected: raise ValueError('Bound source differs')
        sources[str(path)]=sha
        return raw
    for path in (__file__,ROOT/'scripts/ndx_identity_source_probe.py',ROOT/'scripts/ndx_joint_weight_verify.py'):bind(path)
    old=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/root_return_semantics_review_20260912.json'
    review=json.loads(bind(old,'a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b'))
    for path,sha in review['source_hashes'].items():bind(path,sha)
    contexts=[];union=set()
    for location in review['actual_window_error_locations']:
        path,=[Path(p) for p,h in sources.items() if h==location['context_sha256'] and Path(p).name=='context.json']
        context=json.loads(path.read_bytes());inputs={k:_restore_input(v) for k,v in context['prepared_inputs'].items()}
        union.update(inputs['universe'].ticker);contexts.append((location,inputs))
    assert len(union)==15 and set(TICKERS)<=union
    probes=[]
    for ticker in TICKERS:
        raw_path=directory/(ticker+'.response.bin');meta_path=directory/(ticker+'.metadata.json')
        if meta_path.exists():
            metadata=json.loads(bind(meta_path));raw=bind(raw_path,metadata['response_sha256'])
        else:
            if raw_path.exists():raise ValueError('Unrecorded raw file requires explicit recovery')
            now=datetime.now(timezone.utc)
            request=dict(name='yahoo_'+ticker.lower()+'_remaining_old_pool',method='GET',direct=False,
                url=f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1=1640995200&period2={int(now.timestamp())}&interval=1d&events=div%2Csplits')
            metadata,raw=capture(request)
            if raw is None:raw=b''
            metadata.update(response_path=str(raw_path),response_sha256=hashlib.sha256(raw).hexdigest(),response_bytes=len(raw))
            with raw_path.open('xb') as handle:handle.write(raw)
            with meta_path.open('x',encoding='utf8') as handle:json.dump(metadata,handle,indent=2,sort_keys=True)
            bind(raw_path,metadata['response_sha256']);bind(meta_path)
        probes.append(metadata)
        print(ticker,metadata['http_status'],metadata['response_bytes'],flush=True)
    rows=[];new_errors=[]
    for ticker,probe in zip(TICKERS,probes):
        if probe['http_status']!=200:
            rows.append(dict(ticker=ticker,status='RAW_ACCESS_FAILURE',events_unknown=True));continue
        raw=Path(probe['response_path']).read_bytes()
        if raw[:2]==b'\x1f\x8b':raw=gzip.decompress(raw)
        d,=json.loads(raw)['chart']['result'];assert d['meta']['symbol']==ticker and d['meta']['currency']=='USD'
        def day(stamp):return datetime.fromtimestamp(stamp,ZoneInfo('America/New_York')).date().isoformat()
        days=[day(t) for t in d['timestamp']];assert days==sorted(set(days))
        received=day(datetime.fromisoformat(probe['received_at_utc']).timestamp())
        unfinalized=[x for x in days if x>=received]
        events=[]
        root=ROOT/'data/cache'/(ticker+'.csv');bind(root);legacy=pd.read_csv(root).set_index('Date').Close
        for event in d.get('events',{}).get('splits',{}).values():
            session=day(event['date']);i=days.index(session)
            affected=[]
            for loc,inputs in contexts:
                dates=[x.date().isoformat() for x in inputs['returns'].index];c=inputs['contract']
                if session not in dates:continue
                fit=[];forward=[]
                for ordinal,start in enumerate(range(c['fit_days'],len(dates)-c['window_days']+1,c['step_days'])):
                    if session in dates[start-c['fit_days']:start]:fit.append(ordinal)
                    if session in dates[start:start+c['window_days']]:forward.append(ordinal)
                affected.append(dict(coordinate=loc['coordinate'],fit_windows=fit,forward_windows=forward))
            fact=dict(ticker=ticker,session=session,new_shares=event['numerator'],old_shares=event['denominator'],context_locations=affected)
            if affected and i>0 and session<received:
                previous=days[i-1];quote=d['indicators']['quote'][0]['close']
                fact.update(previous_session=previous,provider_price_return=quote[i]/quote[i-1]-1,
                    legacy_return=float(legacy.loc[session]/legacy.loc[previous]-1))
                if fact['legacy_return']==0 and abs(fact['provider_price_return'])>1e-12:new_errors.append(fact)
            events.append(fact)
        rows.append(dict(ticker=ticker,status='RETURNED_PROVIDER_EVENT_INVENTORY',first_session=days[0],last_session=days[-1],
            session_count=len(days),completed_session_count=sum(x<received for x in days),unfinalized_sessions=unfinalized,
            unfinalized_training_use_allowed=False,observed_split_events=events,
            provider_no_event_is_not_official_completeness=True))
    for path,sha in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha,path
    result=dict(schema='ndx_legacy_pool_remaining_split_probe_v1',source_hashes=sources,probes=probes,rows=rows,
        exact_old_pool_union=sorted(union),old_pool_union_count=15,new_requested_tickers=list(TICKERS),
        previous_dedicated_six_tickers=['AMAT','AVGO','CDNS','FTNT','GOOG','GOOGL'],
        dedicated_old_pool_provider_channel_coverage=15,new_confirmed_legacy_zero_counterexamples=new_errors,
        existing_TXN_capture_not_reused_reason='Sealed prior channel begins 2023-03-31 and does not cover 2022 training history.',
        scope='RETURNED_PROVIDER_SPLIT_EVENTS_ONLY_NOT_EXHAUSTIVE_CORPORATE_ACTION_OR_PRICE_ERROR_CERTIFICATION',
        official_no_split_intervals_certified=False,all_price_errors_corrected=False,cache_modified=False,
        training_performed=False,point_in_time_verified=False,promotion_allowed=False)
    path=directory/'report.json'
    with path.open('x',encoding='utf8') as handle:json.dump(result,handle,indent=2,sort_keys=True);handle.write('\n')
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),new_error_count=len(new_errors))),flush=True)


if __name__=='__main__':main()

"""Read-only raw comparison; no returns, no reconstructed prices, no HTTP."""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_current79_new_asof_capture_20260919 as capture
PLAN_SHA='f429cc4fbdf8156c4c1f1aec7cdded86da664b74a6d3874be6f80477cf50cbba'
LOADED=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
NY=ZoneInfo('America/New_York')


def read_raw(path,sha,sources):
    if str(path) in sources and sources[str(path)]!=sha:raise ValueError('Source collision')
    sources[str(path)]=sha
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Raw SHA differs')
    body=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
    if body['chart'].get('error') or len(body['chart'].get('result') or [])!=1:raise ValueError('Chart unavailable')
    result=body['chart']['result'][0];quotes=result['indicators']['quote'][0]
    dates=[datetime.fromtimestamp(t,timezone.utc).astimezone(NY).date().isoformat() for t in result['timestamp']]
    if dates!=sorted(set(dates)):raise ValueError('Nonunique/nonascending dates')
    if any(len(quotes[k])!=len(dates) for k in ('open','high','low','close')):raise ValueError('Incomplete field lengths')
    return result,{day:{k:quotes[k][i] for k in ('open','high','low','close')} for i,day in enumerate(dates)}


def positive(value):return type(value) in (float,int) and math.isfinite(value) and value>0


def build(index_path,index_sha):
    plan=capture.load_plan(capture.OUTPUT/'plan.json',PLAN_SHA)
    index=capture.previous.read_bound(index_path,index_sha)
    entries=capture.previous.checked_entries(index,capture.OUTPUT,PLAN_SHA)
    if [e['ticker'] for e in entries]!=plan['tickers']:raise ValueError('Complete 79 required')
    sources=dict(plan['source_hashes']);sources.update({str(Path(__file__).resolve()):LOADED,str(Path(index_path).resolve()):index_sha,str(capture.OUTPUT/'plan.json'):PLAN_SHA})
    authority=capture.previous.read_bound(capture.AUTHORITY,capture.AUTHORITY_SHA)
    old={r['ticker']:r for r in authority['rows']};rows=[];all_completed=[]
    for e in entries:
        ticker=e['ticker'];receipt=capture.previous.read_bound(e['receipt_path'],e['receipt_sha256'])
        sources[e['receipt_path']]=e['receipt_sha256'];sources[e['decoded_path']]=e['decoded_sha256']
        sources[str(capture.OUTPUT/(ticker+'.started.json'))]=receipt['started_sha256']
        row=dict(ticker=ticker,http_status=receipt.get('http_status'),error_type=receipt.get('error_type'),received_at_utc=receipt['received_at_utc'],old_missing_receipt_preserved=ticker in ('GOOGL','FTNT'))
        if receipt.get('http_status')!=200:
            row.update(complete=False,latest_completed=None);rows.append(row);all_completed.append(set());continue
        data,bars=read_raw(receipt['raw_path'],receipt['raw_sha256'],sources)
        excluded=datetime.fromisoformat(receipt['received_at_utc']).astimezone(NY).date().isoformat()
        if excluded!=receipt['completed_training_excludes_dates_on_or_after']:raise ValueError('Receipt day mismatch')
        completed={d for d,q in bars.items() if d<excluded and positive(q['open']) and positive(q['close'])}
        comparisons=[]
        for prior in old[ticker]['raw_variants']:
            _,before=read_raw(prior['path'],prior['sha256'],sources)
            common=sorted(set(before)&set(bars));changes=[];counts={k:0 for k in ('open','high','low','close')}
            old_excluded=prior['receipt_day_excluded'];old_final_changes=0
            for d in common:
                changed={k:{'old':before[d][k],'new':bars[d][k]} for k in counts if before[d][k]!=bars[d][k]}
                if changed:
                    changes.append(dict(date=d,fields=changed))
                    for k in changed:counts[k]+=1
                    if old_excluded is not None and d<old_excluded:old_final_changes+=1
            comparisons.append(dict(old_path=prior['path'],old_sha256=prior['sha256'],common_dates=len(common),changed_dates=len(changes),changed_field_counts=counts,old_receipt_day_excluded=old_excluded,changed_pre_old_receipt_dates=old_final_changes,changes=changes,old_missing_receipt_not_invented=old_excluded is None))
        row.update(complete=True,raw_path=receipt['raw_path'],raw_sha256=receipt['raw_sha256'],completed_count=len(completed),latest_completed=max(completed) if completed else None,receipt_day_excluded=excluded,excluded_observed_dates=[d for d in bars if d>=excluded],provider_meta=data['meta'],returned_events=data.get('events',{}),comparisons=comparisons,quote_basis_authenticated=False,historical_identity_verified=False)
        rows.append(row);all_completed.append(completed)
    new22=capture.previous.read_bound(capture.BASE/list(capture.ANCHORS)[1],list(capture.ANCHORS.values())[1])
    for row in new22['rows']:
        _,bars=read_raw(row['raw_path'],row['raw_sha256'],sources)
        excluded=datetime.fromisoformat(row['received_at_utc']).astimezone(NY).date().isoformat()
        all_completed.append({d for d,q in bars.items() if d<excluded and positive(q['open']) and positive(q['close'])})
    if len(all_completed)!=101:raise ValueError('101 union differs')
    common=set.intersection(*all_completed)
    report=dict(schema='CURRENT79_NEW_ASOF_RAW_READBACK_V1',rows=rows,channel_count=79,successful_http_count=sum(r['http_status']==200 for r in rows),current101_common_completed_latest=max(common) if common else None,current101_common_completed_date_count=len(common),source_hashes=sources,old_raw_modified=False,returns_generated=False,training_performed=False,point_in_time_verified=False,promotion_allowed=False,identity_admission=False,comparison_scope='PROVIDER_OHLC_REVISION_OBSERVATION_NOT_CORRECTION_OR_PRICE_BASIS_AUTHENTICATION')
    capture.verify(sources)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--index',required=True);p.add_argument('--index-sha',required=True);a=p.parse_args()
    report=build(a.index,a.index_sha);path=capture.OUTPUT/'raw_coverage_comparison.json';sha=capture.previous.save(path,report);capture.verify(report['source_hashes'])
    print(json.dumps(dict(path=str(path),sha256=sha,successful=report['successful_http_count'],common_completed=report['current101_common_completed_latest'])))

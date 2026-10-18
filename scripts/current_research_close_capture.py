"""Explicit, bounded saved-close capture; default dry-run and no registration."""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request
from zoneinfo import ZoneInfo
import argparse
import gzip
import io
import json
import os
import re

from scripts.ndx_current_raw_capture_20261014 import (digest,save,safe_directory,default_open,MAX_BYTES,FLAGS)
from data.current_research_saved_quote import read_saved_quote,_json

ROOT=Path(__file__).resolve().parents[1]
NY=ZoneInfo('America/New_York')


def utc_now():return datetime.now(timezone.utc)


def require(ok,reason):
    if not ok:raise ValueError(reason)


def _path(root,value):
    require(isinstance(value,str) and value.strip(),'PATH_REQUIRED')
    path=Path(value)
    require(not path.is_absolute() and not path.drive and '..' not in path.parts,'RELATIVE_ROOT_PATH_REQUIRED')
    absolute=root/path;safe_directory(absolute)
    require(absolute.resolve().is_relative_to(root),'PATH_OUTSIDE_ROOT')
    return absolute


def _clock(clock):
    now=clock();require(isinstance(now,datetime) and now.tzinfo is not None and now.utcoffset().total_seconds()==0,'REAL_AWARE_UTC_CLOCK_REQUIRED')
    return now


def _decimal_json(value):
    """Preserve event Decimal numbers as JSON numeric tokens, not strings/floats."""
    if isinstance(value,Decimal):
        require(value.is_finite(),'NONFINITE_EVENT_NUMBER');return str(value)
    if isinstance(value,dict):return '{'+','.join(json.dumps(k)+':'+_decimal_json(v) for k,v in value.items())+'}'
    if isinstance(value,list):return '['+','.join(_decimal_json(v) for v in value)+']'
    return json.dumps(value,allow_nan=False)


def _write_raw(path,raw):
    safe_directory(path)
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'RAW_READBACK_MISMATCH')
    return digest(raw)


def default_fetch(url, *, timeout, max_bytes):
    headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'gzip'}
    try:response=default_open(Request(url,headers=headers),timeout=timeout)
    except HTTPError as error:response=error
    with response:
        raw=response.read(max_bytes+1)
        return dict(raw=raw,http_status=response.status,final_url=response.url,
                    response_headers={key:response.headers.get(key) for key in ('Date','Content-Type','Content-Encoding','Content-Length','ETag','Last-Modified')})


def capture_saved_close(manifest_path,manifest_sha256,*,root=ROOT,capture=False,fetch=default_fetch,clock=utc_now):
    root=Path(root).resolve();path=_path(root,manifest_path);raw=path.read_bytes()
    require(digest(raw)==manifest_sha256,'MANIFEST_HASH_MISMATCH');manifest=_json(raw)
    require(manifest.get('schema')=='SAVED_CLOSE_CAPTURE_MANIFEST_V1','MANIFEST_SCHEMA_INVALID')
    session=manifest['session'];history=manifest['history_start_date']
    require(date.fromisoformat(session).isoformat()==session and date.fromisoformat(history).isoformat()==history and history<=session,'INVALID_CAPTURE_DATES')
    pins=manifest['calendar_source_hashes'];calendar_path=manifest['calendar_path']
    require(isinstance(pins,dict) and calendar_path in pins,'CALENDAR_PIN_REQUIRED')
    for source,expected in pins.items():require(digest(_path(root,source).read_bytes())==expected,'CALENDAR_SOURCE_CHANGED')
    calendar=_json(_path(root,calendar_path).read_bytes())
    require(calendar.get('schema')=='SCHEDULED_REGULAR_SESSIONS_V1','CALENDAR_SCHEMA_INVALID')
    require(calendar.get('source_hashes') and all(pins.get(k)==v for k,v in calendar['source_hashes'].items()),'CALENDAR_CLOSURE_UNBOUND')
    days=calendar['calendar'];sessions=calendar['sessions'];byday={s['date']:s for s in sessions}
    require(days==sorted(set(days)) and len(byday)==len(sessions) and set(days)==set(byday) and session in byday,'SESSION_CALENDAR_MISMATCH')
    schedule=byday[session];opening=datetime.fromisoformat(schedule['open_at']);closing=datetime.fromisoformat(schedule['close_at'])
    require(schedule['timezone']=='America/New_York' and all(t.tzinfo is not None and t.date().isoformat()==session
            and t.astimezone(NY).date().isoformat()==session and t.utcoffset()==t.astimezone(NY).utcoffset() for t in (opening,closing)) and opening<closing,'INVALID_SESSION_TIMES')
    securities=manifest['securities']
    require(isinstance(securities,list) and 1<=len(securities)<=5,'EXPLICIT_SMALL_SCOPE_REQUIRED')
    seen=set();sids=set()
    for security in securities:
        ticker=security['ticker'];kind=security['security_type'];sid=security.get('security_id')
        require(isinstance(ticker,str) and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,14}',ticker) and ticker not in seen,'INVALID_OR_DUPLICATE_TICKER');seen.add(ticker)
        require(kind in ('EQUITY','ETF'),'INVALID_SECURITY_TYPE')
        require((kind=='ETF' and sid is None) or (isinstance(sid,str) and sid.strip() and sid not in sids),'SECURITY_ID_REQUIRED_OR_DUPLICATE')
        if sid is not None:sids.add(sid)
    output=_path(root,manifest['output_directory']);require(output!=root,'OUTPUT_CANNOT_BE_ROOT')
    now=_clock(clock)
    prepared=dict(schema='SAVED_CLOSE_CAPTURE_PRECHECK_V1',manifest_sha256=manifest_sha256,session=session,
                  session_close_at=closing.isoformat(),checked_at_utc=now.isoformat(),securities=securities,
                  ready_after_close=now>=closing,output_directory=manifest['output_directory'],http_calls=0,
                  registration_performed=False,account_writes=False)
    if not capture:return prepared
    require(now>=closing,'SESSION_NOT_CLOSED_ZERO_HTTP')
    require(not output.exists(),'CAPTURE_OUTPUT_EXISTS_NO_RETRY')
    output.mkdir(parents=True,exist_ok=False)
    save(output/'manifest.json',manifest)
    codepins={str(Path(__file__).resolve().relative_to(ROOT).as_posix()):digest(Path(__file__).read_bytes()),
              'scripts/ndx_current_raw_capture_20261014.py':digest((ROOT/'scripts/ndx_current_raw_capture_20261014.py').read_bytes()),
              'data/current_research_saved_quote.py':digest((ROOT/'data/current_research_saved_quote.py').read_bytes())}
    save(output/'started.json',dict(prepared,source_hashes=dict(pins),code_hashes=codepins,maximum_http_calls=len(securities),retry_allowed=False))
    entries=[]
    for security in securities:
        ticker=security['ticker'];started=_clock(clock);require(started>=closing,'CLOCK_BEFORE_CLOSE_ZERO_FURTHER_HTTP')
        period1=int(datetime.combine(date.fromisoformat(history),datetime.min.time(),tzinfo=timezone.utc).timestamp())
        url=f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker,safe="")}?period1={period1}&period2={int(started.timestamp())}&interval=1d&events=div,splits,capitalGains'
        intent=dict(ticker=ticker,security_type=security['security_type'],security_id=security.get('security_id'),target_date=session,started_at_utc=started.isoformat(),request_url=url,attempt_count=1,credentials_sent=False)
        intent_sha=save(output/(ticker+'.started.json'),intent)
        receipt=dict(intent,started_sha256=intent_sha,status='TRANSPORT_FAILED',body_truncated=False);body=None;received=None
        try:
            fetched=fetch(url,timeout=15,max_bytes=MAX_BYTES)
            received=_clock(clock)
            body=fetched['raw'];require(isinstance(body,bytes),'RAW_BYTES_REQUIRED')
            receipt.update(http_status=fetched['http_status'],final_url=fetched['final_url'],response_headers=fetched.get('response_headers',{}))
            receipt['status']='BODY_LIMIT_FAILED' if len(body)>MAX_BYTES else 'HTTP_FAILED' if fetched['http_status']!=200 or fetched['final_url']!=url else 'RAW_CAPTURED'
        except Exception as error:
            if received is None:received=_clock(clock)
            receipt.update(status='TRANSPORT_FAILED',error_type=type(error).__name__)
        if isinstance(body,bytes):
            body=body[:MAX_BYTES+1];raw_sha=_write_raw(output/(ticker+'.response.bin'),body)
            receipt.update(raw_sha256=raw_sha,raw_bytes=len(body),body_truncated=len(body)>MAX_BYTES)
        receipt['received_at_utc']=received.isoformat()
        if received<started or received<closing:receipt['status']='CLOCK_FAILED'
        receipt.update(FLAGS);receipt_sha=save(output/(ticker+'.receipt.json'),receipt)
        observation=dict(ticker=ticker,receipt_sha256=receipt_sha,status=receipt['status'],**FLAGS)
        if receipt['status']=='RAW_CAPTURED':
            try:
                if body[:2]==b'\x1f\x8b':
                    with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:decoded=stream.read(MAX_BYTES+1)
                else:decoded=body
                require(len(decoded)<=MAX_BYTES,'DECOMPRESSED_BODY_TOO_LARGE')
                chart=_json(decoded)['chart'];require(chart.get('error') is None and len(chart.get('result') or [])==1,'INVALID_PROVIDER_RESULT')
                observation.update(decoded_sha256=digest(decoded),raw_returned_events=chart['result'][0].get('events',{}),status='DECODED_PENDING_READER_VALIDATION')
            except Exception as error:observation.update(status='DECODE_FAILED',error_type=type(error).__name__)
        observation_sha=_write_raw(output/(ticker+'.decoded.json'),(_decimal_json(observation)+'\n').encode('utf-8'))
        entry=dict(security,ticker=ticker,raw_sha256=receipt.get('raw_sha256'),receipt_sha256=receipt_sha,decoded_sha256=observation_sha,status=observation['status'])
        if observation['status']=='DECODED_PENDING_READER_VALIDATION':
            try:
                verified=read_saved_quote(root=root,ticker=ticker,expected_security_type=security['security_type'],entry=entry,
                    relative_directory=output.relative_to(root).as_posix(),decision_date=session,decision_session_close_at=closing.isoformat())
                entry.update(status='SAVED_EXACT_SESSION_READER_VALIDATED_NOT_ADMITTED',quote_observation=verified)
            except Exception as error:entry.update(status='READER_VALIDATION_FAILED',reason=str(error))
        entries.append(entry)
    index=dict(schema='SAVED_CLOSE_CAPTURE_INDEX_V1',session=session,manifest_sha256=manifest_sha256,entries=entries,
               source_hashes=pins,code_hashes=codepins,http_calls=len(securities),maximum_http_calls=len(securities),
               registration_performed=False,account_writes=False,admission_status='NOT_REVIEWED_NOT_REGISTERED',completed_at_utc=_clock(clock).isoformat())
    save(output/'completion_index.json',index)
    return index


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--manifest-sha256',required=True);parser.add_argument('--capture',action='store_true')
    args=parser.parse_args();result=capture_saved_close(args.manifest,args.manifest_sha256,capture=args.capture)
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))

if __name__=='__main__':main()

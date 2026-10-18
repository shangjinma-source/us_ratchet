"""Transport-only evidence for unresolved equity identity. Never training admission."""
from datetime import date,datetime,timezone
from pathlib import Path
from urllib.parse import quote
import gzip,io,re
from scripts.current_research_close_capture import (
    NY,MAX_BYTES,FLAGS,_path,_clock,_write_raw,_decimal_json,_json,
    require,digest,save,default_fetch,utc_now)
from data.current_research_saved_quote import read_saved_quote


def capture_unresolved_close(security,*,root,output_directory,session,history_start_date,
                             session_close_at,fetch=default_fetch,clock=utc_now,capture=False):
    """Caller pins exchange calendar. Default preflight has no HTTP or output IO."""
    require(type(security)is dict and set(security)<= {'ticker','security_id','security_type','identity_status'},'UNRESOLVED_SECURITY_FIELDS')
    ticker=security.get('ticker')
    require(type(ticker)is str and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,14}',ticker)
        and security.get('security_id') is None and security.get('security_type')=='EQUITY'
        and security.get('identity_status','UNRESOLVED')=='UNRESOLVED','UNRESOLVED_EQUITY_REQUIRED')
    require(type(session)is str and date.fromisoformat(session).isoformat()==session and type(history_start_date)is str
        and date.fromisoformat(history_start_date).isoformat()==history_start_date<=session,'INVALID_CAPTURE_DATES')
    close=datetime.fromisoformat(session_close_at)
    require(close.tzinfo is not None and close.date().isoformat()==session and close.astimezone(NY).date().isoformat()==session
        and close.utcoffset()==close.astimezone(NY).utcoffset(),'INVALID_NEW_YORK_CLOSE_TIME')
    root=Path(root).resolve();output=_path(root,output_directory);require(output!=root,'OUTPUT_CANNOT_BE_ROOT');now=_clock(clock)
    entry=dict(ticker=ticker,security_id=None,security_type='EQUITY',identity_status='UNRESOLVED',
        training_admitted=False,registration_performed=False,account_writes=False,http_calls=0,
        ready_after_close=now>=close,status='PREFLIGHT_ONLY',**FLAGS)
    if not capture:return entry
    require(now>=close,'SESSION_NOT_CLOSED_ZERO_HTTP');require(not output.exists(),'CAPTURE_OUTPUT_EXISTS_NO_RETRY')
    # Recheck before any directory creation or request.
    started=_clock(clock);require(started>=close and started>=now,'CLOCK_BEFORE_CLOSE_ZERO_HTTP')
    output.mkdir(parents=True,exist_ok=False)
    period1=int(datetime.combine(date.fromisoformat(history_start_date),datetime.min.time(),tzinfo=timezone.utc).timestamp())
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker,safe="")}?period1={period1}&period2={int(started.timestamp())}&interval=1d&events=div,splits,capitalGains'
    intent=dict(ticker=ticker,security_id=None,security_type='EQUITY',identity_status='UNRESOLVED',target_date=session,
        started_at_utc=started.isoformat(),request_url=url,attempt_count=1,credentials_sent=False)
    intent_sha=save(output/(ticker+'.started.json'),intent)
    receipt=dict(intent,started_sha256=intent_sha,status='TRANSPORT_FAILED',body_truncated=False);body=None
    try:
        response=fetch(url,timeout=15,max_bytes=MAX_BYTES);received=_clock(clock);body=response['raw']
        require(type(body)is bytes,'RAW_BYTES_REQUIRED')
        receipt.update(http_status=response['http_status'],final_url=response['final_url'],response_headers=response.get('response_headers',{}))
        receipt['status']='BODY_LIMIT_FAILED' if len(body)>MAX_BYTES else 'HTTP_FAILED' if response['http_status']!=200 or response['final_url']!=url else 'RAW_CAPTURED'
    except Exception as error:
        received=_clock(clock);receipt.update(status='TRANSPORT_FAILED',error_type=type(error).__name__)
    if type(body)is bytes:
        body=body[:MAX_BYTES+1];receipt.update(raw_sha256=_write_raw(output/(ticker+'.response.bin'),body),raw_bytes=len(body),body_truncated=len(body)>MAX_BYTES)
    receipt['received_at_utc']=received.isoformat()
    if received<started or received<close:receipt['status']='CLOCK_FAILED'
    receipt.update(FLAGS);receipt_sha=save(output/(ticker+'.receipt.json'),receipt)
    observation=dict(ticker=ticker,receipt_sha256=receipt_sha,status=receipt['status'],**FLAGS)
    if receipt['status']=='RAW_CAPTURED':
        try:
            if body[:2]==b'\x1f\x8b':
                with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:decoded=stream.read(MAX_BYTES+1)
            else:decoded=body
            require(len(decoded)<=MAX_BYTES,'DECOMPRESSED_BODY_TOO_LARGE')
            chart=_json(decoded)['chart'];require(chart.get('error') is None and len(chart.get('result') or [])==1,'INVALID_PROVIDER_RESULT')
            observation.update(decoded_sha256=digest(decoded),raw_returned_events=chart['result'][0].get('events',{}),status='DECODED_NOT_IDENTITY_ADMITTED')
        except Exception as error:observation.update(status='DECODE_FAILED',error_type=type(error).__name__)
    observation_sha=_write_raw(output/(ticker+'.decoded.json'),(_decimal_json(observation)+'\n').encode())
    entry.update(raw_sha256=receipt.get('raw_sha256'),receipt_sha256=receipt_sha,decoded_sha256=observation_sha,http_calls=1,
        status='TRANSPORT_SAVED_UNRESOLVED_NOT_ADMITTED' if receipt['status']=='RAW_CAPTURED' else receipt['status'],quote_validation='NOT_VALIDATED')
    if observation['status']=='DECODED_NOT_IDENTITY_ADMITTED':
        try:
            read_saved_quote(root=root,ticker=ticker,expected_security_type='EQUITY',entry=entry,relative_directory=output.relative_to(root).as_posix(),decision_date=session,decision_session_close_at=session_close_at)
            entry['quote_validation']='EXACT_SESSION_OHLC_VALIDATED_IDENTITY_UNRESOLVED'
        except Exception as error:entry.update(quote_validation='READER_VALIDATION_FAILED',reason=str(error))
    save(output/'completion_index.json',entry)
    return entry

"""V2 action capture: short reservation locks, concurrent durable writes.

Four workers, original 120-second window, budgets, receipts and final checks.
No production wiring; consumers must replay raw evidence exactly as before.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import re
from threading import Lock
from core.strategy_account_ledger import canonical
from data.current_quantity_v2_paper_action_sources import fetch_daily_actions, daily_url
from scripts.current_research_official_alert_capture import fetch_official_feed, URL


def require(ok,reason):
    if not ok:raise ValueError(reason)


def stamp(value):
    value=datetime.fromisoformat(value) if isinstance(value,str) else value
    require(isinstance(value,datetime) and value.tzinfo is not None and value.utcoffset() is not None,'AWARE_CLOCK_REQUIRED')
    return value.astimezone(timezone.utc)


class ConcurrentCaptureFilesV2:
    """Reserve bounded unique bytes under lock; durable IO belongs to one owner.

    Failed reservations remain failed for this attempt. Waiters receive the same
    failure; they never retry writes or claim partial files as complete evidence.
    """
    def __init__(self,write,maximum_bytes=128*1024*1024):
        require(type(maximum_bytes)is int and maximum_bytes>0,'ACTION_BUDGET_INVALID')
        self.write=write;self.maximum_bytes=maximum_bytes
        self.files={};self.pins={};self.pending={};self.total=0;self.lock=Lock()

    def put(self,raw,suffix):
        require(type(raw)is bytes and suffix in {'.raw','.json','.xml'},'ACTION_STORAGE_INPUT')
        digest=sha256(raw).hexdigest();name=digest+suffix;path='strategy-action-capture/'+name
        with self.lock:
            entry=self.pending.get(path)
            owner=entry is None
            if owner:
                require(self.total+len(raw)<=self.maximum_bytes,'ACTION_PACKAGE_TOO_LARGE')
                future=Future();self.pending[path]=(raw,future);self.total+=len(raw)
            else:
                expected,future=entry
                require(raw==expected,'ACTION_DIGEST_COLLISION')
        if not owner:
            return future.result()
        try:
            # No package mutex is held during open/write/flush/fsync.
            self.write(name,raw)
            with self.lock:
                self.files[path]=raw;self.pins[path]=digest
            future.set_result(path)
            return path
        except BaseException as error:
            future.set_exception(error)
            raise


class StrategyAccountActionCaptureV2:
    def __init__(self,*,fetch=fetch_daily_actions,rss_fetch=fetch_official_feed,clock=None,max_workers=4):
        require(type(max_workers)is int and max_workers==4,'BOUNDED_CONCURRENCY_REQUIRED')
        self.fetch=fetch;self.rss_fetch=rss_fetch;self.clock=clock or (lambda:datetime.now(timezone.utc));self.workers=max_workers

    def capture(self,request,output_directory):
        request=deepcopy(request)
        require(type(request)is dict and set(request)=={'account_id','state_revision','window_start','observed_floor','securities','current_target_quantities'},'ACTION_REQUEST_FIELDS')
        require(all(type(request[k])is str and bool(request[k]) for k in ('account_id','state_revision')),'ACTION_ACCOUNT_BINDING')
        began=stamp(self.clock());start=stamp(request['window_start']);floor=stamp(request['observed_floor'])
        require(start<=floor<=began,'ACTION_REQUEST_TIME')
        securities=request['securities'];targets=request['current_target_quantities']
        require(type(securities)is dict and 0<len(securities)<=200 and type(targets)is dict,'ACTION_DOMAIN_REQUIRED')
        require(all(type(sid)is str and bool(sid) and type(row)is dict and type(row.get('ticker'))is str
                    and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,14}',row['ticker']) for sid,row in securities.items()),'ACTION_IDENTITY_REQUIRED')
        require(len({r['ticker'] for r in securities.values()})==len(securities),'DUPLICATE_TICKER_MAPPING')
        require(all(type(q)is int and q>=0 and (q==0 or sid in securities) for sid,q in targets.items()),'ACTION_TARGET_DOMAIN')
        directory=Path(output_directory)
        require(not any(p.is_symlink() for p in [directory,*directory.parents]),'ACTION_DIRECTORY_SYMLINK')
        directory.mkdir(parents=True,exist_ok=False)
        def write(name,raw):
            with (directory/name).open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        write('started.json',canonical(dict(request=request,started_at=began.isoformat(),automatic_retry=False)))
        storage=ConcurrentCaptureFilesV2(write)
        files=storage.files;pins=storage.pins;put=storage.put
        def in_window(at):require(began<=at and (at-began).total_seconds()<120,'ACTION_CAPTURE_WINDOW_EXPIRED')
        requested_from=start-timedelta(days=7)
        def one(sid):
            ticker=securities[sid]['ticker'];before=stamp(self.clock());in_window(before)
            response=self.fetch(ticker,requested_from,before);received=stamp(self.clock())
            raw=response['body'];require(type(raw)is bytes and 0<len(raw)<=4*1024*1024,'ACTION_RAW_BYTES_INVALID')
            rawpath=put(raw,'.raw');url=daily_url(ticker,requested_from,before)
            receipt=dict(security_id=sid,ticker=ticker,raw_path=rawpath,raw_sha256=sha256(raw).hexdigest(),
                http_status=response['status'],body_truncated=False,transport_error=None,
                started_at=before.isoformat(),requested_from=requested_from.isoformat(),requested_through=before.isoformat(),
                received_at=received.isoformat(),events_requested=['dividends','splits'],interval='1d',url=url,
                response_url=response.get('url',url),request_period1=int(requested_from.timestamp()),request_period2=int(before.timestamp())+1)
            path=put(canonical(receipt),'.json')
            require(response['status']==200 and response.get('url',url)==url,'ACTION_RESPONSE_INVALID')
            require(received>=before,'SERVER_CLOCK_ROLLBACK');in_window(received)
            return path,received
        try:
            receipts={};times=[];failures={}
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                pending={executor.submit(one,sid):sid for sid in sorted(securities)}
                for future in as_completed(pending):
                    sid=pending[future]
                    try:path,at=future.result();receipts[sid]=path;times.append(at)
                    except Exception as error:
                        reason=str(error);failures[sid]=reason if isinstance(error,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,99}',reason) else 'ACTION_TRANSPORT_FAILED'
            if failures:
                write('failures.json',canonical(failures));raise ValueError('INCOMPLETE_ACTION_DOMAIN')
            require(set(receipts)==set(securities),'INCOMPLETE_ACTION_DOMAIN')
            before=stamp(self.clock());in_window(before);require(before>=max(times),'SERVER_CLOCK_ROLLBACK')
            response=self.rss_fetch();received=stamp(self.clock());raw=response['body']
            require(type(raw)is bytes and 0<len(raw)<=2*1024*1024,'RSS_RAW_BYTES_INVALID')
            rsspath=put(raw,'.xml')
            rssreceipt=put(canonical(dict(url=URL,response_url=response.get('url',URL),http_status=response['status'],started_at=before.isoformat(),
                received_at=received.isoformat(),raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw))),'.json')
            require(response['status']==200 and response.get('url',URL)==URL,'RSS_RESPONSE_INVALID')
            require(received>=before,'SERVER_CLOCK_ROLLBACK');in_window(received)
            result=dict(files=files,source_hashes=pins,documents=dict(action_receipts=receipts,rss_raw=rsspath,rss_receipt=rssreceipt))
            finished=stamp(self.clock());in_window(finished);require(finished>=received,'SERVER_CLOCK_ROLLBACK')
            write('complete.json',canonical(dict(status='CAPTURED_NOT_REVIEWED',request_sha256=sha256(canonical(request)).hexdigest(),
                source_hashes=pins,documents=result['documents'],finished_at=finished.isoformat(),automatic_retry=False)))
            return deepcopy(result)
        except Exception as error:
            reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,99}',str(error)) else 'ACTION_CAPTURE_FAILED'
            write('failed.json',canonical(dict(status='BLOCKED',reason=reason,finished_at=stamp(self.clock()).isoformat(),automatic_retry=False)))
            raise

"""Bounded current-mark capture; no unit approval, target search or account writes."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import replay, canonical
from data.current_research_intraday_execution import fetch_intraday_chart
from data.strategy_account_mark_reference import decode_current_mark as decode_intraday_reference
from data.strategy_account_quote_clock import wait_for_vendor_clock


def require(ok,reason):
    if not ok:raise ValueError(reason)


class StrategyAccountMarketCapture:
    def __init__(self,*,identity_resolver,fetch=fetch_intraday_chart,clock=None,max_workers=4,max_mark_age=120):
        require(type(max_mark_age)is int and max_mark_age in (120,900),'UNSUPPORTED_MARK_AGE_POLICY')
        self.max_mark_age=max_mark_age
        require(type(max_workers)is int and 1<=max_workers<=8,'BOUNDED_CONCURRENCY_REQUIRED')
        self.identity=identity_resolver;self.fetch=fetch;self.clock=clock or (lambda:datetime.now(timezone.utc));self.workers=max_workers

    def _now(self):
        at=self.clock();require(isinstance(at,datetime) and at.tzinfo is not None and at.utcoffset() is not None,'AWARE_SERVER_CLOCK_REQUIRED')
        return at

    def capture(self,*,state,candidate_metadata,output_directory):
        require(replay(state['account_id'],[e['payload'] for e in state['events']])==state,'ACCOUNT_REPLAY_MISMATCH')
        require(type(candidate_metadata)is dict and len(candidate_metadata)<=200,'BOUNDED_CANDIDATE_DOMAIN_REQUIRED')
        tickers={sid:row['ticker'] for sid,row in candidate_metadata.items()}
        needed=set(tickers)|{s for s,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
        require(0<len(needed)<=250,'TOTAL_SECURITY_DOMAIN_TOO_LARGE')
        for event in state['events']:
            identity=event['payload'].get('identity_evidence')
            if identity and identity['security_id'] in needed:
                sid=identity['security_id']
                require(sid not in tickers or tickers[sid]==identity['ticker'],'RECORDED_TICKER_CONFLICT')
                tickers[sid]=identity['ticker']
        require(set(tickers)==needed,'HELD_OR_PENDING_IDENTITY_MISSING')
        require(len(set(tickers.values()))==len(tickers),'DUPLICATE_TICKER_MAPPING')
        directory=Path(output_directory)
        require(not any(p.is_symlink() for p in [directory,*directory.parents]),'CAPTURE_SYMLINK_REFUSED')
        directory.mkdir(parents=True,exist_ok=False)  # Failed/partial attempts never automatically retried.
        def put(name,value,raw=False):
            data=value if raw else canonical(value)
            with (directory/name).open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            return sha256(data).hexdigest()
        started=self._now();put('started.json',dict(account_id=state['account_id'],account_revision=state['revision'],started_at=started.isoformat(),securities=tickers,automatic_retry=False))
        try:
            identities={};source_files={};source_pins={}
            for sid,ticker in sorted(tickers.items()):
                identity=self.identity(ticker)
                require(identity['security_id']==sid and identity['ticker']==ticker,'IDENTITY_MAPPING_CHANGED')
                for path,h in identity['source_hashes'].items():
                    require(path not in source_pins or source_pins[path]==h,'IDENTITY_SOURCE_CONFLICT')
                    raw=self.identity._read(path,h)
                    require(sha256(raw).hexdigest()==h,'IDENTITY_SOURCE_CHANGED')
                    source_files[path]=raw;source_pins[path]=h
                identities[sid]=deepcopy(identity)
            require(sum(len(raw) for raw in source_files.values())<=64*1024*1024,'IDENTITY_PACKAGE_TOO_LARGE')
            # Shared identity bytes archived once; logical references remain in index.
            for h,raw in {sha256(raw).hexdigest():raw for raw in source_files.values()}.items():put(h+'.identity',raw,True)
            put('identities.json',dict(identities=identities,source_hashes=source_pins,blobs={p:h+'.identity' for p,h in source_pins.items()}))
            def one(sid):
                before=self._now();require(before>=started,'SERVER_CLOCK_ROLLBACK')
                raw=self.fetch(tickers[sid]);captured=self._now()
                require(type(raw)is bytes and 0<len(raw)<=4*1024*1024,'RAW_QUOTE_BYTES_REQUIRED')
                token=sha256(sid.encode()).hexdigest();rawpath=token+'.raw';receiptpath=token+'.receipt.json'
                h=put(rawpath,raw,True)
                receipt=dict(security_id=sid,ticker=tickers[sid],started_at=before.isoformat(),captured_at=captured.isoformat(),raw_path=rawpath,raw_sha256=h)
                require(captured>=before,'SERVER_CLOCK_ROLLBACK')
                try:
                    checked=wait_for_vendor_clock(raw,captured_at=captured,clock=self._now)
                except Exception:
                    put(receiptpath,receipt)
                    raise
                receipt['checked_at']=checked.isoformat()
                put(receiptpath,receipt)
                decoded=decode_intraday_reference(raw,ticker=tickers[sid],captured_at=captured,now=checked,maximum_age_seconds=self.max_mark_age)
                require(datetime.fromisoformat(decoded['last_at'])<=checked,'LAST_QUOTE_AFTER_CHECK')
                return sid,raw,receipt,receiptpath,captured
            results={};failures={}
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                futures={executor.submit(one,sid):sid for sid in sorted(needed)}
                for future in as_completed(futures):
                    sid=futures[future]
                    try:results[sid]=future.result()
                    except Exception as error:
                        reason=str(error);failures[sid]=reason if isinstance(error,ValueError) and reason.replace('_','').isalnum() and len(reason)<=100 else 'QUOTE_CAPTURE_FAILED'
            if failures:
                put('failures.json',failures);raise ValueError('INCOMPLETE_MARK_DOMAIN')
            require(set(results)==needed,'INCOMPLETE_MARK_DOMAIN')
            final=self._now();require(final>=started,'SERVER_CLOCK_ROLLBACK');session=final.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            marks={};sessions=set();pins={};files={};references={}
            for sid,(unused,raw,receipt,receiptpath,captured) in sorted(results.items()):
                require(self.identity(tickers[sid])==identities[sid],'IDENTITY_CHANGED_DURING_CAPTURE')
                ref=decode_intraday_reference(raw,ticker=tickers[sid],captured_at=captured,now=final,maximum_age_seconds=self.max_mark_age)
                require(ref['session']==session and final<datetime.fromisoformat(ref['refresh_by']),'FINAL_MARK_EXPIRED')
                sessions.add((ref['session_open'],ref['session_close']));references[sid]=ref
                for path in (receipt['raw_path'],receiptpath):
                    value=(directory/path).read_bytes();files[path]=value;pins[path]=sha256(value).hexdigest()
                marks[sid]=dict(security_id=sid,ticker=tickers[sid],currency='USD',price=ref['last_price'],
                    valuation_max_age_seconds=self.max_mark_age,price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',observed_at=ref['last_at'],captured_at=captured.isoformat(),checked_at=receipt['checked_at'],
                    source_references=[receipt['raw_path'],receiptpath],source_hashes={p:pins[p] for p in (receipt['raw_path'],receiptpath)})
            require(len(sessions)==1,'MIXED_REGULAR_SESSIONS')
            require(sum(len(raw) for raw in files.values())+sum(len(raw) for raw in source_files.values())<=128*1024*1024,'CAPTURE_PACKAGE_TOO_LARGE')
            require(not (set(files)&set(source_files)),'SOURCE_PATH_CONFLICT')
            files.update(source_files);pins.update(source_pins)
            put('marks.json',marks)
            finished=self._now();require(finished>=final,'SERVER_CLOCK_ROLLBACK')
            require(finished.astimezone(ZoneInfo('America/New_York')).date().isoformat()==session
                    and all(finished<datetime.fromisoformat(ref['refresh_by']) for ref in references.values()),'FINAL_MARK_EXPIRED')
            result=dict(status='MARKS_CAPTURED_UNIT_REVIEW_REQUIRED',account_id=state['account_id'],account_revision=state['revision'],
                session=session,finished_at=finished.isoformat(),marks=marks,identities=identities,source_hashes=pins,
                unit_review_completed=False,action_completeness_verified=False,account_mutated=False,orders_created=False)
            put('complete.json',result)
            return dict(result,files=files)
        except Exception as error:
            reason=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalnum() and len(str(error))<=100 else 'MARK_CAPTURE_FAILED'
            put('failed.json',dict(status='BLOCKED',reason=reason,finished_at=self._now().isoformat(),automatic_retry=False))
            raise

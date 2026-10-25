"""Static versioned V20 capture bodies for an already-verified account projection.

Original network transport, raw mark decoder and V3 receipt normalization are
preserved. No account authority is granted here: public paper wrapper must
replay its formal book. All needed ticker identities must be explicit metadata;
this body never synthesizes real-account events. Existing real modules unchanged.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical
from data.current_research_intraday_execution import fetch_intraday_chart
from data.strategy_account_mark_reference import decode_current_mark as decode_intraday_reference
from data.strategy_account_quote_clock import wait_for_vendor_clock


def require(ok,reason):
    if not ok:raise ValueError(reason)


class VerifiedContextMarketCapture:
    def __init__(self,*,identity_resolver,fetch=fetch_intraday_chart,clock=None,max_workers=4,max_mark_age=120):
        require(type(max_mark_age)is int and max_mark_age in (120,900),'UNSUPPORTED_MARK_AGE_POLICY')
        self.max_mark_age=max_mark_age
        require(type(max_workers)is int and 1<=max_workers<=8,'BOUNDED_CONCURRENCY_REQUIRED')
        self.identity=identity_resolver;self.fetch=fetch;self.clock=clock or (lambda:datetime.now(timezone.utc));self.workers=max_workers

    def _now(self):
        at=self.clock();require(isinstance(at,datetime) and at.tzinfo is not None and at.utcoffset() is not None,'AWARE_SERVER_CLOCK_REQUIRED')
        return at

    def capture(self,*,state,candidate_metadata,output_directory):
        require(type(candidate_metadata)is dict and len(candidate_metadata)<=200,'BOUNDED_CANDIDATE_DOMAIN_REQUIRED')
        tickers={sid:row['ticker'] for sid,row in candidate_metadata.items()}
        needed=set(tickers)|{s for s,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
        require(0<len(needed)<=250,'TOTAL_SECURITY_DOMAIN_TOO_LARGE')
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

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from core.strategy_account_ledger import canonical, require

from data.strategy_account_mark_reference import decode_current_mark
from data.current_research_intraday_execution import fetch_intraday_chart


def verified_mark_transport(raw, *, ticker, received_at, clock, sleep=time.sleep,
                            monotonic=time.monotonic):
    require(type(raw) is bytes and 0 < len(raw) <= 4*1024*1024, 'RAW_QUOTE_BYTES_REQUIRED')
    meta=json.loads(raw)['chart']['result'][0]['meta']
    require(meta['symbol']==ticker and type(meta['regularMarketTime']) is int,
            'MARK_TRANSPORT_IDENTITY_TIME')
    observed=datetime.fromtimestamp(meta['regularMarketTime'],timezone.utc)
    require(received_at.utcoffset() is not None,'AWARE_SERVER_CLOCK_REQUIRED')
    ahead=(observed-received_at).total_seconds()
    require(ahead<=2,'MARK_TRANSPORT_LEAD_EXCEEDS_TWO_SECONDS')
    began=monotonic(); previous=received_at; checked=clock()
    while True:
        require(checked.utcoffset() is not None and checked>=previous,'MARK_TRANSPORT_CLOCK_ROLLBACK')
        elapsed=monotonic()-began
        require(0<=elapsed<=3,'MARK_TRANSPORT_WAIT_EXPIRED')
        if checked>=observed:break
        require(elapsed<3,'MARK_TRANSPORT_WAIT_EXPIRED')
        previous=checked
        sleep(min(0.05,3-elapsed))
        checked=clock()
    return dict(schema='MARK_TRANSPORT_REAL_WAIT_V1',ticker=ticker,
        network_received_at=received_at.isoformat(),verified_at=checked.isoformat(),
        vendor_observed_at=observed.isoformat(),lead_seconds=ahead,
        monotonic_wait_seconds=elapsed,raw_sha256=sha256(raw).hexdigest(),raw_modified=False)


class VerifiedContextTransportCapture:
    def __init__(self, *, identity_resolver, fetch=fetch_intraday_chart, clock=None,
                 max_workers=4,max_mark_age=120,sleep=time.sleep,monotonic=time.monotonic):
        self.identity=identity_resolver;self.fetch=fetch
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.workers=max_workers;self.max_mark_age=max_mark_age
        self.sleep=sleep;self.monotonic=monotonic

    def capture(self, *, state,candidate_metadata,output_directory):
        directory=Path(output_directory);records={}
        def save(name,body):
            with (directory/name).open('xb') as f:
                require(f.write(body)==len(body),'MARK_TIMING_SHORT_WRITE');f.flush();os.fsync(f.fileno())
            require((directory/name).read_bytes()==body,'MARK_TIMING_READBACK')
        def fetch(ticker):
            raw=self.fetch(ticker);received=self.clock()
            token=sha256(ticker.encode()).hexdigest()
            require(type(raw) is bytes and 0<len(raw)<=4*1024*1024,'RAW_QUOTE_BYTES_REQUIRED')
            save(token+'.network.raw',raw)
            save(token+'.network.json',canonical(dict(ticker=ticker,network_received_at=received.isoformat(),raw_sha256=sha256(raw).hexdigest())))
            timing=verified_mark_transport(raw,ticker=ticker,received_at=received,
                clock=self.clock,sleep=self.sleep,monotonic=self.monotonic)
            name=sha256(ticker.encode()).hexdigest()+'.transport.json'
            save(name,canonical(timing));records[ticker]=(name,timing)
            require(self.clock()>=datetime.fromisoformat(timing['verified_at']),'MARK_TRANSPORT_CLOCK_ROLLBACK')
            return raw
        inner=VerifiedContextMarketCapture(identity_resolver=self.identity,fetch=fetch,
            clock=self.clock,max_workers=self.workers,max_mark_age=self.max_mark_age)
        result=inner.capture(state=state,candidate_metadata=candidate_metadata,output_directory=directory)
        require(set(records)=={m['ticker']for m in result['marks'].values()},'MARK_TIMING_DOMAIN')
        for sid,mark in result['marks'].items():
            name,timing=records[mark['ticker']]
            receipt=json.loads(result['files'][mark['source_references'][1]])
            require(timing['raw_sha256']==receipt['raw_sha256'] and
                datetime.fromisoformat(timing['network_received_at'])<=datetime.fromisoformat(timing['verified_at'])
                <=datetime.fromisoformat(receipt['captured_at']),'MARK_TIMING_BINDING')
            body=(directory/name).read_bytes();require(body==canonical(timing),'MARK_TIMING_CHANGED')
            result['files'][name]=body;result['source_hashes'][name]=sha256(body).hexdigest()
            mark['source_references'].append(name);mark['source_hashes'][name]=sha256(body).hexdigest()
        finished=self.clock()
        require(finished>=datetime.fromisoformat(result['finished_at']),'MARK_TRANSPORT_CLOCK_ROLLBACK')
        for mark in result['marks'].values():
            reference=decode_current_mark(result['files'][mark['source_references'][0]],ticker=mark['ticker'],
                captured_at=datetime.fromisoformat(mark['captured_at']),now=finished,
                maximum_age_seconds=self.max_mark_age)
            arrived=datetime.fromisoformat(records[mark['ticker']][1]['network_received_at'])
            require(datetime.fromisoformat(reference['session_open'])<=arrived<=finished
                and (finished-arrived).total_seconds()<self.max_mark_age,'MARK_NETWORK_ARRIVAL_STALE')
        require(sum(map(len,result['files'].values()))<=128*1024*1024,'CAPTURE_PACKAGE_TOO_LARGE')
        result['finished_at']=finished.isoformat()
        save('transport-complete.json',canonical({k:v for k,v in result.items()if k!='files'}))
        after=self.clock()
        try:
            require(after>=finished,'MARK_TRANSPORT_CLOCK_ROLLBACK')
            for mark in result['marks'].values():
                decode_current_mark(result['files'][mark['source_references'][0]],ticker=mark['ticker'],
                    captured_at=datetime.fromisoformat(mark['captured_at']),now=after,
                    maximum_age_seconds=self.max_mark_age)
                arrived=datetime.fromisoformat(records[mark['ticker']][1]['network_received_at'])
                require((after-arrived).total_seconds()<self.max_mark_age,'MARK_NETWORK_ARRIVAL_STALE')
        except Exception:
            save('transport-failed.json',canonical(dict(status='BLOCKED_AFTER_METADATA_BARRIER')))
            raise
        return result

from hashlib import sha256
from datetime import datetime
import json
from core.strategy_account_ledger import require



class VerifiedContextDailyMarketCapture(VerifiedContextTransportCapture):
    def capture(self, **kwargs):
        result = super().capture(**kwargs)
        for mark in result['marks'].values():
            refs = mark['source_references']
            require(len(refs) == 3 and len(set(refs)) == 3
                    and set(mark['source_hashes']) == set(refs), 'DAILY_MARK_TRANSPORT_DOMAIN')
            for name in refs:
                require(sha256(result['files'][name]).hexdigest()
                        == result['source_hashes'][name] == mark['source_hashes'][name],
                        'DAILY_MARK_TRANSPORT_HASH')
            timing_path = refs[2]
            timing = json.loads(result['files'][timing_path])
            receipt = json.loads(result['files'][refs[1]])
            require(timing['schema'] == 'MARK_TRANSPORT_REAL_WAIT_V1'
                    and timing['ticker'] == mark['ticker']
                    and timing['raw_sha256'] == receipt['raw_sha256']
                    == result['source_hashes'][refs[0]]
                    and timing['raw_modified'] is False
                    and receipt['raw_path'] == refs[0]
                    and receipt['captured_at'] == mark['captured_at']
                    and datetime.fromisoformat(timing['network_received_at'])
                    <= datetime.fromisoformat(timing['verified_at'])
                    <= datetime.fromisoformat(mark['captured_at']), 'DAILY_MARK_TRANSPORT_BINDING')
            mark['transport_timing_reference'] = dict(path=timing_path,
                sha256=result['source_hashes'][timing_path])
            mark['source_references'] = refs[:2]
            mark['source_hashes'] = {name: result['source_hashes'][name] for name in refs[:2]}
        # Timing remains in the complete package and is covered by the mark hash.
        return result

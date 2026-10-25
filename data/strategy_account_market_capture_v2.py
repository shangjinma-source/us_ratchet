"""Versioned mark transport wait; original capture/decoder remain unchanged."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from core.strategy_account_ledger import canonical, require
from data.strategy_account_market_capture import StrategyAccountMarketCapture
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


class StrategyAccountMarketCaptureV2:
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
        inner=StrategyAccountMarketCapture(identity_resolver=self.identity,fetch=fetch,
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

"""Explicit, bounded action-source capture. No IO on construction or frozen read.

Request coverage is not proof of complete corporate-action coverage. The account
review consumer must parse and replay these original bytes before using them.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from threading import RLock
from urllib.parse import urlencode, quote
from urllib.request import Request, build_opener
from urllib.error import HTTPError
from scripts.current_research_official_alert_capture import NoRedirect, fetch_official_feed, URL

MAX_DAILY_BYTES=4*1024*1024
MAX_TOTAL_BYTES=128*1024*1024
MAX_SECURITIES=200
ERROR='PAPER_ACTION_SOURCE_UNAVAILABLE'


def require(ok):
    if not ok:raise ValueError(ERROR)


def stamp(value):
    value=datetime.fromisoformat(value) if isinstance(value,str) else value
    require(isinstance(value,datetime) and value.tzinfo is not None)
    return value.astimezone(timezone.utc)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def daily_url(ticker,start,end):
    return 'https://query1.finance.yahoo.com/v8/finance/chart/'+quote(ticker,safe='')+'?'+urlencode(dict(
        period1=int(start.timestamp()),period2=int(end.timestamp())+1,interval='1d',events='div,splits',includePrePost='false'))


def fetch_daily_actions(ticker,start,end):
    url=daily_url(ticker,start,end)
    request=Request(url,headers={'User-Agent':'us-ratchet-paper-action-research/1.0','Accept':'application/json','Accept-Encoding':'identity'})
    try:response=build_opener(NoRedirect()).open(request,timeout=15)
    except HTTPError as error:response=error
    with response:
        return dict(status=response.code,body=response.read(MAX_DAILY_BYTES+1),url=url)


class PaperActionEvidenceSources:
    """Server-owned request only; capture callable, read never fetches or writes."""
    def __init__(self,*,fetch=fetch_daily_actions,rss_fetch=fetch_official_feed,clock=None):
        self.fetch=fetch;self.rss_fetch=rss_fetch
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.lock=RLock();self._attempt=0;self._saved=None

    def capture(self,request):
        with self.lock:self._attempt+=1;attempt=self._attempt;self._saved=None
        request=deepcopy(request);identity=sha256(canonical(request)).hexdigest()
        require(set(request)=={'account_id','state_revision','window_start','observed_floor','securities','current_target_quantities'})
        require(all(type(request[k])is str and request[k] for k in ('account_id','state_revision')))
        start=stamp(request['window_start']);floor=stamp(request['observed_floor']);began=stamp(self.clock())
        require(start<=floor<=began)
        securities=request['securities'];targets=request['current_target_quantities']
        require(type(securities)is dict and len(securities)<=MAX_SECURITIES and type(targets)is dict)
        require(all(type(q)is int and q>=0 and (q==0 or sid in securities) for sid,q in targets.items()))
        for sid,security in securities.items():
            require(type(sid)is str and bool(sid) and type(security)is dict and type(security.get('ticker'))is str
                and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,14}',security['ticker']) is not None)
        require(len({v["ticker"] for v in securities.values()})==len(securities))
        files={};pins={};receipts={};total=0;daily={};received_times=[]
        def put(raw,suffix):
            nonlocal total
            h=sha256(raw).hexdigest();path='paper-action-capture/'+h+suffix
            if path not in files:
                total+=len(raw);require(total<=MAX_TOTAL_BYTES);files[path]=raw;pins[path]=h
            return path
        # Start earlier to include the last market close preceding a weekend baseline.
        requested_from=start-timedelta(days=7)
        for sid,security in sorted(securities.items()):
            ticker=security['ticker']
            if ticker not in daily:
                before=stamp(self.clock());require(began<=before and (before-began).total_seconds()<120)
                response=self.fetch(ticker,requested_from,before);received=stamp(self.clock())
                require(before<=received and (received-began).total_seconds()<120)
                raw=response['body'];require(response['status']==200 and type(raw)is bytes and 0<len(raw)<=MAX_DAILY_BYTES)
                url=daily_url(ticker,requested_from,before)
                require(response.get('url',url)==url)
                daily[ticker]=(put(raw,'.raw'),raw,before,received,url)
            rawpath,raw,through,received,url=daily[ticker];received_times.append(received)
            receipt=dict(security_id=sid,ticker=ticker,raw_path=rawpath,raw_sha256=sha256(raw).hexdigest(),
                http_status=200,body_truncated=False,transport_error=None,requested_from=requested_from.isoformat(),
                requested_through=through.isoformat(),received_at=received.isoformat(),events_requested=['dividends','splits'],interval='1d',url=url,
                request_period1=int(requested_from.timestamp()),request_period2=int(through.timestamp())+1)
            receipts[sid]=put(canonical(receipt),'.json')
        rss_raw=rss_receipt=None
        if securities:
            started=stamp(self.clock());require(started>=max(received_times))
            response=self.rss_fetch();received=stamp(self.clock());raw=response['body']
            require(started<=received and (received-began).total_seconds()<120 and response['status']==200
                and type(raw)is bytes and 0<len(raw)<=2*1024*1024)
            rss_raw=put(raw,'.xml');rss_receipt=put(canonical(dict(url=URL,http_status=200,started_at=started.isoformat(),
                received_at=received.isoformat(),raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw))),'.json')
        finished=stamp(self.clock());require(finished>=began and (finished-began).total_seconds()<120)
        if securities:require(finished>=received)
        received_times.extend((began,finished))
        result=dict(files=files,source_hashes=pins,documents=dict(action_receipts=receipts,rss_raw=rss_raw,rss_receipt=rss_receipt))
        with self.lock:
            require(attempt==self._attempt)
            self._saved=(identity,deepcopy(result),tuple(received_times))
        return deepcopy(result)

    __call__=capture

    def read(self,request):
        identity=sha256(canonical(request)).hexdigest()
        with self.lock:
            require(self._saved is not None and self._saved[0]==identity)
            result,times=deepcopy(self._saved[1]),self._saved[2]
        now=stamp(self.clock());require(all(0<=(now-t).total_seconds()<120 for t in times))
        return result

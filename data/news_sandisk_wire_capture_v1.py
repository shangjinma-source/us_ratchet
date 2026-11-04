"""Bounded Sandisk Business Wire capture candidate; no model/account access."""
from datetime import datetime,timezone,timedelta
from hashlib import sha256
import json,time
from pathlib import Path
import requests
from data.news_issuer_source import API
from data.news_sandisk_wire_v1 import headlines,parse_story,moment,require


def capture(cache,*,session=None,clock=None):
    session=session or requests
    clock=clock or (lambda:datetime.now(timezone.utc))
    now=clock();require(now.utcoffset() is not None,'WIRE_AWARE_CLOCK_REQUIRED')
    directory=Path(cache)/'raw';directory.mkdir(parents=True,exist_ok=True)
    receipts=[];events=[];errors=[];calls=0;started=time.monotonic()
    def fetch(endpoint,params):
        nonlocal calls
        require(endpoint in ('getHeadlines.json','getStory.json') and calls<3,'WIRE_REQUEST_BUDGET')
        require(time.monotonic()-started<55,'WIRE_CAPTURE_DEADLINE')
        calls+=1;requested=clock().isoformat()
        with session.get(API+endpoint,params=params,timeout=(5,15),stream=True,allow_redirects=False,
                         headers={'User-Agent':'UsRatchet personal research news reader/1.0'}) as response:
            raw=bytearray()
            for block in response.iter_content(16384):
                raw.extend(block)
                require(len(raw)<=1500000 and time.monotonic()-started<55,'WIRE_RESPONSE_BUDGET')
            data=bytes(raw);digest=sha256(data).hexdigest();received=clock().isoformat()
            (directory/('wire-'+digest+'.json')).write_bytes(data)
            receipts.append(dict(source='Sandisk Business Wire via QuoteMedia',url=API+endpoint,params=dict(params),
                status=response.status_code,requested_at=requested,fetched_at=received,sha256=digest,bytes=len(data)))
            require(response.status_code==200,'WIRE_HTTP_STATUS')
        return json.loads(data),received
    try:
        listing,_=fetch('getHeadlines.json',dict(topics='SNDK',src='bwi',start=(now-timedelta(days=90)).date().isoformat(),end=now.date().isoformat(),summary='true'))
        seen=set();eligible=[]
        for row in headlines(listing):
            published=moment(row['datetime'])
            if now-timedelta(days=90)<=published<=now and row['permalink'] not in seen:
                seen.add(row['permalink']);eligible.append(row)
        for row in eligible[:2]:
            try:
                document,received=fetch('getStory.json',dict(storyId=str(row['newsid']),newslang='en'))
                events.append(parse_story(row,document,received))
            except (ValueError,KeyError,TypeError,OSError,requests.RequestException) as error:
                errors.append(dict(source='Sandisk Business Wire via QuoteMedia',story_id=str(row['newsid']),error_type=type(error).__name__,message='WIRE_STORY_UNAVAILABLE_OR_UNVERIFIED'))
    except (ValueError,KeyError,TypeError,OSError,requests.RequestException) as error:
        errors.append(dict(source='Sandisk Business Wire via QuoteMedia',error_type=type(error).__name__,message='WIRE_LIST_UNAVAILABLE_OR_UNVERIFIED'))
    return dict(events=events,receipts=receipts,errors=errors,request_count=calls,
                scope='DISTRIBUTOR_RELEASE_TIME_NOT_GLOBAL_FIRST_PUBLICATION')

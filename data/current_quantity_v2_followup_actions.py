"""Bounded saved-source interval check, not certification of absent actions."""
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
import re
import html
from decimal import Decimal
from zoneinfo import ZoneInfo
from data.current_quantity_v2_paper_action_sources import daily_url
from scripts.current_research_official_alert_capture import parse_official_feed, URL


def check_known_actions(events,*,start,end,captured):
    """Late split-adjusted historical bars cannot be compared to the old limit.

    Cash dividends/capital-gain distributions after the target day do not alone
    change share units. Unknown event kinds remain conservative until classified.
    Future effective timestamps beyond this capture are not treated as occurred.
    """
    ny=ZoneInfo('America/New_York')
    start_day=start.astimezone(ny).date().isoformat();end_day=end.astimezone(ny).date().isoformat()
    if type(events)is not dict:raise ValueError('BLOCKED_ACTION_SOURCE_VALIDATION')
    for kind,records in events.items():
        if type(records)is not dict:raise ValueError('BLOCKED_ACTION_SOURCE_VALIDATION')
        for event in records.values():
            if type(event)is not dict or type(event.get('date'))is not int:raise ValueError('BLOCKED_ACTION_SOURCE_VALIDATION')
            effective=datetime.fromtimestamp(event['date'],ny);day=effective.date().isoformat()
            if effective>captured:continue
            if start_day<=day<=end_day:raise ValueError('BLOCKED_KNOWN_CORPORATE_ACTION')
            if day>end_day and kind not in ('dividends','capitalGains'):
                raise ValueError('BLOCKED_POST_HORIZON_UNIT_CHANGE')


def review_interval_actions(*,files,pins,evidence,security_id,ticker,start,end,now,daily_closes,latest_daily_capture):
    consumed={}
    def require(ok,reason='BLOCKED_ACTION_SOURCE_VALIDATION'):
        if not ok:raise ValueError(reason)
    def stamp(value):
        result=datetime.fromisoformat(value);require(result.tzinfo is not None);return result
    def read(path,limit=4*1024*1024):
        raw=files[path];require(type(raw)is bytes and len(raw)<=limit and sha256(raw).hexdigest()==pins[path]);consumed[path]=pins[path];return raw
    if evidence is None:raise ValueError('PENDING_INTERVAL_ACTION_SOURCES')
    receipt=json.loads(read(evidence['daily_receipt_path']))
    left,right,received=map(stamp,(receipt['requested_from'],receipt['requested_through'],receipt['received_at']))
    require(receipt['security_id']==security_id and receipt['ticker']==ticker
        and receipt['http_status']==200 and receipt['body_truncated']is False and receipt['transport_error']is None
        and receipt['events_requested']==['dividends','splits'] and receipt['interval']=='1d'
        and left<=start<=end<=right<=received<=now
        and receipt['request_period1']==int(left.timestamp()) and receipt['request_period2']==int(right.timestamp())+1
        and receipt['url']==daily_url(ticker,left,right))
    require(end<=latest_daily_capture<=right,'BLOCKED_ACTION_INTERVAL_BEFORE_PRICE_CAPTURE')
    raw=read(receipt['raw_path']);require(sha256(raw).hexdigest()==receipt['raw_sha256'])
    chart=json.loads(raw,parse_float=Decimal)['chart'];require(chart.get('error')is None and len(chart['result'])==1)
    channel=chart['result'][0];meta=channel['meta']
    require(meta['symbol']==ticker and meta['currency']=='USD' and meta['instrumentType']=='EQUITY'
        and meta['exchangeTimezoneName']=='America/New_York' and meta['dataGranularity']=='1d')
    ny=ZoneInfo('America/New_York')
    check_known_actions(channel.get('events',{}),start=start,end=end,captured=received)
    times=channel['timestamp'];require(type(times)is list and all(type(value)is int and value>0 for value in times) and times==sorted(set(times)))
    days=[datetime.fromtimestamp(value,ny).date().isoformat() for value in times];require(len(days)==len(set(days)))
    quotes=channel['indicators']['quote'];require(len(quotes)==1 and len(quotes[0]['close'])==len(days))
    marks=dict(zip(days,quotes[0]['close']))
    for day,close in daily_closes.items():
        require(day in marks and Fraction(str(marks[day]))==Fraction(close),'BLOCKED_INTERVAL_PRICE_COORDINATE_MISMATCH')
    rss_receipt=json.loads(read(evidence['rss_receipt_path']))
    rss=read(evidence['rss_raw_path'],2*1024*1024)
    begun,captured=stamp(rss_receipt['started_at']),stamp(rss_receipt['received_at'])
    require(received<=begun<=captured<=now and rss_receipt['url']==URL and rss_receipt['http_status']==200
        and rss_receipt['raw_sha256']==sha256(rss).hexdigest() and rss_receipt['stored_bytes']==len(rss))
    parsed=parse_official_feed(rss,observed_at=captured)
    require(not parsed['channel']['publication_time_issue'] and parsed['channel']['future_publication']is not True)
    def normalized(text):
        return ' '.join(re.sub(r'<[^>]*>', ' ', html.unescape(text)).split())
    names=[normalized(meta[k]) for k in ('longName','shortName') if isinstance(meta.get(k),str) and len(normalized(meta[k]))>=2]
    for item in parsed['items']:
        require(not item['publication_time_issue'] and item['future_publication']is False and not item['description_truncated'])
        text=normalized(item['title']+' '+item['description_summary'])
        require(not any(re.search(r'(?<![A-Za-z0-9])'+re.escape(name)+r'(?![A-Za-z0-9])',text,re.I) for name in [ticker,*names]),'BLOCKED_OFFICIAL_ACTION_CANDIDATE')
    return dict(status='CONDITIONAL_NO_KNOWN_CHANGE_IN_CHECKED_SOURCES',source_hashes=consumed,
        coverage_complete=False,source_authenticated=False,limited_issuer_name_coverage=not bool(names),
        limitation='Requested daily interval and visible official feed checked; omitted actions or identity changes remain possible; no certification of nominal continuity.')

"""Bounded saved official RSS observation; no notice fetch or action approval."""
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
import argparse
import html
import json
import re
import xml.etree.ElementTree as ET

URL='https://m.nasdaqtrader.com/rss.aspx?categorylist=0&feed=currentheadlines'
ROOT=Path(__file__).resolve().parents[1]
MAX_BYTES=2*1024*1024


def utc_now():return datetime.now(timezone.utc)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def fetch_official_feed():
    request=Request(URL,headers={'User-Agent':'us-ratchet-official-alert-research/1.0','Accept':'application/rss+xml,application/xml,text/xml'})
    try:response=build_opener(NoRedirect()).open(request,timeout=15)
    except HTTPError as error:response=error
    with response:
        body=response.read(MAX_BYTES+1)
        return dict(status=response.code,headers={k:response.headers.get(k) for k in ('Content-Type','Content-Encoding','Location')},body=body)


def require(ok,reason):
    if not ok:raise ValueError(reason)


def parse_official_feed(raw,*,observed_at):
    require(isinstance(raw,bytes) and 0<len(raw)<=MAX_BYTES,'EMPTY_OR_OVERSIZE_XML')
    require(observed_at.tzinfo is not None,'AWARE_OBSERVATION_TIME_REQUIRED')
    text=raw.decode('utf-8-sig')
    require(not re.search(r'<!\s*(DOCTYPE|ENTITY)\b',text,re.I),'XML_DECLARATIONS_FORBIDDEN')
    document=ET.fromstring(text)
    require(document.tag=='rss','NOT_RSS_DOCUMENT')
    channels=document.findall('channel');require(len(channels)==1,'RSS_CHANNEL_REQUIRED')
    channel=channels[0]
    items=channel.findall('item');require(0<len(items)<=1000,'EMPTY_OR_EXCESSIVE_CHANNEL')
    def channel_value(name):
        matches=[node for node in channel if node.tag.rsplit('}',1)[-1]==name]
        require(len(matches)<=1,'DUPLICATE_CHANNEL_METADATA:'+name)
        return ''.join(matches[0].itertext()).strip() if matches else None
    declared=channel_value('numItems')
    if declared is not None:
        require(re.fullmatch(r'[0-9]+',declared) is not None,'INVALID_DECLARED_ITEM_COUNT')
        require(int(declared)==len(items),'DECLARED_ITEM_COUNT_MISMATCH')
    channel_published=channel_value('pubDate');channel_timestamp=None;channel_time_issue=None
    if channel_published is not None:
        try:
            channel_timestamp=parsedate_to_datetime(channel_published)
            require(channel_timestamp is not None and channel_timestamp.tzinfo is not None,'CHANNEL_TIMEZONE_NOT_EXPLICIT')
            channel_timestamp=channel_timestamp.astimezone(timezone.utc)
        except (ValueError,TypeError,OverflowError) as error:
            channel_time_issue=str(error);channel_timestamp=None
    channel_metadata=dict(pubDate=channel_published,ttl=channel_value('ttl'),declared_num_items=declared,
        actual_num_items=len(items),declared_count_matches=None if declared is None else True,
        published_at_utc=channel_timestamp.isoformat() if channel_timestamp is not None else None,
        publication_time_issue=channel_time_issue,
        future_publication=channel_timestamp>observed_at if channel_timestamp is not None else None)
    results=[]
    for index,item in enumerate(items):
        def field(name):return ''.join(item.find(name).itertext()).strip() if item.find(name) is not None else ''
        categories=[node for node in item if node.tag.rsplit('}',1)[-1]=='NewsCategory']
        require(len(categories)<=1,'DUPLICATE_ITEM_NEWS_CATEGORY')
        news_category=''.join(categories[0].itertext()).strip() if categories else None
        title=field('title');require(bool(title),'ITEM_TITLE_REQUIRED')
        published=field('pubDate');parsed=None;time_issue=None
        try:
            timestamp=parsedate_to_datetime(published)
            require(timestamp is not None and timestamp.tzinfo is not None,'PUBLICATION_TIMEZONE_NOT_EXPLICIT')
            parsed=timestamp.astimezone(timezone.utc)
        except (ValueError,TypeError,OverflowError) as error:time_issue=str(error)
        summary=html.unescape(re.sub('<[^>]*>',' ',field('description')))
        summary=' '.join(summary.split())[:2000]
        results.append(dict(index=index,title=title,news_category=news_category,link=field('link'),guid=field('guid'),pubDate=published,
            published_at_utc=parsed.isoformat() if parsed is not None else None,
            publication_time_issue=time_issue,future_publication=parsed>observed_at if parsed is not None else None,
            description_summary=summary,description_truncated=len(' '.join(html.unescape(re.sub('<[^>]*>',' ',field('description'))).split()))>2000,
            title_match_candidate=bool(re.search(r'\b(?:SNDK|Sandisk)\b',title,re.I)),entity_confirmed=False))
    category_counts={}
    for row in results:
        category=row['news_category'] or 'UNSPECIFIED'
        category_counts[category]=category_counts.get(category,0)+1
    channel_metadata['news_category_counts']=dict(sorted(category_counts.items()))
    matches=[row['index'] for row in results if row['title_match_candidate']]
    return dict(schema='OFFICIAL_RSS_VISIBLE_ALERTS_V1',status='TITLE_MATCH_CANDIDATES_REQUIRE_REVIEW' if matches else 'NO_MATCH_IN_VISIBLE_FEED_NOT_NO_ACTION',
        official_feed_url=URL,observed_at=observed_at.isoformat(),channel=channel_metadata,items=results,matching_item_indexes=matches,
        coverage_complete=False,retention_unknown=True,entity_confirmed=False,unit_registry_generated=False,automatic_approval=False,
        limitations=['Visible feed may omit older notices or actions. No match does not establish absence of corporate actions.',
                    'Title matching is a candidate hint, not verified security identity. Links are stored only, never fetched.',
                    'Local capture timestamps and hashes are not externally trusted timestamps.'])


def capture_official_alerts(output_directory,*,root=ROOT,capture=False,fetch=fetch_official_feed,clock=utc_now):
    root=Path(root).resolve();relative=Path(output_directory)
    require(not relative.is_absolute() and not relative.drive and '..' not in relative.parts and str(relative) not in ('','.'),'OUTPUT_MUST_BE_RELATIVE_CHILD')
    output=(root/relative).resolve();require(output.is_relative_to(root) and output!=root,'OUTPUT_OUTSIDE_ROOT')
    require(not output.exists(),'CREATE_ONLY_OUTPUT_EXISTS')
    intent=dict(url=URL,output_directory=output.relative_to(root).as_posix(),http_calls=0,timeout_seconds=15,max_bytes=MAX_BYTES,
        redirects_allowed=False,retries=0,source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),coverage_complete=False)
    if not capture:return dict(intent,status='DRY_RUN_NO_HTTP_NO_FILES')
    output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        require(output.resolve().is_relative_to(root),'OUTPUT_OUTSIDE_ROOT')
        with (output/name).open('xb') as stream:stream.write(value)
    def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2).encode('utf-8')
    started=clock();require(started.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
    save('intent.json',encoded(dict(intent,started_at_utc=started.astimezone(timezone.utc).isoformat())))
    raw=b'';status=None;headers={};transport_error=None
    try:
        response=fetch();received=clock()
        raw=response['body'];require(isinstance(raw,bytes),'RAW_BYTES_REQUIRED')
        status=response['status'];headers=response.get('headers',{})
    except Exception as error:
        received=clock();transport_error=type(error).__name__+': '+str(error)
    require(received.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
    raw=raw[:MAX_BYTES+1];save('response.bin',raw)
    receipt=dict(url=URL,http_status=status,headers=headers,request_started_at_utc=started.astimezone(timezone.utc).isoformat(),received_at_utc=received.astimezone(timezone.utc).isoformat(),raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw),body_truncated=len(raw)>MAX_BYTES,transport_error=transport_error,code_sha256=intent['source_sha256'],http_calls=1)
    save('receipt.json',encoded(receipt))
    try:
        require(transport_error is None,'TRANSPORT_FAILED')
        require(type(status) is int and status==200,'HTTP_STATUS_NOT_200_NO_REDIRECT_FOLLOWED')
        require(not receipt['body_truncated'],'RESPONSE_TOO_LARGE')
        require(received>=started,'CLOCK_REGRESSED')
        result=parse_official_feed(raw,observed_at=received)
    except (ValueError,TypeError,ET.ParseError,UnicodeError) as error:
        result=dict(status='UNAVAILABLE',reason=str(error),coverage_complete=False,automatic_approval=False)
    result.update(raw_sha256=receipt['raw_sha256'],receipt_sha256=sha256(encoded(receipt)).hexdigest(),code_sha256=intent['source_sha256'])
    save('result.json',encoded(result));return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--capture',action='store_true')
    args=parser.parse_args();result=capture_official_alerts(args.output,capture=args.capture)
    print(json.dumps({k:result.get(k) for k in ('status','reason','coverage_complete')},ensure_ascii=False))

if __name__=='__main__':main()

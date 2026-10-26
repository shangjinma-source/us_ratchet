"""Candidate only: Moderna issuer-distributed releases, not generic ticker mentions.

Source chain: Moderna official site -> feeds.issuerdirect.com -> public
ACCESS Newswire/QuoteMedia JSON. No account, trading or model calls.
"""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json
import time
import requests
from hashlib import sha256
from html import unescape
import re

FEED_URL='https://feeds.issuerdirect.com/news.html?exclude_headlines=Global+AI,Tectonic+Therapeutic,Platform+Biotech+Models+Draw&latest=3&news_template=boxes-mrna&symbol=MRNA'
API='https://www.accesswire.com/qm/data/'

def text(value):return re.sub(r'\s+',' ',unescape(re.sub(r'<[^>]+>',' ',value))).strip()

def candidate_headlines(document):
    groups=document['results']['news']
    matches=[group for group in groups if group.get('topicstring')=='MRNA']
    if len(matches)!=1:raise ValueError('MRNA_TOPIC_REQUIRED')
    rows=[]
    for row in matches[0]['newsitem']:
        if not row['headline'].startswith('Moderna '):continue
        if any(noise in row['headline'].casefold() for noise in ('top employer','best workplace','investigation','class action')):continue
        if row['qmsource']!='bayaw' or 'NONCOMPANY' in row.get('topic',''):continue
        rows.append(row)
    return sorted(rows,key=lambda row:row['datetime'],reverse=True)[:4]

def parse_issuer_story(headline,document,fetched_at):
    envelope=document['qmcistory'];story=envelope['qmnews']['qmstory']
    if str(envelope['storyid'])!=str(headline['newsid']):raise ValueError('STORY_ID_MISMATCH')
    if story['qmheadline']!=headline['headline'] or story['datetime']!=headline['datetime']:
        raise ValueError('HEADLINE_DATE_MISMATCH')
    if headline.get('qmsource')!='bayaw' or 'NONCOMPANY' in headline.get('topic',''):
        raise ValueError('ISSUER_DISTRIBUTION_HEADLINE_REQUIRED')
    body=text(story['qmtext'])
    if not headline['headline'].startswith('Moderna ') or 'SOURCE: Moderna, Inc.' not in body:
        raise ValueError('COMPANY_ISSUER_SOURCE_REQUIRED')
    if not ('NASDAQ:MRNA' in body or 'NASDAQ: MRNA' in body) or '@modernatx.com' not in body:
        raise ValueError('ISSUER_TICKER_AND_CONTACT_REQUIRED')
    if 'ACCESS Newswire' not in envelope['source']:raise ValueError('EXPECTED_DISTRIBUTOR_REQUIRED')
    published=datetime.fromisoformat(story['datetime'])
    if published.tzinfo is None:raise ValueError('REAL_PUBLICATION_ZONE_REQUIRED')
    stamp=published.astimezone(timezone.utc).isoformat()
    if published>datetime.fromisoformat(fetched_at):raise ValueError('FUTURE_STORY_REJECTED')
    # Expose a verified source URL from the headline API rather than inventing an issuer page path.
    url=headline['storyurl']
    if not url.startswith('https://api.quotemedia.com/supplement/news-story/?'):
        raise ValueError('UNEXPECTED_PUBLIC_STORY_URL')
    return dict(id=sha256(url.encode()).hexdigest()[:24],title=headline['headline'],url=url,
        source='Moderna 公司发布（ACCESS Newswire / QuoteMedia）',source_type='issuer_distributed',
        published_at=stamp,published_raw=story['datetime'],collected_at=fetched_at,tickers=['MRNA'],relevance='company',
        content_kind='ISSUER_RELEASE_BODY',source_text=body[:6000],summary=body[:1200],
        content_sha256=sha256(body.encode()).hexdigest(),evidence=[url],
        uncertainty=['公司自行发布，经官网链接的发行服务取得；尚无独立来源交叉确认。']+(['正文超过6000字符，分析输入截取前6000字符。'] if len(body)>6000 else []),
        analysis_status='NOT_ANALYZED',model=None,issuer_source_chain=['https://investors.modernatx.com/',FEED_URL,API+'getStory.json'],
        noise_hint='LOW_INFORMATION_EMPLOYER_AWARD' if 'Top Employer' in headline['headline'] else None)


def capture(cache, *, session=None, now=None):
    """At most one headlines and two stories; no retry, no arbitrary URL input.

    Moderna official newsroom embeds the FEED_URL above. Its inspected news.js
    calls these public getHeadlines/getStory endpoints. Ticker matching alone is
    insufficient: parse_issuer_story additionally checks the issuing company.
    """
    session=session or requests
    now=now or datetime.now(timezone.utc)
    cache=Path(cache);raw_directory=cache/'raw';raw_directory.mkdir(parents=True,exist_ok=True)
    events,receipts,errors=[],[],[];calls=0;started=time.monotonic()
    def fetch(endpoint,params):
        nonlocal calls
        if endpoint not in ('getHeadlines.json','getStory.json') or calls>=3:
            raise ValueError('FIXED_ENDPOINT_AND_THREE_REQUEST_LIMIT')
        if time.monotonic()-started>55:raise ValueError('CAPTURE_TIME_BUDGET')
        calls+=1;requested=datetime.now(timezone.utc).isoformat()
        with session.get(API+endpoint,params=params,timeout=(5,15),stream=True,allow_redirects=False,
                         headers={'User-Agent':'UsRatchet personal research news reader/1.0'}) as response:
            response.raise_for_status()
            if response.status_code!=200:raise ValueError('EXPECTED_HTTP_200')
            raw=bytearray()
            for block in response.iter_content(16384):
                raw.extend(block)
                if len(raw)>1500000 or time.monotonic()-started>55:raise ValueError('CAPTURE_SIZE_OR_TIME_BUDGET')
        received=datetime.now(timezone.utc).isoformat();body=bytes(raw);digest=sha256(body).hexdigest()
        path=raw_directory/('issuer-'+digest+'.json')
        if not path.exists():path.write_bytes(body)
        receipts.append(dict(source='Moderna issuer-distributed releases',url=API+endpoint,params=params,
                             requested_at=requested,fetched_at=received,sha256=digest,bytes=len(body)))
        return json.loads(body),received
    try:
        headlines,_=fetch('getHeadlines.json',dict(topics='MRNA',noSrc='qmr',
            src='pzo,bayaw,prn,bwi,TheNewsWire,nfil,actw,irw,acn,cnw,nwd,glpr,nwmw',
            thumbnailurl='true',summary='true',summLen=300,start=(now-timedelta(days=90)).date().isoformat(),end=now.date().isoformat()))
        eligible=[]
        for headline in candidate_headlines(headlines):
            stamp=datetime.fromisoformat(headline['datetime'])
            if stamp.tzinfo and now-timedelta(days=90)<=stamp<=now:eligible.append(headline)
        for headline in eligible[:2]:
            try:
                story,fetched=fetch('getStory.json',dict(storyId=str(headline['newsid']),newslang='en'))
                events.append(parse_issuer_story(headline,story,fetched))
            except Exception as error:
                errors.append(dict(source='Moderna issuer-distributed releases',story_id=str(headline['newsid']),error_type=type(error).__name__,message='ISSUER_STORY_UNAVAILABLE_OR_UNVERIFIED'))
    except Exception as error:
        errors.append(dict(source='Moderna issuer-distributed releases',error_type=type(error).__name__,message='ISSUER_FEED_UNAVAILABLE_OR_UNVERIFIED'))
    return dict(events=events,receipts=receipts,errors=errors,request_count=calls,
                source_chain=['https://investors.modernatx.com/',FEED_URL],scope='ISSUER_DISTRIBUTED_NOT_INDEPENDENT_CONFIRMATION')

"""Offline Sandisk-issued Business Wire distribution parser. Not mounted.

Publication time is the distributor's timestamp, not proven global first release.
"""
from datetime import datetime,timezone
from hashlib import sha256
import re
from urllib.parse import urlsplit,parse_qs
from data.news_issuer_source import text


def require(ok,reason):
    if not ok:raise ValueError(reason)


def moment(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    require(result.utcoffset() is not None,'WIRE_AWARE_TIME_REQUIRED')
    return result


def headlines(document):
    groups=[group for group in document['results']['news'] if group.get('topicstring')=='SNDK']
    require(len(groups)==1,'WIRE_SNDK_TOPIC_REQUIRED')
    rows=[]
    for row in groups[0]['newsitem']:
        topics=set(row.get('topic','').strip('[]').split(','))
        if row.get('qmsource')=='bwi' and 'SNDK' in topics and 'NONCOMPANY' not in topics and row.get('headline','').startswith('Sandisk '):
            moment(row['datetime']);rows.append(row)
    return sorted(rows,key=lambda row:moment(row['datetime']),reverse=True)[:4]


def parse_story(headline,document,fetched_at):
    topics=set(headline.get('topic','').strip('[]').split(','))
    require(headline.get('qmsource')=='bwi' and 'SNDK' in topics and 'NONCOMPANY' not in topics,
            'WIRE_ISSUER_HEADLINE_REQUIRED')
    require(headline['headline'].startswith('Sandisk '),'WIRE_ISSUER_TITLE_REQUIRED')
    envelope=document['qmcistory'];story=envelope['qmnews']['qmstory']
    require(envelope.get('source')=='Business Wire via QuoteMedia','WIRE_DISTRIBUTOR_REQUIRED')
    require(str(envelope['storyid'])==str(headline['newsid']),'WIRE_STORY_ID_MISMATCH')
    require(story['qmheadline']==headline['headline'] and story['datetime']==headline['datetime'],
            'WIRE_HEADLINE_TIME_MISMATCH')
    require(story.get('qmtopics',{}).get('qmsymbol')==['SNDK'],'WIRE_STORY_SYMBOL_REQUIRED')
    permalink=headline.get('permalink','')
    require(re.fullmatch(r'https://www\.businesswire\.com/news/home/[0-9]{14}/en/',permalink) is not None,
            'WIRE_PUBLISHER_LINK_REQUIRED')
    body=text(story['qmtext'])
    require(len(body)>=100 and permalink in body and '@sandisk.com' in body
            and re.search(r'Sandisk Corporation\s*\(Nasdaq:\s*SNDK\)',body,re.I),'WIRE_ISSUER_BODY_REQUIRED')
    published,observed=moment(story['datetime']),moment(fetched_at)
    require(published<=observed,'WIRE_FUTURE_PUBLICATION')
    url=headline['storyurl'];parts=urlsplit(url);query=parse_qs(parts.query)
    require(parts.scheme=='https' and parts.netloc=='api.quotemedia.com'
            and parts.path=='/supplement/news-story/' and not parts.fragment
            and query=={'webmasterId':['102691'],'storyId':[str(headline['newsid'])]},'WIRE_STORY_URL_MISMATCH')
    return dict(id=sha256(url.encode()).hexdigest()[:24],title=headline['headline'],url=url,
        source='Sandisk 公司发布（Business Wire / QuoteMedia）',source_type='issuer_distributed',
        published_at=published.astimezone(timezone.utc).isoformat(),published_raw=story['datetime'],
        collected_at=fetched_at,tickers=['SNDK'],relevance='company',content_kind='SANDISK_DISTRIBUTED_BODY',
        source_text=body[:6000],content_sha256=sha256(body.encode()).hexdigest(),evidence=[url,permalink],
        publisher_permalink=permalink,publication_scope='DISTRIBUTOR_RELEASE_TIME',
        uncertainty=['发行人自行发布，经分发商取得；非独立证实，不保证全球最早公开时间。'],
        analysis_status='NOT_ANALYZED',model=None)

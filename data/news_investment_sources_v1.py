"""Offline full-body recovery from current news capture receipts; no fetching."""
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from data.news_issuer_source import parse_issuer_story, text, API
from data.news_sandisk_parser import parse_release
from core.news_investment_review_v1 import moment, require


def raw_bytes(cache, receipt, prefix, suffix):
    digest=receipt['sha256']
    require(len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'RAW_HASH_INVALID')
    path=cache/'raw'/(prefix+digest+suffix)
    raw=path.read_bytes()
    require(sha256(raw).hexdigest()==digest,'RAW_HASH_MISMATCH')
    return raw


def recover(event, receipts, cache):
    kind=event.get('content_kind')
    if kind=='ISSUER_RELEASE_BODY' and event.get('tickers')==['MRNA']:
        headlines=[]
        for receipt in receipts:
            if receipt.get('url')==API+'getHeadlines.json':
                doc=json.loads(raw_bytes(cache,receipt,'issuer-','.json'))
                for group in doc['results']['news']:
                    if group.get('topicstring')=='MRNA':headlines.extend(group['newsitem'])
        matches=[h for h in headlines if h.get('storyurl')==event['url'] and h.get('headline')==event['title']]
        require(bool(matches),'HEADLINE_RECEIPT_MISSING')
        recovered=[]
        for headline in matches:
            for receipt in receipts:
                if receipt.get('url')!=API+'getStory.json' or str(receipt.get('params',{}).get('storyId'))!=str(headline['newsid']):continue
                if receipt['fetched_at']!=event['collected_at']:continue
                raw=raw_bytes(cache,receipt,'issuer-','.json');doc=json.loads(raw)
                parsed=parse_issuer_story(headline,doc,receipt['fetched_at'])
                body=text(doc['qmcistory']['qmnews']['qmstory']['qmtext'])
                recovered.append((parsed,body,receipt['sha256']))
    elif kind=='OFFICIAL_RELEASE_BODY' and event.get('tickers')==['SNDK']:
        from bs4 import BeautifulSoup
        recovered=[]
        for receipt in receipts:
            if receipt.get('url')!=event['url'] or receipt.get('status')!=200 or receipt['fetched_at']!=event['collected_at']:continue
            raw=raw_bytes(cache,receipt,'sandisk-','.raw')
            parsed=parse_release(raw,event['url'],receipt['fetched_at'])['event']
            body=BeautifulSoup(raw,'html.parser').find('h1').parent.select_one('.para-text').get_text(' ',strip=True)
            recovered.append((parsed,body,receipt['sha256']))
    else:
        raise ValueError('FULL_BODY_RECOVERY_UNSUPPORTED')
    require(bool(recovered),'MATCHING_RAW_RECEIPT_MISSING')
    unique={}
    for parsed,body,digest in recovered:
        for key in ('id','url','title','content_sha256','tickers'):
            require(parsed[key]==event[key],'EVENT_RAW_IDENTITY_MISMATCH')
        require(moment(parsed['published_at'])==moment(event['published_at']),'EVENT_RAW_PUBLICATION_MISMATCH')
        require(sha256(body.encode('utf-8')).hexdigest()==event['content_sha256'],'FULL_BODY_HASH_MISMATCH')
        unique[(body,digest)]=(body,digest)
    require(len(unique)==1,'AMBIGUOUS_RAW_RECOVERY')
    return next(iter(unique.values()))


def build_sources(snapshot,cache,positions,*,max_chars=60000):
    require(type(max_chars) is int and 1<=max_chars<=110000,'BOUNDED_SOURCE_BUDGET_REQUIRED')
    cache=Path(cache);now=moment(snapshot['generated_at'])
    mapping={}
    for position in positions:
        mapping.setdefault(position['ticker'],set()).add(position['security_id'])
    sources={};coverage=[];counts={};total=0
    events=sorted(snapshot['events'],key=lambda e:e.get('published_at',''),reverse=True)
    for event in events:
        row=dict(event_id=event.get('id'),tickers=event.get('tickers',[]),status='REJECTED')
        try:
            require(event.get('relevance')=='company','UNSCOPED_MACRO_NOT_ADMITTED')
            tickers=event.get('tickers',[])
            require(len(tickers)==1 and len(mapping.get(tickers[0],set()))==1,'UNIQUE_POSITION_IDENTITY_REQUIRED')
            sid=next(iter(mapping[tickers[0]]))
            publication,observed=moment(event['published_at']),moment(event['collected_at'])
            require(publication<=observed<=now,'SOURCE_TIME_INVALID')
            require(now-publication<=timedelta(days=7),'OLDER_THAN_SEVEN_DAYS')
            body,raw_digest=recover(event,snapshot['source_receipts'],cache)
            require(counts.get(sid,0)<2,'LATEST_TWO_SOURCE_LIMIT')
            require(total+len(body)<=max_chars,'FULL_TEXT_BATCH_BUDGET_EXCEEDED')
            source_id=event['id']+':'+event['content_sha256']
            require(source_id not in sources,'DUPLICATE_SOURCE')
            sources[source_id]=dict(id=source_id,security_ids=[sid],tickers=tickers,title=event['title'],url=event['url'],
                content_kind='FULL_TEXT',text=body,text_sha256=event['content_sha256'],raw_sha256=raw_digest,
                published_at=event['published_at'],observed_at=event['collected_at'],collected_at=event['collected_at'],
                source_uncertainty=list(event.get('source_uncertainty',event.get('uncertainty',[]))),
                recovery_note='Full body recovered offline and hash matched; company statement is not independent confirmation.')
            total+=len(body);counts[sid]=counts.get(sid,0)+1
            row.update(status='ADMITTED_FULL_TEXT',source_id=source_id,characters=len(body),security_id=sid)
        except (ValueError,KeyError,TypeError,OSError) as error:
            row['reason']=str(error)[:160]
        coverage.append(row)
    for ticker,sids in mapping.items():
        for sid in sorted(sids):
            coverage.append(dict(security_id=sid,ticker=ticker,status='POSITION_COVERAGE',admitted_full_text_count=counts.get(sid,0)))
    payload=dict(sources=sources,coverage=coverage)
    payload['fingerprint']=sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return payload

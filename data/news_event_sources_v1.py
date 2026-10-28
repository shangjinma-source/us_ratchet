"""Fixed issuer endpoints: two list requests, then at most two new bodies."""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit
import requests

from data.news_issuer_source import API, candidate_headlines, parse_issuer_story
from data.news_sandisk_capture import LIST_URL
from data.news_sandisk_parser import official, parse_release


def moment(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('PUBLICATION_TIME_ZONE_REQUIRED')
    return result


class EventSources:
    supported = frozenset(('MRNA', 'SNDK'))

    def __init__(self, cache, *, session=None, clock=None):
        self.cache = Path(cache)
        self.session = session or requests
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.started = monotonic()
        self.request_count = 0
        self.receipts = []

    def fetch(self, url, *, params=None, ticker):
        allowed = (ticker == 'MRNA' and url in (API+'getHeadlines.json', API+'getStory.json')) or (
            ticker == 'SNDK' and (url == LIST_URL or (official(url) and '/press-releases/' in urlsplit(url).path)))
        if not allowed or self.request_count >= 4 or monotonic()-self.started >= 55:
            raise ValueError('EVENT_SOURCE_REQUEST_BUDGET_OR_DOMAIN')
        self.request_count += 1
        requested = self.clock().isoformat()
        with self.session.get(url, params=params, timeout=(5, 15), stream=True, allow_redirects=False) as response:
            payload = bytearray()
            for block in response.iter_content(16384):
                payload.extend(block)
                if len(payload) > 2_000_000 or monotonic()-self.started >= 55:
                    raise ValueError('EVENT_SOURCE_RESPONSE_BUDGET')
            raw = bytes(payload)
            digest = sha256(raw).hexdigest()
            directory = self.cache/'raw'
            directory.mkdir(parents=True, exist_ok=True)
            filename = ('issuer-'+digest+'.json') if ticker == 'MRNA' else ('sandisk-'+digest+'.raw')
            (directory/filename).write_bytes(raw)
            receipt = dict(source=ticker, url=url, params=params or {}, status=response.status_code,
                           requested_at=requested, fetched_at=self.clock().isoformat(), sha256=digest, bytes=len(raw))
            self.receipts.append(receipt)
            if response.status_code != 200:
                raise ValueError('EVENT_SOURCE_HTTP_FAILURE')
        return raw, receipt

    def discover(self, ticker):
        now = self.clock()
        if ticker == 'MRNA':
            params = dict(topics='MRNA', noSrc='qmr', src='pzo,bayaw,prn,bwi,TheNewsWire,nfil,actw,irw,acn,cnw,nwd,glpr,nwmw',
                          thumbnailurl='true', summary='true', summLen=300,
                          start=(now-timedelta(days=90)).date().isoformat(), end=now.date().isoformat())
            raw, receipt = self.fetch(API+'getHeadlines.json', params=params, ticker=ticker)
            rows = candidate_headlines(json.loads(raw))
            result = [dict(ticker=ticker, url=row['storyurl'], title=row['headline'], published_at=row['datetime'],
                           original=row, discovered_at=receipt['fetched_at']) for row in rows]
        elif ticker == 'SNDK':
            raw, receipt = self.fetch(LIST_URL, ticker=ticker)
            rows = json.loads(raw).get('docs')
            if not isinstance(rows, list) or len(rows) > 5:
                raise ValueError('SANDISK_LIST_SCHEMA')
            result = []
            for row in rows:
                if (row.get('documentType') != ['Press Release'] or not official(row.get('url', '')) or
                        '/press-releases/' not in urlsplit(row['url']).path or
                        not isinstance(row.get('title'), list) or len(row['title']) != 1):
                    raise ValueError('SANDISK_LIST_IDENTITY')
                result.append(dict(ticker=ticker, url=row['url'], title=row['title'][0],
                                   published_at=row['documentTypeDate'], original=row, discovered_at=receipt['fetched_at']))
        else:
            raise ValueError('UNSUPPORTED_ISSUER_SOURCE')
        for row in result:
            if moment(row['published_at']) > moment(row['discovered_at']):
                raise ValueError('FUTURE_LIST_PUBLICATION')
        return result

    def hydrate(self, row):
        ticker = row['ticker']
        if ticker == 'MRNA':
            raw, receipt = self.fetch(API+'getStory.json', ticker=ticker,
                                      params=dict(storyId=str(row['original']['newsid']), newslang='en'))
            event = parse_issuer_story(row['original'], json.loads(raw), receipt['fetched_at'])
        else:
            raw, receipt = self.fetch(row['url'], ticker=ticker)
            event = parse_release(raw, row['url'], receipt['fetched_at'])['event']
            if event['title'] != row['title']:
                raise ValueError('SANDISK_LIST_TITLE_MISMATCH')
            event['listing_published_raw'] = row['published_at']
            if moment(event['published_at']) != moment(row['published_at']):
                raise ValueError('TIMELY_TRIGGER_PUBLICATION_CONFLICT')
        if event['tickers'] != [ticker] or event['url'] != row['url']:
            raise ValueError('EVENT_IDENTITY_MISMATCH')
        event['discovered_at'] = row['discovered_at']
        return event

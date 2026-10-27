"""Bounded official endpoint observed in newsroom browser traffic. Candidate only."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
import requests
from data.news_sandisk_parser import parse_release, official

LIST_URL = ('https://www.sandisk.com/tools/api/globalsearchquery?q=*&locale=en-us'
            '&fl=title,url,description,primaryImage,documentType,documentTypeDate'
            '&fq=documentType:Press%20Release&from=0&rows=5&sort=documentTypeDate')


def capture(cache, *, session=None):
    session = session or requests
    directory = Path(cache) / 'raw'
    directory.mkdir(parents=True, exist_ok=True)
    receipts, errors, events = [], [], []
    started = time.monotonic()
    attempts = 0

    def fetch(url):
        nonlocal attempts
        if attempts >= 3 or time.monotonic() - started > 55:
            raise ValueError('SANDISK_CAPTURE_BUDGET')
        if url != LIST_URL and not (official(url) and '/press-releases/' in urlsplit(url).path):
            raise ValueError('SANDISK_URL_REJECTED')
        attempts += 1
        requested = datetime.now(timezone.utc).isoformat()
        with session.get(url, timeout=(5, 15), allow_redirects=False, stream=True) as response:
            raw = bytearray()
            for block in response.iter_content(16384):
                raw.extend(block)
                if len(raw) > 2_000_000 or time.monotonic() - started > 55:
                    raise ValueError('SANDISK_RESPONSE_BUDGET')
            payload = bytes(raw)
            digest = sha256(payload).hexdigest()
            (directory / ('sandisk-' + digest + '.raw')).write_bytes(payload)
            receipt = dict(source='Sandisk 官方新闻室', url=url, requested_at=requested,
                           fetched_at=datetime.now(timezone.utc).isoformat(),
                           status=response.status_code, sha256=digest, bytes=len(payload))
            receipts.append(receipt)
            if response.status_code != 200:
                raise ValueError('SANDISK_HTTP_' + str(response.status_code))
        return payload, receipt

    try:
        payload, _ = fetch(LIST_URL)
        document = json.loads(payload)
        if not isinstance(document.get('docs'), list) or len(document['docs']) > 5:
            raise ValueError('SANDISK_LIST_SCHEMA')
        candidates = []
        for row in document['docs']:
            url = row.get('url', '')
            if row.get('documentType') != ['Press Release'] or not official(url) or '/press-releases/' not in urlsplit(url).path:
                raise ValueError('SANDISK_LIST_IDENTITY')
            stamp = datetime.fromisoformat(row['documentTypeDate'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if stamp.utcoffset() is None or stamp > now:
                raise ValueError('SANDISK_LIST_DATE')
            if (now-stamp).days <= 90 and url not in [r['url'] for r in candidates]:
                candidates.append(row)
        for row in sorted(candidates, key=lambda r: r['documentTypeDate'], reverse=True)[:2]:
            try:
                payload, receipt = fetch(row['url'])
                event = parse_release(payload, row['url'], receipt['fetched_at'])['event']
                if row.get('title') != [event['title']]:
                    raise ValueError('SANDISK_LIST_TITLE_MISMATCH')
                event['summary'] = event['source_text'][:1200]
                event['listing_published_raw'] = row['documentTypeDate']
                if datetime.fromisoformat(row['documentTypeDate'].replace('Z', '+00:00')) != datetime.fromisoformat(event['published_at']):
                    event['uncertainty'].append('列表时间与正文发布时间不同；均保留，不据此回填历史交易。')
                events.append(event)
            except Exception as error:
                errors.append(dict(source='Sandisk 官方新闻室', url=row['url'], error_type=type(error).__name__, message=str(error)[:160]))
    except Exception as error:
        errors.append(dict(source='Sandisk 官方新闻室', url=LIST_URL, error_type=type(error).__name__, message=str(error)[:160]))
    return dict(events=events, receipts=receipts, errors=errors, request_count=attempts,
                coverage='Latest two of at most five official list entries; not complete company news.')

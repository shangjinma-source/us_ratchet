"""Offline Sandisk official newsroom parser candidate; requires beautifulsoup4.

No fetching. Caller must bind response bytes and final URL to a fetch receipt.
"""
from datetime import datetime
from hashlib import sha256
import re
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup


def official(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.netloc == 'www.sandisk.com'
            and not parsed.username and parsed.path.startswith('/company/newsroom'))


def parse_release(raw, url, collected_at):
    if not official(url) or '/press-releases/' not in urlsplit(url).path:
        raise ValueError('OFFICIAL_RELEASE_URL_REQUIRED')
    if len(raw) > 2_000_000:
        raise ValueError('HTML_TOO_LARGE')
    soup = BeautifulSoup(raw, 'html.parser')
    canonical = soup.select_one('link[rel="canonical"]')
    headings = soup.find_all('h1')
    if canonical is None or canonical.get('href') != url or len(headings) != 1:
        raise ValueError('ARTICLE_IDENTITY_MISMATCH')
    heading = headings[0]
    title = heading.get_text(' ', strip=True)
    container = heading.parent
    body_node = container.select_one('.para-text')
    date_node = heading.find_next_sibling('p')
    meta = soup.find('meta', attrs={'name': 'article:published_time'})
    if body_node is None or date_node is None or meta is None or not title:
        raise ValueError('ARTICLE_STRUCTURE_MISSING')
    body = body_node.get_text(' ', strip=True)
    if len(body) < 100 or not re.search(r'NASDAQ\s*:\s*SNDK\b', body):
        raise ValueError('ISSUER_BODY_MISSING')
    stamp = meta.get('content', '')
    published = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    fetched = datetime.fromisoformat(collected_at.replace('Z', '+00:00'))
    if published.utcoffset() is None or fetched.utcoffset() is None or published > fetched:
        raise ValueError('PUBLICATION_TIME_INVALID')
    dateline = re.sub(r'\s+', ' ', date_node.get_text(' ', strip=True))
    date_match = re.search(r'([A-Za-z]+ \d{1,2}, \d{4})', dateline)
    if date_match is None or datetime.strptime(date_match.group(1), '%B %d, %Y').date() != published.date():
        raise ValueError('DATELINE_MISMATCH')
    links = []
    for anchor in soup.find_all('a', href=True):
        target = urljoin(url, anchor['href'])
        if official(target) and not urlsplit(target).fragment and target not in links:
            links.append(target)
    warnings = ['公司官方发布；未经独立来源证实。']
    if len(body) > 6000:
        warnings.append('正文超过6000字符，展示文本截断；原始HTML另存。')
    event = dict(id=sha256(url.encode()).hexdigest()[:24], title=title, url=url,
                 source='Sandisk 官方新闻室', source_type='official', tickers=['SNDK'],
                 relevance='company', published_at=published.isoformat(), published_raw=stamp,
                 collected_at=collected_at, content_kind='OFFICIAL_RELEASE_BODY',
                 source_text=body[:6000], content_sha256=sha256(body.encode()).hexdigest(),
                 raw_html_sha256=sha256(raw).hexdigest(), evidence=[url],
                 uncertainty=warnings, analysis_status='NOT_ANALYZED', model=None)
    return dict(event=event, observed_newsroom_links=links)

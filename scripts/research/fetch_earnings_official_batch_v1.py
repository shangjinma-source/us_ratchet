"""One bounded official-source acquisition batch; missing URLs are retained."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT/'tmp/earnings_official_bounded_batch_20261027'
NVIDIA = {
    '0001045810-22-000008': 'fourth-quarter-and-fiscal-2022',
    '0001045810-23-000171': 'second-quarter-fiscal-2024',
    '0001045810-23-000225': 'third-quarter-fiscal-2024',
    '0001045810-24-000028': 'fourth-quarter-and-fiscal-2024',
    '0001045810-24-000113': 'first-quarter-fiscal-2025',
    '0001045810-24-000262': 'second-quarter-fiscal-2025',
    '0001045810-24-000315': 'third-quarter-fiscal-2025',
}
APP = {
    '0001751008-25-000006': 'Fourth-Quarter-and-Full-Year-2024',
    '0001751008-25-000069': 'Second-Quarter-2025',
    '0001751008-25-000079': 'Third-Quarter-2025',
}
URLS = {accession:'https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-'+suffix
        for accession,suffix in NVIDIA.items()}
URLS.update({accession:'https://investors.applovin.com/news/news-details/2025/AppLovin-Announces-'+suffix+'-Financial-Results/default.aspx'
             for accession,suffix in APP.items()})
URLS.update({
    '0001091667-21-000082':'https://ir.charter.com/news-releases/news-release-details/charter-announces-first-quarter-2021-results/',
    '0001091667-23-000141':'https://ir.charter.com/news-releases/news-release-details/charter-announces-third-quarter-2023-results/',
})


def main():
    if OUTPUT.exists():
        raise ValueError('BATCH_ALREADY_EXISTS_NO_AUTOMATIC_RETRY')
    raw = (ROOT/'tmp/held_disclosure_inventory_20261027/earnings_queue.json').read_bytes()
    queue = json.loads(raw)
    rows = [row for window in queue['windows'] for row in window['queue'][2:]]
    if len(rows) != 35 or len(URLS) > 35 or not set(URLS) <= {row['accession'] for row in rows}:
        raise ValueError('FROZEN_BATCH_SCOPE_MISMATCH')
    OUTPUT.mkdir()
    registration = dict(queue_sha256=sha256(raw).hexdigest(), rows=rows, urls=URLS,
        source_queries_used=12, source_query_limit=12, request_limit=35,
        actual_request_plan=len(URLS), timeout_seconds=15, retries=0,
        note='Some NVIDIA/Charter slugs are pattern-derived candidates; HTTP success alone is not document identity.')
    (OUTPUT/'registration.json').write_text(json.dumps(registration,indent=2),encoding='utf-8')
    def fetch(row):
        accession = row['accession']
        if accession not in URLS:
            return dict(accession=accession,tickers=row['tickers'],status='URL_NOT_LOCATED_WITHIN_QUERY_BUDGET')
        result = dict(accession=accession,tickers=row['tickers'],url=URLS[accession],
                      started_at=datetime.now(timezone.utc).isoformat())
        try:
            response = requests.get(URLS[accession],timeout=15,allow_redirects=False)
            content = response.content
            path = OUTPUT/(accession+'.response.bin')
            path.write_bytes(content)
            soup = BeautifulSoup(content,'html.parser')
            text = soup.get_text(' ',strip=True)
            result.update(status=response.status_code,bytes=len(content),path=str(path.relative_to(ROOT)),
                sha256=sha256(content).hexdigest(),title=soup.title.get_text(' ',strip=True) if soup.title else '',
                contains_financial_results='financial results' in text.lower(),table_count=len(soup.find_all('table')),
                identity_review='PENDING_NOT_A_TRADING_EVENT')
            (OUTPUT/(accession+'.text.txt')).write_text(text,encoding='utf-8')
        except requests.RequestException as error:
            result.update(status='REQUEST_FAILED',error=type(error).__name__)
        (OUTPUT/(accession+'.receipt.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch,rows))
    report = dict(status='BATCH_TERMINAL',requests=len(URLS),queries=12,rows=results,
        http200=sum(row['status']==200 for row in results),
        unresolved_urls=sum(row['status']=='URL_NOT_LOCATED_WITHIN_QUERY_BUDGET' for row in results),
        production_changed=False,model_calls=0,admitted_events=0)
    (OUTPUT/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='rows'}))
    print(json.dumps([(row['tickers'],row['status'],row.get('title'),row.get('table_count')) for row in results if row['accession'] in URLS]))


if __name__ == '__main__':
    main()

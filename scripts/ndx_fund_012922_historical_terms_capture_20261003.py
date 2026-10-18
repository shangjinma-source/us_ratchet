"""Save dated public fund disclosures; capture only, no historical certification."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/cache/research/fund_012922_historical_terms_20261003_v1'
PROSPECTUS = 'https://cdn.efunds.com.cn/owch/data/bulletin/20250801/' + quote('易方达全球成长精选混合型证券投资基金（QDII）更新的招募说明书.pdf') + '?from=org'
SOURCES = (
    ('prospectus_20250801', PROSPECTUS),
    ('product_summary_20250728', 'https://static.cninfo.com.cn/finalpage/2025-07-28/1224312455.PDF'),
)


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    source_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    save(OUTPUT / 'started.json', dict(started_at=now(), source_sha256=source_sha, requested_sources=SOURCES))
    rows = []
    try:
        for name, url in SOURCES:
            start = now()
            with urlopen(Request(url, headers={'User-Agent': 'us-ratchet-research/1.0', 'Accept-Encoding': 'identity'}), timeout=30) as response:
                raw = response.read(32 * 1024 * 1024 + 1)
                status, final_url = response.status, response.geturl()
                content_type = response.headers.get('Content-Type')
            finish = now()
            path = OUTPUT / (name + '.pdf')
            with path.open('xb') as stream:
                stream.write(raw)
            reference = dict(path=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(raw).hexdigest())
            receipt = dict(requested_url=url, final_url=final_url, http_status=status, content_type=content_type,
                           read_started_at=start, read_completed_at=finish, bytes=len(raw), raw_reference=reference)
            receipt_path = OUTPUT / (name + '.receipt.json')
            save(receipt_path, receipt)
            if status != 200 or final_url != url or not raw.startswith(b'%PDF-') or len(raw) > 32 * 1024 * 1024:
                raise ValueError('Unexpected source response: ' + name)
            rows.append(dict(name=name, raw_reference=reference, receipt_reference=dict(
                path=receipt_path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest())))
        if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != source_sha:
            raise ValueError('Capture source changed')
        save(OUTPUT / 'manifest.json', dict(schema='FUND_HISTORICAL_DISCLOSURE_CAPTURE_V1', completed_at=now(),
             source_sha256=source_sha, documents=rows, content_extracted=False, historical_currency_interval_verified=False,
             actual_nav_publication_times_verified=False, subscription_calendar_verified=False,
             benchmark_qualified=False, point_in_time_verified=False, execution_authorized=False, promotion_allowed=False))
        print(json.dumps(dict(path=str(OUTPUT / 'manifest.json'), sha256=hashlib.sha256((OUTPUT / 'manifest.json').read_bytes()).hexdigest())))
    except Exception as error:
        save(OUTPUT / 'failure.json', dict(failed_at=now(), error_type=type(error).__name__, error=str(error), retry_allowed=False))
        raise


if __name__ == '__main__':
    main()

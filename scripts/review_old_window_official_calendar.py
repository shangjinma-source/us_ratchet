"""Independent holiday reconstruction for the old-window source coverage audit."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta, datetime, timezone
from hashlib import sha256
import gzip
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'tmp/old_window_official_calendar_20261026'
SOURCES = {
    'nyse_2024_2026.pdf': 'https://s2.q4cdn.com/154085107/files/doc_news/NYSE-Group-Announces-2024-2025-and-2026-Holiday-and-Early-Closings-Calendar-2023.pdf',
    'nasdaq_carter_closure.html': 'https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2024-87',
}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / 'review.json').exists():
        raise ValueError('COMPLETED_REVIEW_ALREADY_EXISTS')
    def fetch(item):
        name, url = item
        saved = OUTPUT / name
        if saved.exists():
            raw = saved.read_bytes()
            if name.endswith('.pdf') and not raw.startswith(b'%PDF'):
                raise ValueError('EXPECTED_PDF')
            return dict(file=str(saved.relative_to(ROOT)), url=url,
                        retrieval='REUSED_LOCAL_RESPONSE', sha256=sha256(raw).hexdigest())
        response = requests.get(url, timeout=25)
        response.raise_for_status()
        if name.endswith('.pdf') and not response.content.startswith(b'%PDF'):
            raise ValueError('EXPECTED_PDF')
        (OUTPUT / name).write_bytes(response.content)
        return dict(file=str((OUTPUT / name).relative_to(ROOT)), url=url,
                    status=response.status_code, sha256=sha256(response.content).hexdigest())
    with ThreadPoolExecutor(max_workers=2) as pool:
        retrieved = list(pool.map(fetch, SOURCES.items()))
    prior_path = ROOT / 'tmp/independent_calendar_review_20261026/calendar_review.json'
    prior = json.loads(prior_path.read_bytes())
    # Manually transcribed by year from the official release's three columns.
    holidays = set(prior['full_holidays']) | set('''
2024-01-01 2024-01-15 2024-02-19 2024-03-29 2024-05-27
2024-06-19 2024-07-04 2024-09-02 2024-11-28 2024-12-25
2025-01-01 2025-01-20 2025-02-17 2025-04-18 2025-05-26
2025-06-19 2025-07-04 2025-09-01 2025-11-27 2025-12-25
2026-01-01 2026-01-19 2026-02-16 2026-04-03 2026-05-25
2026-06-19 2026-07-03 2026-09-07 2026-11-26 2026-12-25
2025-01-09'''.split())
    start, end = date(2022,12,28), date(2026,7,30)
    expected = []
    day = start
    while day <= end:
        if day.weekday() < 5 and day.isoformat() not in holidays:
            expected.append(day.isoformat())
        day += timedelta(days=1)
    reference_path = ROOT / 'data/cache/research/current_raw_capture_20261014_v1/AAPL.response.bin'
    raw = reference_path.read_bytes()
    if raw.startswith(b'\x1f\x8b'):
        raw = gzip.decompress(raw)
    source = json.loads(raw)['chart']['result'][0]
    observed = sorted(datetime.fromtimestamp(t, timezone.utc).date().isoformat()
                      for t in source['timestamp']
                      if start.isoformat() <= datetime.fromtimestamp(t, timezone.utc).date().isoformat() <= end.isoformat())
    result = dict(status='OFFICIAL_CALENDAR_DATE_COMPARISON', start=str(start), end=str(end),
                  official_sessions=expected, official_count=len(expected), reference_count=len(observed),
                  missing_in_reference=sorted(set(expected)-set(observed)),
                  unexpected_in_reference=sorted(set(observed)-set(expected)),
                  duplicate_reference_dates=len(observed)-len(set(observed)), full_holidays=sorted(holidays),
                  sources=retrieved, special_closure='2025-01-09',
                  early_closes_retained=['2024-07-03','2024-11-29','2024-12-24','2025-07-03','2025-11-28','2025-12-24'],
                  source_hashes={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest()
                                 for p in (prior_path, reference_path, *(OUTPUT / name for name in SOURCES))},
                  limitation='Declared exchange holidays plus explicitly sourced Carter closure; not an exhaustive archive of every unscheduled exchange notice.')
    (OUTPUT / 'review.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('official_count','reference_count','missing_in_reference','unexpected_in_reference','duplicate_reference_dates')}))


if __name__ == '__main__':
    main()

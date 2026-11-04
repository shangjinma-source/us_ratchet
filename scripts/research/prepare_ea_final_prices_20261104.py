"""Prepare three observed EA bars; keep original baseline immutable."""
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]


def run():
    folder = ROOT / 'tmp/ea_final_prices_20261104'
    receipt = json.loads((folder / 'receipt.json').read_bytes())
    source = next(row for row in receipt if row['name'] == 'chartexchange')
    raw = (folder / 'chartexchange.html').read_bytes()
    assert source['http_status'] == 200 and sha256(raw).hexdigest() == source['sha256']
    soup = BeautifulSoup(raw, 'html.parser')
    rows = {}
    for element in soup.find_all('tr'):
        cells = [cell.get_text(' ', strip=True) for cell in element.find_all(['th', 'td'])]
        if not cells or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', cells[0]):
            continue
        assert len(cells) >= 5 and cells[0] not in rows
        values = dict(zip(('open', 'high', 'low', 'close'), map(Fraction, cells[1:5])))
        assert 0 < values['low'] <= min(values['open'], values['close'])
        assert values['high'] >= max(values['open'], values['close'])
        rows[cells[0]] = values
    baseline_path = ROOT / 'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json'
    baseline = json.loads(baseline_path.read_bytes())
    sid = 'security:0000712515:285512109'
    original = baseline['ohlc'][sid]
    overlap = sorted(rows.keys() & original.keys())
    assert overlap and '2026-07-30' in overlap
    differences = [day for day in overlap if any(rows[day][key] != Fraction(original[day][key])
                                                for key in ('open', 'high', 'low', 'close'))]
    requested = ['2026-07-31', '2026-08-03', '2026-08-04']
    assert all(day in rows for day in requested)
    assert not any(day > '2026-08-04' for day in rows)
    result = dict(status='CANDIDATE_PRICE_OVERLAP_PASS' if not differences else 'BLOCKED_PRICE_OVERLAP',
                  security_id=sid, overlap_count=len(overlap), overlap_first=overlap[0],
                  overlap_last=overlap[-1], differing_dates=differences,
                  rows={day:{key:str(value) for key,value in rows[day].items()} for day in requested},
                  source_url=source['url'], source_sha256=source['sha256'],
                  baseline_sha256=sha256(baseline_path.read_bytes()).hexdigest(),
                  scope='Modern provider OHLC only; not independent market-data verification, '
                        'membership certification or merger-cash settlement admission.',
                  baseline_modified=False, production_changed=False)
    (folder / 'candidate.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()

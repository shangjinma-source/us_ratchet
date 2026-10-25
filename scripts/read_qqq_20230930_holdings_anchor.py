"""Extract a pinned SEC QQQ holding snapshot, not a certified index roster."""
from hashlib import sha256
import json
from pathlib import Path
import re
from bs4 import BeautifulSoup


def read_anchor(root):
    folder = Path(root)/'data/cache/candidate_pools/qqq_20230930_annual_20261024'
    raw = (folder/'annual.html').read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != '6e8d2ee750eccb73b3c8e766f66ec067b0c72f5257e4a0705dd49a38fdeb8876':
        raise ValueError('ANNUAL_SOURCE_CHANGED')
    soup = BeautifulSoup(raw, 'html.parser')
    tables = soup.find_all('table')
    holdings = []
    for index in (5, 6, 8, 9):
        table = tables[index]
        if not all(word in table.get_text() for word in ('Shares', 'Value')):
            raise ValueError('HOLDINGS_TABLE_CHANGED')
        for row in table.find_all('tr'):
            cells = [cell.get_text(' ', strip=True) for cell in row.find_all('td', recursive=False)]
            if len(cells) != 9 or not cells[0]:
                continue
            if not re.fullmatch(r'[0-9,]+', cells[3]) or not re.fullmatch(r'[0-9,]+', cells[7]):
                continue
            holdings.append(dict(name=cells[0], shares=int(cells[3].replace(',', '')),
                value_usd=int(cells[7].replace(',', '')), source_table_index=index))
    total = sum(row['value_usd'] for row in holdings)
    if len({row['name'] for row in holdings}) != len(holdings) or total != 196527434884:
        raise ValueError('HOLDINGS_TOTAL_OR_DUPLICATES')
    index_raw = (folder/'filing-index.html').read_bytes()
    if sha256(index_raw).hexdigest() != 'd9d1e10cd756ea702ccfbdb70a2017d3c11aa4d20b428e0a4515b32218a66271':
        raise ValueError('FILING_INDEX_CHANGED')
    index = BeautifulSoup(index_raw, 'html.parser')
    text = index.get_text(' ', strip=True)
    if ('Filing Date 2023-12-28 Accepted 2023-12-28 11:16:55' not in text
            or 'Period of Report 2023-09-30' not in text
            or not any(link.get('href','').endswith('/d538532dn30b2.htm') for link in index.find_all('a'))):
        raise ValueError('FILING_DATE_OR_DOCUMENT_BINDING')
    return dict(status='FUND_HOLDINGS_ANCHOR_EXTRACTED', source_sha256=digest,
        report_date='2023-09-30', source_url=json.loads((folder/'capture.json').read_bytes())['url'],
        security_count=len(holdings), total_security_value_usd=total, holdings=holdings,
        exact_index_membership_certified=False, publication_timestamp_verified=True,
        filing_date='2023-12-28', sec_accepted_timestamp_as_displayed='2023-12-28 11:16:55',
        conservative_available_date='2023-12-29', filing_index_sha256=sha256(index_raw).hexdigest(),
        index_event_completeness_verified=False, production_pool_changed=False,
        limitation='Fund portfolio snapshot only; identities and subsequent index events require verification. Availability is conservatively the day after filing, not the holdings report date.')


if __name__ == '__main__':
    print(json.dumps(read_anchor(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))

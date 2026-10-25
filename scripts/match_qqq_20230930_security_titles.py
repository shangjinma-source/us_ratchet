"""Match security titles across two SEC filings without dropping share classes."""
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree
import csv
import json
import re
from bs4 import BeautifulSoup
from scripts.read_qqq_20230930_holdings_anchor import read_anchor


def normalized_title(name):
    # Parentheses contain report footnotes/countries, never share-class suffixes.
    return re.sub(r'[^a-z0-9]', '', re.sub(r'\([^)]*\)', '', name).casefold())


def match(root):
    root = Path(root)
    anchor = read_anchor(root)
    folder = root/'data/cache/candidate_pools/qqq_20230930_annual_20261024'
    raw = (folder/'nport.xml').read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != '5a9d80e6fcd288e79822440b3a0136c49216d767c3a2ae8b3598f8772edfb613':
        raise ValueError('NPORT_SOURCE_CHANGED')
    document = ElementTree.fromstring(raw)
    for node in document.iter():
        node.tag = node.tag.split('}')[-1]
    securities = document.findall('.//invstOrSec')
    registry_path = root/'data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv'
    registry_raw = registry_path.read_bytes()
    manifest = json.loads(registry_path.with_suffix('.csv.manifest.json').read_bytes())
    if sha256(registry_raw).hexdigest() != manifest['content_sha256']:
        raise ValueError('REGISTRY_CHANGED')
    registry = [row for row in csv.DictReader(registry_raw.decode('utf-8-sig').splitlines())
                if row['report_date'] == anchor['report_date']]
    # ORLY's own contemporaneous filing supplies its symbol directly. Do not
    # infer its CUSIP or erase the conflicting Class R label in the fund filing.
    issuer_raw = (folder/'orly-20230930-10q.html').read_bytes()
    index_raw = (folder/'orly-filing-index.html').read_bytes()
    if sha256(issuer_raw).hexdigest() != '27e7415c0960332748c9e7d7464d140ed480e1d541f3b720caf7818fef839131':
        raise ValueError('ORLY_ISSUER_SOURCE_CHANGED')
    if sha256(index_raw).hexdigest() != '1ac2f3a5149bf40b95014d09b21d8bcc0b49b6681af37aaf494a9dbb9de42149':
        raise ValueError('ORLY_FILING_INDEX_CHANGED')
    issuer = BeautifulSoup(issuer_raw, 'html.parser')
    facts = lambda name: {node.get_text(' ', strip=True) for node in issuer.find_all(attrs={'name': name})}
    if (facts('dei:TradingSymbol') != {'ORLY'} or
            facts('dei:Security12bTitle') != {'Common Stock,'} or
            facts('dei:SecurityExchangeName') != {'Nasdaq'} or
            facts('dei:EntityRegistrantName') != {'O Reilly Automotive Inc'}):
        raise ValueError('ORLY_LISTED_SECURITY_AMBIGUOUS')
    index_text = BeautifulSoup(index_raw, 'html.parser').get_text(' ', strip=True)
    if 'Filing Date 2023-11-08' not in index_text or 'Period of Report 2023-09-30' not in index_text:
        raise ValueError('ORLY_PUBLICATION_UNCONFIRMED')
    rows = []
    for holding in anchor['holdings']:
        matches = [item for item in securities if normalized_title(holding['name']) ==
                   normalized_title(item.findtext('title', ''))]
        row = dict(annual_name=holding['name'], status='UNRESOLVED_SECURITY_TITLE')
        if len(matches) == 1:
            item = matches[0]
            cusip = item.findtext('cusip')
            tickers = [entry['ticker'] for entry in registry if entry['cusip'] == cusip]
            if len(tickers) != 1:
                raise ValueError('AMBIGUOUS_CUSIP_REGISTRY')
            row.update(status='EXACT_NORMALIZED_SECURITY_TITLE_MATCH', cusip=cusip,
                nport_title=item.findtext('title'), local_registry_ticker=tickers[0],
                ticker_source='EXISTING_LOCAL_CUSIP_REGISTRY_NOT_NEW_PIT_TICKER_PROOF')
        elif normalized_title(holding['name']) == normalized_title('O Reilly Automotive Inc'):
            row.update(status='ISSUER_FILING_SINGLE_LISTED_COMMON_STOCK',
                local_registry_ticker='ORLY',
                ticker_source='SEC_ISSUER_10Q_2023_11_08_DIRECT_SYMBOL',
                issuer_source_sha256=sha256(issuer_raw).hexdigest(),
                issuer_index_sha256=sha256(index_raw).hexdigest(),
                conservative_symbol_available_date='2023-11-09',
                cusip_status='NOT_ASSIGNED_CLASS_R_DISCREPANCY_RETAINED')
        rows.append(row)
    resolved = [row for row in rows if 'cusip' in row]
    if len({row['cusip'] for row in resolved}) != len(resolved):
        raise ValueError('DUPLICATE_SECURITY_MATCH')
    return dict(status='CROSS_FILING_SECURITY_TITLE_CHECK', source_sha256=anchor['source_sha256'],
        nport_sha256=digest, registry_sha256=sha256(registry_raw).hexdigest(),
        report_date=anchor['report_date'], conservative_available_date=anchor['conservative_available_date'],
        matched=len(resolved), issuer_symbol_corrobated=sum(row['status'] ==
            'ISSUER_FILING_SINGLE_LISTED_COMMON_STOCK' for row in rows),
        unresolved=sum('local_registry_ticker' not in row for row in rows), rows=rows,
        index_membership_certified=False, production_pool_changed=False)


if __name__ == '__main__':
    print(json.dumps(match(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))

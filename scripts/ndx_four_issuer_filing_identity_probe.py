"""Create-only official filing cover evidence; no interval or execution certification."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.ndx_identity_raw_fact_research import extract_bound_probe, verify

DEST = ROOT / 'data/cache/research/four_issuer_filing_identity_20260912_v1'
URLS = {
    'AMAT_2023': 'https://www.sec.gov/Archives/edgar/data/6951/000000695123000041/amat-20231029.htm',
    'AVGO_2023': 'https://www.sec.gov/Archives/edgar/data/1730168/000173016823000096/avgo-20231029.htm',
    'CDNS_2023': 'https://www.sec.gov/Archives/edgar/data/813672/000081367224000034/cdns-20231231.htm',
}
ISSUERS = {'AMAT': '0000006951', 'AVGO': '0001730168', 'CDNS': '0000813672', 'GOOG': '0001652044'}
CUSIPS = {'AMAT': '038222105', 'AVGO': '11135F101', 'CDNS': '127387108', 'GOOG': '02079K107'}
FIELDS = {'EntityCentralIndexKey', 'EntityRegistrantName', 'TradingSymbol', 'Security12bTitle', 'DocumentPeriodEndDate'}


def cover(body):
    soup = BeautifulSoup(body, 'html.parser')
    result = []
    for node in soup.find_all():
        name = node.get('name', '')
        if name.startswith('dei:') and name.split(':')[1] in FIELDS:
            result.append({'field': name, 'context': node.get('contextref'), 'value': node.get_text(' ', strip=True)})
        elif node.name.startswith('dei:') and node.name.split(':')[1].lower() in {x.lower() for x in FIELDS}:
            result.append({'field': node.name, 'context': node.get('contextref'), 'value': node.get_text(' ', strip=True)})
    return {'facts': result, 'contains_cusip_text': 'cusip' in soup.get_text().lower()}


def main():
    DEST.mkdir(exist_ok=False)
    sources = {str(Path(__file__).resolve()): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    documents = []
    for key, url in URLS.items():
        response = requests.get(url, headers={'User-Agent': 'us-ratchet public research'}, timeout=35)
        received = datetime.now(timezone.utc).isoformat()
        path = DEST / (key + '.response.bin')
        path.write_bytes(response.content)
        digest = hashlib.sha256(response.content).hexdigest()
        sources[str(path)] = digest
        item = {'key': key, 'source_url': url, 'final_url': response.url, 'http_status': response.status_code,
                'received_at_utc': received, 'path': str(path), 'sha256': digest, 'published_at_utc': None}
        if response.status_code == 200:
            item.update(cover(response.content))
        documents.append(item)
    paths = []
    base = ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2'
    for ticker, cik in ISSUERS.items():
        paths += [(ticker, p) for p in (base / 'raw_sec' / ('issuer_' + cik)).rglob('*.htm')]
    paths += [('GOOG', base / 'incumbent_overlay/raw_sec/filings/GOOG/000165204424000022_goog-20231231.htm')]
    for ticker, path in paths:
        manifest_path = Path(str(path) + '.manifest.json')
        metadata = json.loads(manifest_path.read_bytes())
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != metadata['content_sha256']:
            raise ValueError('Local filing binding changed')
        sources[str(path)] = metadata['content_sha256']
        sources[str(manifest_path)] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        documents.append({'key': ticker + '_LOCAL', 'path': str(path), 'sha256': sources[str(path)],
                          'manifest_claims_not_independent_receipt_proof': metadata, **cover(raw)})
    probe = extract_bound_probe(manifest_path=ROOT / 'data/cache/research/identity_public_source_probe_20260912_v1/manifest.json',
        expected_sha256='93de067b0e994adb0d2b6b1860cb9c3f36e2173c445f044db5f08bc14e20a3c2')
    sources.update(probe['source_hashes'])
    rows = []
    for ticker, cik in ISSUERS.items():
        matches = [d for d in documents if d['key'].startswith(ticker + '_')]
        rows.append({'ticker': ticker, 'local_security_id_claim': f'security:{cik}:{CUSIPS[ticker]}',
                     'issuer_cik_expected': cik, 'filing_cover_documents': [d['path'] for d in matches],
                     'historical_nport_cusip_fact': probe['nport']['holdings'][CUSIPS[ticker]],
                     'adjudication': 'DATED_FILING_CIK_TICKER_CLASS_FACTS_PLUS_SEPARATE_NPORT_NAME_CUSIP_FACT',
                     'cusip_to_issuer_cik_direct_field_binding_verified': False,
                     'continuous_identity_interval_verified': False,
                     'remaining_gap': 'NPORT has no security issuer CIK/ticker; cover has no direct CUSIP. Name join alone is insufficient for authenticated interval binding.'})
    result = {'schema': 'ndx_four_issuer_filing_identity_probe_v1', 'observed_at_utc': datetime.now(timezone.utc).isoformat(),
              'requested_interval': ['2023-03-31', '2024-06-03'], 'documents': documents, 'rows': rows,
              'nport_reporting_fund_is_not_security_issuer': True, 'nport_report_date': probe['nport'],
              'source_hashes': sources, 'source_authenticity_adjudicated': False, 'point_in_time_verified': False,
              'provider_price_binding_verified': False, 'execution_performed': False, 'promotion_allowed': False}
    verify(sources)
    path = DEST / 'report.json'
    with path.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write('\n')
    verify(sources)
    print(json.dumps({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'document_count': len(documents), 'fetch_statuses': [d['http_status'] for d in documents[:3]]}))


if __name__ == '__main__':
    main()

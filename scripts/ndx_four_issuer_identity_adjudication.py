"""Adjudicate dated four-security filing fields, without extending validity intervals."""
import hashlib
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_four_issuer_filing_identity_probe import cover, ISSUERS, CUSIPS

BASE = ROOT / 'data/cache/research/four_issuer_filing_identity_20260912_v1'


def main():
    sources = {}
    def bind(path):
        path = Path(path).resolve()
        body = path.read_bytes()
        sources[str(path)] = hashlib.sha256(body).hexdigest()
        return body
    bind(__file__)
    bind(ROOT / 'scripts/ndx_four_issuer_filing_identity_probe.py')
    previous = json.loads(bind(BASE / 'report.json'))
    for path, digest in previous['source_hashes'].items():
        if hashlib.sha256(bind(path)).hexdigest() != digest:
            raise ValueError('Prior source drift')
    rows = []
    for ticker, cik in ISSUERS.items():
        filename = ticker + ('_13G_2023' if ticker == 'AVGO' else '_13G') + '.response.bin'
        path = BASE / filename
        raw = bind(path)
        meta = json.loads(bind(str(path) + '.json'))
        if meta['status'] != 200 or meta['sha256'] != hashlib.sha256(raw).hexdigest():
            raise ValueError('Failed or changed response')
        text = raw.decode('utf-8')
        header, document = text.split('</SEC-HEADER>', 1)
        subject = header.split('SUBJECT COMPANY:', 1)[1].split('FILED BY:', 1)[0]
        reported = re.findall(r'CENTRAL INDEX KEY:\s*(\d+)', subject)
        if reported != [cik]:
            raise ValueError('Subject company CIK mismatch')
        doc = BeautifulSoup(document, 'html.parser').get_text(' ', strip=True)
        if CUSIPS[ticker] not in doc or 'Common Stock' not in doc:
            raise ValueError('Expected dated CUSIP/class missing')
        if ticker == 'GOOG' and 'Alphabet Inc. Class C' not in doc:
            raise ValueError('GOOG Class C not explicit')
        accepted = re.findall(r'<ACCEPTANCE-DATETIME>(\d{14})', header)
        filing = re.findall(r'FILED AS OF DATE:\s*(\d{8})', header)
        if len(accepted) != 1 or len(filing) != 1:
            raise ValueError('Ambiguous filing time')
        cover_path = (ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay/raw_sec/filings/GOOG/000165204424000022_goog-20231231.htm'
                      if ticker == 'GOOG' else BASE / (ticker + '_2023_retry.response.bin'))
        facts = cover(bind(cover_path))['facts']
        symbols = [f for f in facts if f['field'] == 'dei:TradingSymbol' and f['value'] == ticker]
        ciks = [f['value'] for f in facts if f['field'] == 'dei:EntityCentralIndexKey']
        if len(symbols) != 1 or ciks != [cik]:
            raise ValueError('Cover identity mismatch')
        titles = [f for f in facts if f['field'] == 'dei:Security12bTitle' and f['context'] == symbols[0]['context']]
        if len(titles) != 1:
            raise ValueError('Class-context join ambiguous')
        rows.append({'ticker': ticker, 'security_id': f'security:{cik}:{CUSIPS[ticker]}', 'issuer_cik': cik,
                     'cusip': CUSIPS[ticker], 'security_class_cover': titles[0]['value'],
                     'filing_cover_facts': facts, 'filing_cover_path': str(cover_path),
                     'cusip_subject_cik_primary_source': str(path), 'source_url': meta['url'],
                     'sec_acceptance_datetime_raw': accepted[0], 'sec_acceptance_timezone_not_encoded': True,
                     'sec_filed_as_of_date': filing[0], 'received_at_utc': meta['received_at_utc'],
                     'subject_company_header_distinguished_from_filed_by': True,
                     'dated_cusip_to_subject_cik_field_link_verified': True,
                     'dated_ticker_to_cik_and_class_cover_link_verified': True,
                     'cross_document_same_issuer_class_adjudication': 'MATCH',
                     'historical_full_interval_identity_verified': False,
                     'information_available_at_all_decisions_verified': False,
                     'price_provider_historical_security_binding_verified': False,
                     'limitations': 'Dated filings are evidence snapshots, not a proof of no intervening security changes. 2023 annual covers published after first decision cannot support earlier information availability.'})
    report = {'schema': 'ndx_four_issuer_dated_identity_adjudication_v1',
              'observed_at_utc': datetime.now(timezone.utc).isoformat(), 'rows': rows,
              'source_hashes': sources, 'point_in_time_verified': False, 'continuous_identity_interval_verified': False,
              'provider_price_binding_verified': False, 'execution_performed': False, 'promotion_allowed': False,
              'user_agent_note': 'New successful HTTP requests used a research contact placeholder, not an authenticated identity; transport success does not authenticate every source assertion.'}
    for path, digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Source drift')
    target = BASE / 'dated_identity_adjudication.json'
    with target.open('x', encoding='utf-8') as output:
        json.dump(report, output, indent=2, ensure_ascii=False, sort_keys=True)
        output.write('\n')
    print(json.dumps({'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'rows': len(rows)}))


if __name__ == '__main__':
    main()

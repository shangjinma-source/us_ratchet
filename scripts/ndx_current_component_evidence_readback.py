"""Read sealed current source evidence and capture one distinct official SPCX PDF."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_current_component_evidence_research import OUTPUT, BASE, capture


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    from bs4 import BeautifulSoup
    from pypdf import PdfReader
    manifest_path = OUTPUT / 'manifest.json'
    expected = '56baa4ec87aa7b09da5c07dbf4b934c40341c08e803137d306d6cec47f95be20'
    if digest(manifest_path) != expected:
        raise ValueError('Manifest differs')
    manifest = json.loads(manifest_path.read_bytes())
    sources = dict(manifest['source_hashes'])
    sources[str(manifest_path)] = expected
    sources[str(Path(__file__).resolve())] = digest(Path(__file__).resolve())
    captures = {row['name']: row for row in manifest['captures']}
    for row in captures.values():
        if row.get('raw_path'):
            sources[row['raw_path']] = row['raw_sha256']
    for path, expected_sha in sources.items():
        if digest(Path(path)) != expected_sha:
            raise ValueError('Source differs: ' + path)
    overview = BeautifulSoup(Path(captures['official_overview']['raw_path']).read_bytes(), 'html.parser').get_text(' ', strip=True)
    if '# of Components 102 Index Currency USD' not in overview:
        raise ValueError('Official overview component denominator not confirmed')
    method = PdfReader(captures['current_methodology']['raw_path'])
    pages = [' '.join(page.extract_text().split()) for page in method.pages]
    if ('A Fast Entry inclusion will not require the removal of another security' not in pages[2]
            or 'Multiple classes of securities issued by the same company are each eligible' not in pages[0]
            or 'Securities that are added to the Index as the result of a spin-off event are normally maintained' not in pages[8]):
        raise ValueError('Current methodology rule not confirmed')
    hona = BeautifulSoup(Path(captures['hona_completed_spinoff']['raw_path']).read_bytes(), 'html.parser').get_text(' ', strip=True)
    if not all(fragment in hona for fragment in ('June 29, 2026', 'has completed the previously announced spin-off', 'symbol "HONA," effective at the market opening today')):
        raise ValueError('HONA completed transaction not confirmed')
    # HTML transport timed out: this is its separately published PDF, not a repeated request.
    supplement = capture(('spcx_official_pdf', 'https://ir.nasdaq.com/node/110646/pdf'))
    pdf_verified = False
    if supplement.get('http_status') == 200 and supplement.get('raw_path'):
        sources[supplement['raw_path']] = supplement['raw_sha256']
        pdf_text = ' '.join(' '.join(page.extract_text().split()) for page in PdfReader(supplement['raw_path']).pages)
        pdf_verified = all(fragment in pdf_text for fragment in ('June 26, 2026', 'Space Exploration Technologies Corporation', '(Nasdaq: SPCX)', 'prior to market open on Tuesday, July 7, 2026'))
    observation = json.loads((BASE / 'observation.json').read_bytes())
    special = {row['symbol']: row['companyName'] for row in observation['rows'] if row['symbol'] in ('GOOG','GOOGL','HON','HONA','SPCX')}
    report = dict(schema='CURRENT_OFFICIAL_COMPONENT_CORROBORATION_NOT_HISTORICAL_PIT', source_hashes=sources,
                  original_captures=manifest['captures'], supplementary_capture=supplement,
                  verified_endpoint_count=102, independently_observed_official_overview_count=102,
                  endpoint_pagination_complete=True, special_current_labels=special,
                  current_quote_display_date=observation['provider_display_date'],
                  current_component_count_corroborated=True, issuer_denominator_independently_certified=False,
                  current_methodology_rules=dict(multiple_classes_separately_eligible=True, fast_entry_without_removal_allowed=True,
                                                spun_off_securities_may_remain=True, rule_pdf_pages_one_based=[1,3,9]),
                  spcx=dict(official_pdf_event_verified=pdf_verified, publication_date='2026-06-26',
                            effective_date='2026-07-07', effective_time='BEFORE_MARKET_OPEN',
                            issuer_label='Space Exploration Technologies Corporation', old_same_ticker_etf_history_join_prohibited=True),
                  hona=dict(completed_spinoff_date='2026-06-29', regular_way_first_date='2026-06-29', parent_ticker_continues='HON',
                            index_specific_effective_date_verified=False, current_endpoint_presence_verified=True,
                            inference='Spinoff retention is consistent with current rules, but specific NDX action notice was not located.'),
                  interpretation='102 is independently corroborated current securities count. Dual classes and non-replacement additions are permitted; exact count-change event chain has not been reconstructed.',
                  membership_effective_time_equals_quote_date=False, historical_backfill_allowed=False,
                  all_security_identity_resolved=False, complete_pit_membership_verified=False, promotion_allowed=False)
    for path, expected_sha in sources.items():
        if digest(Path(path)) != expected_sha:
            raise ValueError('Source changed before save')
    path = OUTPUT / 'readback.json'
    with path.open('xb') as stream:
        stream.write((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(dict(path=str(path), sha256=digest(path), spcx_pdf_status=supplement.get('http_status'), spcx_verified=pdf_verified)))


if __name__ == '__main__':
    main()

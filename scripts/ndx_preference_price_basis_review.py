"""Create-only bounded retrospective price-unit findings; not identity adjudication."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
FIRST = ROOT / 'data/cache/research/preference_price_action_source_probe_20260912_v1'
FULL = ROOT / 'data/cache/research/preference_price_action_supplement_20260912_v1'


def run():
    sources = {str(Path(__file__).resolve()): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def bind(path, digest):
        key = str(Path(path).resolve())
        if key in sources and sources[key] != digest:
            raise ValueError('Conflicting source')
        if hashlib.sha256(Path(key).read_bytes()).hexdigest() != digest:
            raise ValueError('Source drift: ' + key)
        sources[key] = digest
    def manifest(path, digest):
        bind(path, digest)
        result = json.loads(path.read_bytes())
        for source, expected in result['source_hashes'].items():
            bind(source, expected)
        for probe in result.get('probes', []):
            if probe['response_path'] is not None:
                bind(probe['response_path'], probe['response_sha256'])
        return result
    first = manifest(FIRST / 'manifest.json', 'fac4d6e47a266d69891a9415919d0a3cfbad639c0e3d7bc111a2a15ab30e32f7')
    full = manifest(FULL / 'manifest.json', 'ef8baa8d5d370b87f31543c770b09703c2b2750c2f19686e444582eea6a67e32')
    overlap = manifest(FIRST / 'archived_price_overlap_20260912.json', '69259a4ac878f146e7fd01107523c59d5fa08ea778a2c36c1db6f15d72f076f4')
    first_probes = {row['name']: row for row in first['probes']}
    full_probes = {row['name']: row for row in full['probes']}
    document = Path(first_probes['avgo_official_20240612_split_faq']['response_path'])
    pdf_text = ' '.join(PdfReader(document).pages[0].extract_text().split())
    if not all(term in pdf_text for term in ('June 12, 2024', 'July 15, 2024', 'Shares are multiplied by 10', 'Share price is divided by 10')):
        raise ValueError('Official AVGO split FAQ differs')
    amat = BeautifulSoup(Path(first_probes['amat_official_split_history']['response_path']).read_bytes(), 'html.parser')
    tables = [table for table in amat.find_all('table') if '04/16/02' in table.get_text()]
    if len(tables) != 1:
        raise ValueError('AMAT historical split table ambiguous')
    amat_rows = [[cell.get_text(' ', strip=True) for cell in row.find_all(['th', 'td'])] for row in tables[0].find_all('tr')]
    if amat_rows[-1][:2] != ['04/16/02', '2:1']:
        raise ValueError('AMAT latest declared historical split differs')
    reviewed = []
    for ticker in ('AMAT', 'AVGO', 'CDNS', 'GOOG'):
        short = first_probes['yahoo_' + ticker.lower() + '_daily_and_events']
        long = full_probes['yahoo_' + ticker.lower() + '_through_received_daily_events']
        if short['http_status'] != 200 or long['http_status'] != 200:
            raise ValueError('Price response missing')
        original = json.loads(Path(short['response_path']).read_bytes())['chart']['result'][0]
        current = json.loads(Path(long['response_path']).read_bytes())['chart']['result'][0]
        timestamps = current['timestamp']
        if len(timestamps) != len(set(timestamps)) or timestamps != sorted(timestamps):
            raise ValueError('Nonunique/unordered provider sessions')
        dates = [datetime.fromtimestamp(t, timezone.utc).date().isoformat() for t in timestamps]
        indexes = {timestamp: i for i, timestamp in enumerate(timestamps)}
        window = [i for i, date in enumerate(dates) if '2023-03-31' <= date <= '2024-06-03']
        if len(window) != 295 or current['meta']['symbol'] != ticker or current['meta']['currency'] != 'USD':
            raise ValueError('Price window or instrument differs')
        if any(original['indicators']['quote'][0][field][i] != current['indicators']['quote'][0][field][indexes[t]]
               for i, t in enumerate(original['timestamp'][:295]) for field in ('open', 'close')):
            raise ValueError('Two captures differ in target price window')
        splits = current.get('events', {}).get('splits', {})
        expected_splits = {'1721050200': {'date': 1721050200, 'numerator': 10.0, 'denominator': 1.0, 'splitRatio': '10:1'}} if ticker == 'AVGO' else {}
        if splits != expected_splits:
            raise ValueError('Provider split events differ from reviewed facts')
        corroboration = next(row for row in overlap['rows'] if row['ticker'] == ticker)
        if corroboration['archived_overlap_sessions'] != 294 or corroboration['differences_over_one_cent'] != 0:
            raise ValueError('Archived quote corroboration differs')
        reviewed.append(dict(ticker=ticker, price_response_path=long['response_path'],
            price_response_sha256=long['response_sha256'], received_at_utc=long['received_at_utc'],
            provider_session_count=len(timestamps), target_session_count=295,
            observed_full_requested_split_events=splits,
            provider_reports_no_target_window_split=True,
            target_nominal_reconstruction_factor=10 if ticker == 'AVGO' else 1,
            target_quotes_exactly_equal_between_captures=True,
            nominal_price_units_supported_by_archived_294_session_corroboration=True,
            archived_corroboration=corroboration,
            retrospective_price_unit_decision='SUPPORTED_FOR_LIMITED_RESEARCH_RECONSTRUCTION',
            historical_provider_security_identity_decision='NOT_ADJUDICATED_HERE',
            official_no_corporate_action_interval_certified=False))
    report = dict(schema='ndx_preference_price_basis_review_v1',
        purpose='BOUNDED_RETROSPECTIVE_PRICE_UNIT_RECONSTRUCTION_FINDINGS',
        quote_field_basis='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS',
        basis_status='CONDITIONAL_RESEARCH_ONLY',
        rows=reviewed, source_hashes=sources,
        avgo_official_split_fact=dict(announcement_date='2024-06-12', legal_effective_after_close_date='2024-07-12',
            first_split_adjusted_trading_date='2024-07-15', numerator=10, denominator=1,
            document_path=str(document), document_page=1,
            received_at_utc=first_probes['avgo_official_20240612_split_faq']['received_at_utc'],
            claim_scope='ISSUER_DECLARED_SPLIT_TERMS_CORROBORATED_BY_PROVIDER_EVENT',
            declaration_terms_verified=True),
        amat_official_split_history=dict(table=amat_rows, source_path=first_probes['amat_official_split_history']['response_path'],
            latest_listed_split_date='2002-04-16', historical_table_verified=True),
        formula='nominal_quote(session)=provider_quote(session)*product(split.numerator/split.denominator for split.date>session through observed request cutoff)',
        consumed_fields=['indicators.quote[0].open', 'indicators.quote[0].close'],
        forbidden_field='indicators.adjclose[0].adjclose',
        dividends_must_remain_separate=True,
        provider_event_query_end_exclusive_utc=full['request_end_exclusive_utc'],
        provider_reporting_completeness_independently_certified=False,
        raw_provider_documentation_limit='Yahoo help authentic raw explains adjclose splits+dividends; historical website split-only Close footnote was searchable but direct raw fetch returned 404. Quote basis additionally corroborated against archived nominal prices.',
        missing_official_access=['CDNS current issuer pages 403', 'GOOG 2023 issuer proxy 403'],
        current_to_historical_security_binding_verified=False, strategy_information_pit_verified=False,
        execution_performed=False, promotion_allowed=False)
    for path, digest in sources.items():
        bind(path, digest)
    path = FULL / 'price_basis_review_20260912.json'
    with path.open('xb') as handle:
        handle.write((json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())))


if __name__ == '__main__':
    run()

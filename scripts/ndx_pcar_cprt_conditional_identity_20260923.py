"""Source-bound dated common-share relations, explicitly not interval certification."""
import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_corrected_frontier_single_refit_archive_research import publish

BASE = ROOT / 'data/cache/research/standard_split_official_evidence_20260912_v1'
MANIFEST = BASE / 'supplement_manifest.json'
MANIFEST_SHA = '99fb04f4b6b57c3935120f797fd7a0b5956c50e81bcab6e3e09d343b5804b134'
CASES = {
    'PCAR': dict(cik='0000075362', cusip='693718108', company='PACCAR Inc', memo_company='PACCAR Inc.',
        title='Common Stock, $1 par value', period='December 31, 2021',
        context='C_0000075362_20210101_20211231',
        cover='issuer_0000075362/000156459022006237/pcar-10k_20211231.htm',
        cover_sha='3a53844a224b1b493bff210b3d38d345b3fa486ac0b3501fa5b5f2faebfe94d0'),
    'CPRT': dict(cik='0000900075', cusip='217204106', company='COPART, INC.', memo_company='Copart, Inc.',
        title='Common Stock, par value $0.0001', period='July 31 , 2022',
        context='idbf6ccbdab65411b8e3f29df33289d79_D20210801-20220731',
        cover='issuer_0000900075/000090007522000050/cprt-20220731.htm',
        cover_sha='338e61174693fb7b897d5ae5057e02e7995684f6143582fd22b544d09d7620c1'),
}
EVENTS = {
    'pcar_20230208_miax': dict(ticker='PCAR', number='51729', publication='January 05, 2023',
        date='2023-02-08', date_text='February 8, 2023', ex='02/08/2023', payable='February 7, 2023',
        record='January 17, 2023', new=3, old=2, deliverable=150,
        sha='89760ae64baa1d658e2081e2ba5e5b96a3ff0faf89972425a5178ccede462765'),
    'cprt_20221104_miax': dict(ticker='CPRT', number='51286', publication='November 03, 2022',
        date='2022-11-04', date_text='November 4, 2022', ex='11/04/2022', payable='November 3, 2022',
        record='October 6, 2022', new=2, old=1, deliverable=100,
        sha='b4291a8993d14bb3a41f787b6f3862548a991922e531b75eccffdf84db5b6faa'),
    'cprt_20230822_miax': dict(ticker='CPRT', number='53008', publication='August 10, 2023',
        date='2023-08-22', date_text='August 22, 2023', ex='08/22/2023', payable='August 21, 2023',
        record='August 14, 2023', new=2, old=1, deliverable=100,
        sha='cbe5bea40d9985b16eb98723bba3d8c7284b8e901937e528feb47edde8434510'),
}
FALSE = ('memo_contains_subject_cik', 'direct_single_document_cusip_cik_proof',
    'latest_security_interval_verified', 'provider_security_binding_verified',
    'corporate_action_completeness_verified', 'legal_training_input_ready',
    'point_in_time_verified', 'promotion_allowed', 'execution_authorized', 'fit_performed',
    'risk_chain_assigned', 'price_unit_independently_authenticated')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


LOADED = {str(p): sha(p) for p in (Path(__file__).resolve(), Path(publish.__code__.co_filename).resolve())}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def relation(ticker, cover_bytes, memo_texts):
    spec = CASES[ticker]
    required = {name for name, event in EVENTS.items() if event['ticker'] == ticker}
    if set(memo_texts) != required:
        raise ValueError('Complete specific memo denominator required')
    soup = BeautifulSoup(cover_bytes, 'lxml')
    fields = {}
    for name, expected in {'entitycentralindexkey': spec['cik'], 'entityregistrantname': spec['company'],
        'tradingsymbol': ticker, 'security12btitle': spec['title'], 'documentperiodenddate': spec['period']}.items():
        nodes = [n for n in soup.find_all(attrs={'name': True}) if n['name'].lower() == 'dei:' + name]
        if len(nodes) != 1 or nodes[0].get('contextref') != spec['context']:
            raise ValueError('Unique same-context cover field required: ' + name)
        text = ' '.join(nodes[0].get_text(' ', strip=True).split())
        if text != expected:
            raise ValueError('Original cover value differs: ' + name)
        fields[name] = dict(text=text, context=spec['context'])
    events = []
    for name in sorted(required):
        event = EVENTS[name]
        text = ' '.join(memo_texts[name].split())
        fragments = [f"#{event['number']}", f"Date: {event['publication']}",
            f"{spec['memo_company']} ({ticker}) has announced a {event['new']} for {event['old']} stock split.",
            f"Ex-Date: {event['ex']}", f"The Ex-distribution Date is {event['date_text']}.",
            f"The Payable Date is {event['payable']}.", f"The Record Date is {event['record']}.",
            f"{event['deliverable']} {spec['memo_company']} ({ticker}) Common Shares",
            'This Information Memo provides an unofficial summary']
        if any(text.count(fragment) != 1 for fragment in fragments):
            raise ValueError('Unique dated common-share memo clauses required')
        if re.findall(r'CUSIP:\s*([A-Z0-9]{9})(?![A-Za-z0-9])', text) != [spec['cusip']]:
            raise ValueError('Exact memo CUSIP required')
        if re.findall(r'Effective Date:\s*([A-Za-z]+ \d+, \d{4})(?![A-Za-z0-9])', text) != [event['date_text']]:
            raise ValueError('Effective date differs')
        events.append(dict(name=name, publication_date_text=event['publication'],
            first_adjusted_trading_date=event['date'], payable_date_text=event['payable'],
            record_date_text=event['record'], new_shares=event['new'], old_shares=event['old'],
            cusip=spec['cusip'], original_security_fragments=fragments,
            memo_is_unofficial_summary=True, option_symbols_are_not_equity_rename_evidence=True))
    return dict(ticker=ticker, conditional_research_security_id=f"security:{spec['cik']}:{spec['cusip']}",
        issuer_id='issuer:' + spec['cik'], cusip=spec['cusip'], security_class=spec['title'],
        original_cover_fields=fields, dated_memo_facts=events,
        class_relation='CONDITIONAL_COMMON_SHARES_TO_SINGLE_SEC_COMMON_STOCK_CLASS',
        company_name_variation='CASE_ONLY' if ticker == 'CPRT' else 'TERMINAL_PERIOD_ONLY',
        issuer_link_is_cross_document_research_assumption=True,
        dates_are_not_joint_availability=True, annual_report_receipt_time=None,
        annual_report_filing_date_independently_verified=False,
        risk_chain=None, risk_gap='NO_BUSINESS_RISK_CLASSIFICATION_ADJUDICATED',
        **dict.fromkeys(FALSE, False))


def verify_sources(sources):
    if any(sources.get(path) != digest for path, digest in LOADED.items()):
        raise ValueError('Loaded code omitted or replaced')
    for path, digest in sources.items():
        if sha(path) != digest:
            raise ValueError('Source changed: ' + path)


def build():
    from pypdf import PdfReader
    sources = dict(LOADED)
    sources[str(MANIFEST)] = MANIFEST_SHA
    for spec in CASES.values():
        sources[str(ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec' / spec['cover'])] = spec['cover_sha']
    for name, event in EVENTS.items():
        sources[str(BASE / (name + '.response.bin'))] = event['sha']
    verify_sources(sources)
    captures = json.loads(MANIFEST.read_text(encoding='utf-8'))['captures']
    rows = []
    for ticker, spec in CASES.items():
        texts, receipts = {}, {}
        for name, event in EVENTS.items():
            if event['ticker'] != ticker:
                continue
            path = BASE / (name + '.response.bin')
            matches = [r for r in captures if r['name'] == name]
            if len(matches) != 1:
                raise ValueError('Unique original capture required')
            receipt = matches[0]
            if receipt['http_status'] != 200 or receipt['raw_path'] != str(path) or receipt['raw_sha256'] != event['sha'] or receipt['decoded_sha256'] != event['sha']:
                raise ValueError('Capture does not bind original PDF')
            raw = path.read_bytes()
            if not raw.startswith(b'%PDF'):
                raise ValueError('Original PDF required')
            texts[name] = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(raw)).pages)
            receipts[name] = receipt
        cover = ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec' / spec['cover']
        row = relation(ticker, cover.read_bytes(), texts)
        row.update(cover_reference=dict(path=str(cover), sha256=spec['cover_sha']), original_memo_captures=receipts)
        rows.append(row)
    verify_sources(sources)
    return dict(schema='PCAR_CPRT_DATED_CONDITIONAL_IDENTITY_FACTS_V1', security_count=2,
        specific_memo_count=3, rows=rows, source_hashes=sources,
        scope='DATED_CROSS_DOCUMENT_RESEARCH_RELATIONS_ONLY', existing_fourteen_panel_modified=False,
        **dict.fromkeys(FALSE, False))


def verify(value):
    if canonical(value) != canonical(build()):
        raise ValueError('Complete source-bound facts rebuild differs')
    verify_sources(value['source_hashes'])


def publish_verified(path, value):
    verify(value)
    reference = publish(path, value)
    verify_sources(value['source_hashes'])
    return reference


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(publish_verified(args.output, build())))

"""CRWD cross-document dated facts; no interval, provider or volume certification."""
import argparse
import hashlib
import io
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
OUTPUT = BASE / 'crwd_conditional_identity_20260923_v1/identity.json'
PDF_PACKAGE = Path(r'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages')
if str(PDF_PACKAGE) not in sys.path:
    sys.path.append(str(PDF_PACKAGE))
import pypdf


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


BOUND = {
 'memo': (BASE/'remaining_standard_split_evidence_20260912_v1/crwd_miax.response.bin', '6ccd3d65d61068e080da9967d0528584d3807b6b61b132f1c9f934afb1ef4bd9'),
 'cover': (ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec/issuer_0001535527/000153552722000006/crwd-20220131.htm', '01ae5d04f8cf78d5dcacf7346743f82f8e973aba1df6011ef4066ac30c55d4f3'),
 'registry': (BASE/'standard_split_exact_gap_20260919_v1/registry_readback.json', '61c1a7a07f1a3ad65d3fffac43e8a8b4494c58c67192d93808333073f711c32e'),
 'suggestions': (BASE/'local_business_excerpt_research_20260912_v1/technology_business_suggestions_20260912.json', 'f3e0fa46fb0cd86a6fa0e49dcea7b6a05e873564c19e2db121c3dedbfb09b7eb'),
 'review': (BASE/'local_business_excerpt_research_20260912_v1/technology_business_independent_root_review_20260912.json', 'cfe29a071a189f11c3cb4e5876363c308cfd80bbc7dd1b365db7411458c54688'),
 'channels': (BASE/'new_cutoff_conditional_channels_20260923_v1/channels.json', '3d708df6b273616edd46e06d2e2976acbc0e9fd90cc1243679ff94ca8befa3ac'),
 'audit': (BASE/'new_cutoff_conditional_channels_20260923_v1/independent_raw_decimal_audit.json', 'a11e7fb3b9006eba71b9d254557f713a32b2615407c9b8f77e7b24a8c01a2ace'),
}
LOADED = {str(p): sha(p) for p in [Path(__file__).resolve(), *Path(pypdf.__file__).parent.rglob('*.py')]}
DOC = 'issuer:0001535527:0001535527-22-000006'
CONTEXT = 'i404921b3424c4df8b62dbd112e21c953_D20210201-20220131'
FALSE = ('point_in_time_verified','provider_security_binding_verified','latest_security_interval_verified',
 'classification_valid_interval_verified','corporate_action_completeness_verified','volume_unit_verified',
 'legal_training_input_ready','promotion_allowed','execution_authorized','fit_performed','http_performed',
 'direct_single_document_cusip_cik_proof','memo_contains_subject_cik','evidence_available_before_window_start')


def norm(text):
    return ' '.join(text.split())


class Cover(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields = {}
        self.active = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag.lower() == 'ix:nonnumeric':
            self.active.append((a.get('name','').lower(),a.get('contextref'),[]))
    def handle_data(self, text):
        for _, _, parts in self.active:
            parts.append(text)
    def handle_endtag(self, tag):
        if tag.lower() == 'ix:nonnumeric' and self.active:
            name, context, parts = self.active.pop()
            self.fields.setdefault(name, []).append((context,norm(''.join(parts))))


def one(rows, key, value):
    found = [r for r in rows if r.get(key) == value]
    if len(found) != 1:
        raise ValueError('Unique coordinate required: '+value)
    return found[0]


def relation(cover_bytes, memo_text, suggestion, review, channel):
    parsed = Cover(); parsed.feed(cover_bytes.decode('utf8'))
    expected = {'entitycentralindexkey':'0001535527','entityregistrantname':'CROWDSTRIKE HOLDINGS, INC.',
      'security12btitle':'Class A common stock, par value $0.0005 per share', 'tradingsymbol':'CRWD',
      'documentperiodenddate':'January 31, 2022'}
    for key, value in expected.items():
        if parsed.fields.get('dei:'+key) != [(CONTEXT,value)]:
            raise ValueError('Same-context unique cover mismatch: '+key)
    text = norm(memo_text)
    phrases = ['#59135','Date: June 09, 2026','Subject: CrowdStrike Holdings, Inc. - 4 For 1 Stock Split',
       '100 CrowdStrike Holdings, Inc. (CRWD) Class A Common Shares','CUSIP:22788C105',
       'Ex-Date: 07/02/2026','The Payable Date is July 1, 2026. The Record Date is June 25, 2026.',
       'This Information Memo provides an unofficial summary']
    for phrase in phrases:
        if text.count(phrase) != 1:
            raise ValueError('Unique memo phrase missing: '+phrase)
    if re.findall(r'CUSIP:\s*([A-Z0-9]{9})', text) != ['22788C105']:
        raise ValueError('Conflicting CUSIP')
    for row in (suggestion,review):
        if row['document_id'] != DOC or row['issuer_id'] != 'issuer:0001535527':
            raise ValueError('Risk subject mismatch')
    if (suggestion['suggested_risk_chain'] != 'cybersecurity' or review['suggested_chain'] != 'cybersecurity'
        or review['independent_business_definition_match'] is not True
        or review['eligible_for_conditional_research_mapping'] is not True
        or review['automatic_registry_assignment_allowed'] is not False
        or review['classification_interval_verified'] is not False
        or suggestion['paragraph_sha256'] != review['paragraph_sha256']
        or suggestion['raw_sha256'] != BOUND['cover'][1]):
        raise ValueError('Reviewed business source mismatch')
    # Independent text presence check; historical paragraph review remains the dated authority.
    parser = HTMLParser(convert_charrefs=True)
    pieces = []; parser.handle_data = pieces.append; parser.feed(cover_bytes.decode('utf8'))
    excerpt = suggestion['evidence_excerpt']
    if norm(excerpt) not in norm(''.join(pieces)) or hashlib.sha256(excerpt.encode()).hexdigest() != suggestion['excerpt_sha256']:
        raise ValueError('Original business excerpt absent')
    ci = channel['channel_input']
    if (channel['ticker'] != 'CRWD' or channel['status'] != 'CONDITIONAL_NUMERIC_RESULT'
        or ci['liquidity']['status'] != 'BLOCKED_VOLUME_UNIT_UNKNOWN'
        or len(ci['calendar']) != 127 or ci['calendar'][0] != '2026-03-20' or ci['calendar'][-1] != '2026-09-21'):
        raise ValueError('Bound current window / volume restriction mismatch')
    return dict(schema='CRWD_CONDITIONAL_DATED_IDENTITY_V1', ticker='CRWD',
      security_id='security:0001535527:22788C105', issuer_id='issuer:0001535527', subject_cik='0001535527',
      cusip='22788C105', security_class='CLASS_A_COMMON', risk_chain='cybersecurity',
      status='CONDITIONAL_CROSS_DOCUMENT_IDENTITY_VOLUME_BLOCKED', cover_fields=expected,
      cover_context=CONTEXT, memo_publication_date='2026-06-09', memo_effective_date='2026-07-02',
      memo_record_date='2026-06-25', memo_payable_date='2026-07-01',
      memo_normalized_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
      memo_extracts=[dict(text=p,normalized_text_offset=text.index(p)) for p in phrases],
      memo_role='OCC_UNOFFICIAL_OPTIONS_SUMMARY_HOSTED_BY_EXCHANGE',
      cross_document_connection='MATCHED_COMPANY_TICKER_CLASS; CIK_FROM_ANNUAL_COVER_ONLY',
      dated_risk_suggestion=suggestion, historical_independent_risk_review=review,
      calendar=ci['calendar'], window_stability_assumption='EXPLICIT_NEW_CONDITIONAL_REUSE_NOT_CERTIFIED_INTERVAL',
      risk_reuse_assumption='HISTORICAL_BUSINESS_MATCH_REUSED_CONDITIONALLY_NOT_CURRENT_CLASSIFICATION_CERTIFICATION',
      volume_status='BLOCKED_VOLUME_UNIT_UNKNOWN', training_blockers=['VOLUME_UNIT_UNKNOWN','CONDITIONAL_IDENTITY_NOT_CERTIFICATION'],
      **{k:False for k in FALSE})


def check(sources):
    for path, digest in sources.items():
        if sha(path) != digest:
            raise ValueError('Source drift: '+path)


def build():
    sources = {**LOADED, **{str(p): h for p,h in BOUND.values()}}
    check(sources)
    raw = {}
    for key, (path, digest) in BOUND.items():
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != digest:
            raise ValueError('Consumed bytes mismatch: '+key)
        raw[key] = blob
    data = {k:json.loads(blob) for k,blob in raw.items() if k not in ('cover','memo')}
    event = one(data['registry']['events'],'ticker','CRWD')
    if (event['raw_path'] != str(BOUND['memo'][0]) or event['raw_sha256'] != BOUND['memo'][1]
        or event['cusip'] != '22788C105' or event['security_class'] != 'CLASS_A_COMMON'
        or event['publication_date'] != '2026-06-09' or event['first_adjusted_trading_date'] != '2026-07-02'):
        raise ValueError('Memo historical readback linkage mismatch')
    suggestion = one(data['suggestions']['suggestions'],'document_id',DOC)
    review = one(data['review']['results'],'document_id',DOC)
    channel = one(data['channels']['rows'],'ticker','CRWD')
    if data['audit']['candidate_reference'] != {'path':str(BOUND['channels'][0]),'sha256':BOUND['channels'][1]}:
        raise ValueError('Independent channel audit binding mismatch')
    detail = one(data['audit']['details'],'ticker','CRWD')
    if detail['liquidity_status'] != 'BLOCKED_VOLUME_UNIT_UNKNOWN':
        raise ValueError('Independent audit volume restriction mismatch')
    text = '\n'.join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(raw['memo'])).pages)
    result = relation(raw['cover'],text,suggestion,review,channel)
    result['source_hashes'] = sources
    result['input_references'] = {k:dict(path=str(p),sha256=h) for k,(p,h) in BOUND.items()}
    result['memo_url'] = 'https://www.miaxglobal.com/sites/default/files/alert-files/CRWD_Split_59135.pdf'
    result['memo_received_at_utc'] = event['received_at_utc']
    result['memo_historical_readback'] = event
    result['cover_url'] = 'https://www.sec.gov/Archives/edgar/data/1535527/000153552722000006/crwd-20220131.htm'
    result['source_closure_scope'] = 'EXACT_CONSUMED_ARTIFACTS_AND_PDF_PARSER_PYTHON_FILES_NOT_RUNTIME_BINARY_CERTIFICATION'
    check(sources)
    return result


def build_and_publish():
    if OUTPUT.parent.exists():
        raise ValueError('Fixed namespace already exists; no repeated build')
    result = build()
    if any(result.get(k) is not False for k in FALSE):
        raise ValueError('Authority upgrade')
    expected = {**LOADED, **{str(p):h for p,h in BOUND.values()}}
    if result['source_hashes'] != expected:
        raise ValueError('Source map mismatch')
    check(expected)
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    payload = (json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with OUTPUT.open('xb') as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    check(expected)
    if sorted(p.name for p in OUTPUT.parent.iterdir()) != [OUTPUT.name]:
        raise ValueError('Unexpected publication namespace contents')
    if OUTPUT.read_bytes() != payload:
        raise ValueError('Publication readback mismatch')
    return sha(OUTPUT)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    if not args.publish:
        parser.error('--publish required; no implicit artifact generation')
    print(json.dumps({'path':str(OUTPUT),'sha256':build_and_publish()}))

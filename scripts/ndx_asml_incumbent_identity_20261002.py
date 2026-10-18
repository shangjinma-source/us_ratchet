"""Dated ASML cross-document identity sidecar; no ADR or holding conversion."""
import argparse
import gzip
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
OUTPUT = ROOT / 'data/cache/research/asml_incumbent_identity_20261002_v1'
SCHEMA = 'ASML_INCUMBENT_CONDITIONAL_DATED_IDENTITY_V1'
BOUND = {
 'annual': ('data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec/issuer_0000937966/000093796621000007/asml-20201231.htm', '7bcb9f3a14f64df1af2674bbdb63296ddc199a54f485170ecf3a58db3d9f6394'),
 'annual_manifest': ('data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec/issuer_0000937966/000093796621000007/asml-20201231.htm.manifest.json', '8263be0fa0201a5b734519a4005a31a3ada2ffccc8bc0fae7f25a6efdd0a6595'),
 'nport_raw': ('data/cache/research/identity_public_source_probe_20260912_v1/sec_qqq_nport_20230228.response.bin', '3b4e01ee477fed756b7c9cda91aa8ed65f94cafef5a3da4b8775bdf112e57792'),
 'nport_manifest': ('data/cache/research/identity_public_source_probe_20260912_v1/manifest.json', '93de067b0e994adb0d2b6b1860cb9c3f36e2173c445f044db5f08bc14e20a3c2')}
DECODED_SHA = '9ae7e606c7fab7c8c0d2e29dd1e58600e24af6014717e057d2073b95f4fa8e42'
ANNUAL_URL = 'https://www.sec.gov/Archives/edgar/data/937966/000093796621000007/asml-20201231.htm'
NPORT_URL = 'https://www.sec.gov/Archives/edgar/data/1067839/000175272423047901/primary_doc.xml'
CONTEXT = 'i1897fb38cb5844acb93eee454c93c370_D20200101-20201231'
TEXTS = (
 "As ASML's New York Shares are listed on NASDAQ Stock Market LLC (‘NASDAQ’)",
 'Our ordinary shares are listed for trading in the form of registered ASML NASDAQ shares and in the form of registered ASML Euronext Amsterdam shares.',
 'Our shares listed on NASDAQ are registered with JPMorgan Chase Bank N.A., our New York Transfer Agent, pursuant to the terms of the Transfer Agent Agreement between ASML and JPMorgan Chase Bank N.A.')
FALSE_FLAGS = dict.fromkeys(('point_in_time_verified', 'promotion_allowed', 'ndx_membership_verified',
 'price_identity_verified', 'holdings_conversion_performed', 'price_conversion_performed',
 'historical_2023_identity_interval_verified', 'cross_document_identity_certified',
 'single_document_cik_cusip_binding_verified', 'local_evidence_available_in_2023_verified',
 'legal_identity_certified', 'corporate_action_completeness_verified', 'live_execution_authorized',
 'orders_generated', 'fit_performed', 'account_executed', 'old_audit_repeated'), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


LOADED = {str(SOURCE): digest(SOURCE.read_bytes())}


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def strict(sources):
    for path, sha in sources.items():
        require(digest(Path(path).read_bytes()) == sha, 'Source drift: ' + path)



class AnnualParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.fields, self.contexts = [], [], []
        self.active_fields = []
        self.context = self.leaf = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == 'ix:nonnumeric':
            self.active_fields.append({'name': attrs.get('name', '').lower(), 'context': attrs.get('contextref'), 'parts': []})
        if tag == 'xbrli:context':
            require(self.context is None, 'Nested context')
            self.context = {'id': attrs.get('id'), 'identifier': [], 'startdate': [], 'enddate': [], 'segments': 0}
        if self.context is not None:
            if tag == 'xbrli:segment':
                self.context['segments'] += 1
            if tag in ('xbrli:identifier', 'xbrli:startdate', 'xbrli:enddate'):
                self.leaf = {'tag': tag, 'parts': []}

    def handle_endtag(self, tag):
        if tag == 'ix:nonnumeric' and self.active_fields:
            value = self.active_fields.pop()
            self.fields.append({'name': value['name'], 'context': value['context'], 'text': ' '.join(' '.join(value['parts']).split())})
        if self.leaf is not None and tag == self.leaf['tag']:
            self.context[tag.split(':')[-1]].append(''.join(self.leaf['parts']).strip())
            self.leaf = None
        if tag == 'xbrli:context' and self.context is not None:
            self.contexts.append(self.context)
            self.context = None

    def handle_data(self, data):
        self.parts.append(data)
        for field in self.active_fields:
            field['parts'].append(data)
        if self.leaf is not None:
            self.leaf['parts'].append(data)


def annual_facts(raw, manifest, reference, manifest_reference):
    require(digest(raw) == reference['sha256'] == manifest['content_sha256'], 'Annual hash mismatch')
    require(type(manifest['content_bytes']) is int and manifest['content_bytes'] == len(raw), 'Annual byte count mismatch')
    require(Path(manifest['cache_path']).resolve() == Path(reference['path']).resolve()
            and Path(manifest['manifest_path']).resolve() == Path(manifest_reference['path']).resolve(), 'Annual manifest paths mismatch')
    expected = {'schema_version': 1, 'cik': '0000937966', 'issuer_id': 'issuer:0000937966', 'ticker': 'ASML',
                'form': '20-F', 'accession_number': '0000937966-21-000007', 'source_locator': ANNUAL_URL,
                'evidence_available_date': '2021-02-11', 'fetched_at': '2026-07-13T15:45:54+00:00',
                'dataset_type': 'ndx_taxonomy_v2_sec_raw_filing'}
    for key, value in expected.items():
        require(type(manifest.get(key)) is type(value) and manifest[key] == value, 'Annual field mismatch: ' + key)
    require(manifest['research_only'] is True and manifest['classification_automatic'] is False, 'Annual scope mismatch')
    parser = AnnualParser()
    parser.feed(raw.decode('utf-8', errors='strict'))
    parser.close()
    require(not parser.active_fields and parser.context is None, 'Unclosed annual capture')
    fields = {}
    for name, value in {'dei:entitycentralindexkey': '0000937966', 'dei:tradingsymbol': 'ASML',
                        'dei:security12btitle': 'Ordinary Shares', 'dei:documentperiodenddate': 'December 31 , 2020'}.items():
        matches = [item for item in parser.fields if item['name'] == name]
        require(len(matches) == 1 and matches[0]['context'] == CONTEXT and matches[0]['text'] == value, 'Ambiguous/mismatched cover field: ' + name)
        fields[name] = matches[0]
    contexts = [item for item in parser.contexts if item['id'] == CONTEXT]
    require(len(contexts) == 1 and contexts[0]['identifier'] == ['0000937966']
            and contexts[0]['startdate'] == ['2020-01-01'] and contexts[0]['enddate'] == ['2020-12-31']
            and contexts[0]['segments'] == 0, 'Annual cover entity/period/context mismatch')
    text = ' '.join(' '.join(parser.parts).split())
    require(text.count('CUSIP') == 0 and text.count('N07059210') == 0, 'Unexpected annual CUSIP; preserve separate evidence contract')
    passages = []
    for needle in TEXTS:
        require(text.count(needle) == 1, 'Annual listing text absent/ambiguous')
        start = text.index(needle)
        passages.append({'text': needle, 'normalized_start': start, 'normalized_end_exclusive': start + len(needle)})
    return {'report_date': '2020-12-31', 'evidence_available_date': manifest['evidence_available_date'],
            'fetched_at': manifest['fetched_at'], 'cover_fields': fields, 'cover_context': contexts[0],
            'listing_passages': passages, 'normalized_text_sha256': digest(text.encode()),
            'normalization': 'UTF8_STRICT_HTMLPARSER_ALL_HANDLE_DATA_JOIN_WHITESPACE_ZERO_BASED_CHAR_OFFSETS',
            'cusip_present_in_annual': False, 'original_manifest': manifest, 'reference': reference}


def xml_one(element, path, namespaces):
    matches = element.findall(path, namespaces)
    require(len(matches) == 1, 'XML field absent/duplicate: ' + path)
    return ''.join(matches[0].itertext()).strip()


def nport_facts(raw, manifest, reference, decoded_sha):
    probes = [(index, item) for index, item in enumerate(manifest['probes']) if item.get('name') == 'sec_qqq_nport_20230228']
    require(len(probes) == 1, 'NPORT receipt absent/duplicate')
    index, receipt = probes[0]
    require(type(receipt['http_status']) is int and receipt['http_status'] == 200 and receipt['transport_success'] is True, 'NPORT unsuccessful receipt')
    require(receipt['request']['method'] == 'GET' and receipt['request']['url'] == NPORT_URL == receipt['final_url'], 'NPORT URL mismatch')
    require(receipt['received_at_utc'] == '2026-09-11T18:19:26.610468+00:00'
            and receipt['started_at_utc'] == '2026-09-11T18:19:26.177637+00:00', 'NPORT receipt time mismatch')
    require(receipt['response_sha256'] == reference['sha256'] == digest(raw)
            and Path(receipt['response_path']).resolve() == Path(reference['path']).resolve(), 'NPORT raw binding mismatch')
    require(type(receipt['response_bytes']) is int and receipt['response_bytes'] == len(raw), 'NPORT receipt length mismatch')
    require(len(raw) <= 2_000_000 and raw.startswith(b'\x1f\x8b'), 'Expected bounded gzip transport')
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        decoded = stream.read(10_000_001)
    require(len(decoded) <= 10_000_000 and digest(decoded) == decoded_sha, 'NPORT decoded binding/size mismatch')
    require(b'<!DOCTYPE' not in decoded and b'<!ENTITY' not in decoded, 'DTD/entities unsupported')
    tree = ET.fromstring(decoded)
    ns = {'n': 'http://www.sec.gov/edgar/nport'}
    require(tree.tag == '{http://www.sec.gov/edgar/nport}edgarSubmission', 'Wrong XML namespace/root')
    period = xml_one(tree, 'n:formData/n:genInfo/n:repPdDate', ns)
    period_end = xml_one(tree, 'n:formData/n:genInfo/n:repPdEnd', ns)
    fund_cik = xml_one(tree, 'n:formData/n:genInfo/n:regCik', ns)
    require(period == '2022-12-31' and period_end == '2023-09-30' and fund_cik == '0001067839', 'NPORT report/fund fields mismatch')
    rows = tree.findall('n:formData/n:invstOrSecs/n:invstOrSec', ns)
    matches = [(i, row) for i, row in enumerate(rows) if any(element.text == 'N07059210' for element in row.findall('n:cusip', ns))]
    require(len(matches) == 1, 'ASML NPORT CUSIP absent/duplicate')
    row_index, row = matches[0]
    expected = {'name': 'ASML Holding N.V.', 'title': 'ASML Holding N.V., New York Shares',
                'cusip': 'N07059210', 'lei': '724500Y6DUVHQD6OXN27', 'curCd': 'USD', 'assetCat': 'EC'}
    values = {name: xml_one(row, 'n:' + name, ns) for name in expected}
    require(values == expected, 'ASML NPORT identity fields mismatch')
    isin = row.findall('n:identifiers/n:isin', ns)
    require(len(isin) == 1 and isin[0].get('value') == 'USN070592100', 'NPORT ISIN mismatch')
    return {'report_date': period, 'reporting_period_end': period_end, 'reporting_fund_cik': fund_cik,
            'reporting_fund_cik_is_security_issuer': False, 'security_fields': values, 'isin': 'USN070592100',
            'row_index_zero_based': row_index, 'security_xml': ET.tostring(row, encoding='unicode'),
            'xml_pointer': '/edgarSubmission/formData/invstOrSecs/invstOrSec[cusip="N07059210"]',
            'receipt_json_pointer': '/probes/' + str(index), 'original_receipt': receipt,
            'decoded_sha256': decoded_sha, 'transport_encoding': 'gzip', 'reference': reference,
            'issuer_cik_present_in_security_row_verified': False, 'ticker_present_in_security_row_verified': False}


def assemble(annual_raw, annual_manifest, nport_raw, nport_manifest, references, decoded_sha):
    annual = annual_facts(annual_raw, annual_manifest, references['annual'], references['annual_manifest'])
    nport = nport_facts(nport_raw, nport_manifest, references['nport_raw'], decoded_sha)
    return {'schema': SCHEMA, 'ticker': 'ASML', 'security_id': 'security:0000937966:N07059210',
            'issuer_id': 'issuer:0000937966', 'issuer_cik': '0000937966', 'cusip': 'N07059210',
            'security_class': 'New York Shares', 'annual_registered_class': 'Ordinary Shares',
            'annual_fact': annual, 'nport_fact': nport, 'source_references': references,
            'cross_document_join_assumption': 'Conditionally associate the 2022 N-PORT ASML New York Shares/CUSIP/LEI record with the 2020 ASML same-context cover and NASDAQ registration narrative. The annual has no CUSIP; the N-PORT reporting fund CIK is not the security issuer. This is not proof of 2023 identity continuity.',
            'depositary_receipt_class_asserted': False, 'ads_conversion_ratio': None,
            'research_only': True, 'dated_facts_observed': True, **FALSE_FLAGS}


def build():
    strict(LOADED)
    references = {role: {'path': str(ROOT / path), 'sha256': sha} for role, (path, sha) in BOUND.items()}
    raw = {}
    sources = dict(LOADED)
    for role, reference in references.items():
        raw[role] = Path(reference['path']).read_bytes()
        require(digest(raw[role]) == reference['sha256'], 'Hard source hash mismatch: ' + role)
        sources[reference['path']] = reference['sha256']
    result = assemble(raw['annual'], json.loads(raw['annual_manifest']), raw['nport_raw'], json.loads(raw['nport_manifest']), references, DECODED_SHA)
    strict(sources)
    result['source_hashes'] = sources
    return result


def durable(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def publish():
    require(not OUTPUT.exists(), 'Fixed namespace exists; no overwrite or retry')
    result = build()
    strict(result['source_hashes'])
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        raw = encoded(result)
        path = OUTPUT / 'identity.json'
        durable(path, raw)
        strict(result['source_hashes'])
        require(path.read_bytes() == raw and {p.name for p in OUTPUT.iterdir()} == {'identity.json'}, 'Publication readback/orphan failure')
        reference = {'path': str(path), 'sha256': digest(raw)}
        receipt = encoded({'schema': 'ASML_CONDITIONAL_IDENTITY_PUBLICATION_V1', 'identity_reference': reference,
                           'source_hashes': result['source_hashes'], 'status': 'PUBLISHED_CONDITIONAL_SID_SIDECAR_ONLY'})
        durable(OUTPUT / 'publication.json', receipt)
        strict(result['source_hashes'])
        require(path.read_bytes() == raw and (OUTPUT / 'publication.json').read_bytes() == receipt
                and {p.name for p in OUTPUT.iterdir()} == {'identity.json', 'publication.json'}, 'Final publication readback/orphan failure')
        return dict(reference, publication_sha256=digest(receipt))
    except Exception as error:
        durable(OUTPUT / 'failure.json', encoded({'status': 'FAILED_NOT_CONSUMABLE', 'error': str(error), 'retry_allowed': False}))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Publish this new conditional sidecar once')
    args = parser.parse_args()
    if not args.execute:
        parser.error('Explicit --execute required; no implicit build')
    print(json.dumps(publish(), indent=2))

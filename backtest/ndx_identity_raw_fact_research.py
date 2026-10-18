"""Extract bound primary-source facts; never adjudicate price identity or PIT."""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ElementTree

from bs4 import BeautifulSoup

SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
NS = {'n': 'http://www.sec.gov/edgar/nport'}
EXPECTED_CUSIPS = {'038222105', '11135F101', '127387108', '02079K107'}
PROBE_NAMES = {'openfigi_cusip_mapping', 'eastmoney_amat_nominal_two_sessions',
    'yahoo_amat_two_sessions', 'nasdaq_amat_historical_access',
    'nasdaq_meta_20220603_rename_notice', 'occ_fiserv_20230605_rename_notice', 'sec_qqq_nport_20230228'}


def verify(sources):
    for path, expected in sources.items():
        if not Path(path).is_absolute() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Raw fact source drift: ' + path)


def _utc(value):
    if type(value) is not str:
        raise ValueError('Recorded reception UTC required')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError('Recorded reception UTC required')
    return value


def _single_text(parent, name):
    nodes = parent.findall('n:' + name, NS)
    if len(nodes) != 1 or not nodes[0].text or nodes[0].text != nodes[0].text.strip():
        raise ValueError('Unique explicit NPORT field required: ' + name)
    return nodes[0].text


def extract_nport(raw, cusips):
    decoded = gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
    if b'<!DOCTYPE' in decoded or b'<!ENTITY' in decoded:
        raise ValueError('NPORT external/entity declarations forbidden')
    root = ElementTree.fromstring(decoded)
    if root.tag != '{http://www.sec.gov/edgar/nport}edgarSubmission':
        raise ValueError('NPORT SEC namespace differs')
    def unique(parent, name):
        nodes = parent.findall('n:' + name, NS)
        if len(nodes) != 1:
            raise ValueError('Unique NPORT container required: ' + name)
        return nodes[0]
    header = unique(root, 'headerData')
    form = unique(root, 'formData')
    general = unique(form, 'genInfo')
    securities = unique(form, 'invstOrSecs')
    if _single_text(header, 'submissionType') != 'NPORT-P':
        raise ValueError('Public NPORT-P document required')
    if _single_text(general, 'regCik') != '0001067839':
        raise ValueError('QQQ reporting fund CIK differs')
    report_date = _single_text(general, 'repPdDate')
    if report_date != '2022-12-31':
        raise ValueError('Expected NPORT reporting date differs')
    matches = {}
    for position, node in enumerate(securities.findall('n:invstOrSec', NS)):
        nodes = node.findall('n:cusip', NS)
        if len(nodes) != 1:
            raise ValueError('Unique NPORT holding CUSIP required')
        cusip = nodes[0].text
        if cusip not in cusips:
            continue
        if cusip in matches:
            raise ValueError('Duplicate requested NPORT CUSIP')
        identifiers = node.findall('n:identifiers/n:isin', NS)
        if len(identifiers) != 1 or not re.fullmatch(r'US[A-Z0-9]{10}', identifiers[0].get('value', '')):
            raise ValueError('Explicit unique NPORT ISIN required')
        isin = identifiers[0].get('value')
        if isin[2:11] != cusip:
            raise ValueError('NPORT CUSIP and ISIN security body differ')
        matches[cusip] = dict(cusip=cusip, isin=isin, issuer_name=_single_text(node, 'name'),
            security_title=_single_text(node, 'title'), lei=_single_text(node, 'lei'),
            currency=_single_text(node, 'curCd'), security_ticker=None, security_issuer_cik=None,
            absent_fields_not_inferred=['security_ticker', 'security_issuer_cik'],
            reporting_fund_cik='0001067839', reporting_fund_cik_is_security_issuer=False,
            fact_observation_date=report_date, fact_valid_interval=None,
            published_at_utc=None, filing_date_in_raw_document=None,
            xml_element_position=position,
            xml_locator='/edgarSubmission/formData/invstOrSecs/invstOrSec[cusip="' + cusip + '"]')
    if set(matches) != set(cusips):
        raise ValueError('Requested CUSIP absent from raw NPORT')
    return dict(decoded_sha256=hashlib.sha256(decoded).hexdigest(), decoded_bytes=len(decoded),
        raw_encoding='GZIP_IDENTIFIED_BY_MAGIC' if raw.startswith(b'\x1f\x8b') else 'XML_BYTES',
        report_date=report_date, reporting_fund_cik='0001067839', holdings=matches)


def extract_openfigi(request_metadata, raw):
    if (request_metadata['method'] != 'POST' or request_metadata['url'] != 'https://api.openfigi.com/v3/mapping'
            or request_metadata['credentials_sent'] is not False):
        raise ValueError('Explicit public CUSIP mapping request required')
    jobs = request_metadata['json_payload']
    response = json.loads(raw)
    if type(jobs) is not list or type(response) is not list or len(jobs) != len(response) or not jobs:
        raise ValueError('OpenFIGI request-response denominator differs')
    output = {}
    for position, (job, result) in enumerate(zip(jobs, response)):
        if (set(job) != {'idType', 'idValue', 'exchCode'} or job['idType'] != 'ID_CUSIP'
                or job['exchCode'] != 'US' or not re.fullmatch(r'[A-Z0-9]{9}', job['idValue'])):
            raise ValueError('Exact CUSIP request required')
        cusip = job['idValue']
        if cusip in output or set(result) != {'data'} or len(result['data']) != 1:
            raise ValueError('Unique unambiguous OpenFIGI response required')
        reference = result['data'][0]
        if 'cusip' in reference and reference['cusip'] != cusip:
            raise ValueError('OpenFIGI explicit CUSIP echo conflicts with request')
        if (reference.get('exchCode') != 'US' or reference.get('securityType') != 'Common Stock'
                or reference.get('marketSector') != 'Equity'
                or any(not re.fullmatch(r'BBG[A-Z0-9]{9}', reference.get(key, ''))
                       for key in ('figi', 'compositeFIGI', 'shareClassFIGI'))):
            raise ValueError('US equity FIGI response required')
        output[cusip] = dict(request_position=position, requested_cusip=cusip,
            response=deepcopy(reference), response_cusip_echo_present='cusip' in reference,
            mapping_time_scope='RETRIEVED_NOW_NO_HISTORICAL_AS_OF_PARAMETER',
            fact_valid_interval=None, published_at_utc=None, historic_available_at=None,
            historical_mapping_verified=False)
    return output


def extract_nasdaq_meta_notice(raw):
    """Dedicated known-notice contract, not keyword presence authentication."""
    soup = BeautifulSoup(raw, 'html.parser')
    headers = soup.select('#NewsHeader')
    if len(headers) != 1:
        raise ValueError('Unique Nasdaq article header required')
    date_nodes = headers[0].select('p > strong')
    if len(date_nodes) != 1 or date_nodes[0].get_text(' ', strip=True) != 'Friday, June 3, 2022':
        raise ValueError('Nasdaq publication date differs')
    headings = headers[0].find_all('h2')
    title = ' '.join(headings[0].get_text(' ', strip=True).split()) if len(headings) == 1 else ''
    if title != ('Equity Corporate Actions Alert #2022 - 125 '
                  'Information Regarding the symbol change for Meta Platforms, Inc. (FB)'):
        raise ValueError('Nasdaq notice identity differs')
    tables = []
    for table in soup.select('.newscontentbox2 .genTable table'):
        rows = table.find_all('tr')
        values = {}
        for row in rows:
            labels, cells = row.find_all('th', recursive=False), row.find_all('td', recursive=False)
            if len(labels) != 1 or len(cells) != 1:
                raise ValueError('Exact Nasdaq label/value table required')
            label = labels[0].get_text(' ', strip=True)
            if label in values:
                raise ValueError('Duplicate Nasdaq table label')
            values[label] = cells[0].get_text(' ', strip=True)
        tables.append(values)
    expected = {'Company Name/Issue:': 'Meta Platforms, Inc. Class A Common Stock',
        'CUSIP#:': '30303M102', 'Current Symbol:': 'FB', 'New Symbol:': 'META',
        'Marketplace Effective Date for Change:': 'June 9, 2022'}
    if tables != [expected]:
        raise ValueError('Nasdaq CUSIP/symbol/effective-date table differs')
    return dict(notice_id='ECA2022-125', publication_date='2022-06-03', published_at_utc=None,
        publication_time_precision='DATE_ONLY', fact_effective_date='2022-06-09',
        cusip='30303M102', from_ticker='FB', to_ticker='META', security_issuer_cik=None,
        event_claim='SAME_CLASS_A_COMMON_STOCK_SYMBOL_CHANGE',
        source_table_fields=expected, provider_price_interval_binding_verified=False)


def extract_bound_probe(*, manifest_path, expected_sha256):
    manifest_path = Path(manifest_path).resolve()
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Probe manifest SHA differs')
    manifest = json.loads(raw)
    if (manifest['schema'] != 'ndx_identity_public_source_probe_v1'
            or any(manifest[key] is not False for key in ('point_in_time_verified', 'execution_performed',
                'promotion_allowed', 'provider_to_historical_security_binding_verified'))):
        raise ValueError('Unadjudicated research probe required')
    sources = dict(manifest['source_hashes'])
    for path, digest in {str(manifest_path): expected_sha256, str(SOURCE): LOADED_SHA}.items():
        if path in sources and sources[path] != digest:
            raise ValueError('Conflicting extraction source')
        sources[path] = digest
    verify(sources)
    probes, bodies = {}, {}
    for item in manifest['probes']:
        name = item['name']
        if name in probes:
            raise ValueError('Duplicate probe identity')
        _utc(item['received_at_utc'])
        if item['request']['credentials_sent'] is not False:
            raise ValueError('Public sanitized probe required')
        probes[name] = deepcopy(item)
        if item['response_path'] is None:
            if item['http_status'] is not None or item['response_sha256'] is not None or item['response_bytes'] != 0:
                raise ValueError('Missing raw response metadata differs')
            continue
        path = Path(item['response_path']).resolve()
        if path.parent != manifest_path.parent:
            raise ValueError('Raw response outside bound probe directory')
        body = path.read_bytes()
        if len(body) != item['response_bytes'] or hashlib.sha256(body).hexdigest() != item['response_sha256']:
            raise ValueError('Raw HTTP body binding differs')
        if str(path) in sources and sources[str(path)] != item['response_sha256']:
            raise ValueError('Conflicting raw body source')
        sources[str(path)] = item['response_sha256']
        bodies[name] = body
    if set(probes) != PROBE_NAMES:
        raise ValueError('Complete original probe denominator required')
    required = ('openfigi_cusip_mapping', 'sec_qqq_nport_20230228', 'nasdaq_meta_20220603_rename_notice')
    if any(probes[name]['http_status'] != 200 or probes[name]['transport_success'] is not True for name in required):
        raise ValueError('Required raw fact source was not successfully retrieved')
    for name, url in {
        required[1]: 'https://www.sec.gov/Archives/edgar/data/1067839/000175272423047901/primary_doc.xml',
        required[2]: 'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-125',
    }.items():
        if probes[name]['request']['method'] != 'GET' or probes[name]['request']['url'] != url:
            raise ValueError('Expected dedicated primary-source request differs')
    references = extract_openfigi(probes[required[0]]['request'], bodies[required[0]])
    if set(references) != EXPECTED_CUSIPS:
        raise ValueError('Complete original four-CUSIP denominator required')
    nport = extract_nport(bodies[required[1]], set(references))
    event = extract_nasdaq_meta_notice(bodies[required[2]])
    for cusip in references:
        references[cusip]['received_at_utc'] = probes[required[0]]['received_at_utc']
        nport['holdings'][cusip]['received_at_utc'] = probes[required[1]]['received_at_utc']
    event['received_at_utc'] = probes[required[2]]['received_at_utc']
    outcomes = []
    for name, item in probes.items():
        status = ('NO_HTTP_RESPONSE' if item['http_status'] is None else
                  'HTTP_ERROR_RAW_RETAINED' if item['http_status'] != 200 else 'HTTP_200_CONTENT_NOT_ADJUDICATED')
        if name == 'nasdaq_amat_historical_access' and item['http_status'] == 200:
            value = json.loads(bodies[name])
            if isinstance(value.get('data'), dict) and value['data'].get('totalRecords') == 0:
                status = 'HTTP_200_EMPTY_PRICE_DATA'
        outcomes.append(dict(item, extraction_access_status=status))
    verify(sources)
    return dict(schema='ndx_identity_raw_fact_research_v1',
        scope='FACT_EXTRACTION_NOT_BINDING_ADJUDICATION', nport=nport,
        current_cusip_references=references, nasdaq_meta_event=event,
        probe_outcomes=outcomes, source_hashes=sources,
        candidate_scope='ALL_POINT_IN_TIME_NDX_ISSUERS_NO_INDUSTRY_FILTER',
        probe_examples_are_candidate_pool=False, raw_nport_has_security_ticker=False,
        raw_nport_has_security_issuer_cik=False, provider_to_historical_security_binding_verified=False,
        source_authenticity_adjudicated=False, historical_information_availability_verified=False,
        strategy_information_pit_verified=False, point_in_time_verified=False,
        selection_performed=False, execution_performed=False, promotion_allowed=False)

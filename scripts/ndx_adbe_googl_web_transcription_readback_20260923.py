"""Offline, stdlib-only verification of two bounded web observations, not admission."""
import argparse
import hashlib
import json
import os
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE = ROOT / 'data/cache/research/adbe_googl_web_transcription_20260923_v1'
ARTIFACTS = {
    'ADBE': '16a92629a586bec6eee31656f60d4eb1ae1b6adf2b698d4a8832c34fe9cdd625',
    'GOOGL': '0e4a9568403a715083c36f5eed032d82465b72013f8138090c4fcfb32ee6a757',
}
FLAGS = ('full_tool_response_preserved', 'local_http_original_bytes_available',
         'historical_identity_interval_verified', 'provider_binding_verified',
         'point_in_time_verified', 'promotion_allowed')
EXPECTED = {
    'ADBE': ('0000796343', '0000102909', '00724F101', 'Common Stock',
             '0001104659-23-015203', '2023-02-09', '2022-12-30'),
    'GOOGL': ('0001652044', '0001364742', '02079K305', 'Class A Common Stock',
              '0001306550-23-005871', '2023-02-01', '2022-12-31'),
}


class CoverParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields = []
        self.contexts = {}
        self.context = None
        self.active = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'xbrli:context':
            self.context = attrs.get('id')
        if tag == 'ix:nonnumeric' and attrs.get('name', '').lower() in (
                'dei:tradingsymbol', 'dei:security12btitle', 'dei:entitycentralindexkey'):
            if self.active is not None:
                raise ValueError('Nested fact unsupported')
            self.active = (tag, attrs, [])
        elif tag == 'xbrli:identifier' and self.context:
            self.active = (tag, {'context': self.context, **attrs}, [])

    def handle_data(self, value):
        if self.active:
            self.active[2].append(value)

    def handle_endtag(self, tag):
        if self.active and tag == self.active[0]:
            _, attrs, values = self.active
            value = ' '.join(''.join(values).split())
            if tag == 'ix:nonnumeric':
                self.fields.append((attrs.get('name', '').lower(), attrs.get('contextref'), value))
            elif attrs.get('scheme') == 'http://www.sec.gov/CIK':
                self.contexts.setdefault(attrs['context'], []).append(value)
            self.active = None
        if tag == 'xbrli:context':
            self.context = None


def parse_cover(raw, row):
    parser = CoverParser()
    parser.feed(raw.decode('utf-8'))
    context = row['cover_context']
    for name, expected in [('dei:tradingsymbol', row['ticker']),
                           ('dei:security12btitle', row['cover_security_class_title'])]:
        values = [value for field, ctx, value in parser.fields if field == name and ctx == context]
        if values != [expected]:
            raise ValueError('Same-context ticker/class mismatch')
    if parser.contexts.get(context) != [row['subject_cik']]:
        raise ValueError('Same-context entity CIK mismatch')
    if {value for name, _, value in parser.fields if name == 'dei:entitycentralindexkey'} != {row['subject_cik']}:
        raise ValueError('Cover issuer mismatch')
    return {'context': context, 'ticker': row['ticker'], 'subject_cik': row['subject_cik'],
            'security_class_title': row['cover_security_class_title'], 'cusip_asserted_from_cover': False}


def inspect(row):
    t = row['ticker']
    actual = tuple(row[k] for k in ('subject_cik', 'reporter_cik', 'cusip', 'security_class',
                                    'accession', 'filing_date', 'event_date'))
    if actual != EXPECTED[t] or row['schema'] != 'TWO_SECURITY_WEB_FACT_TRANSCRIPTION_V1':
        raise ValueError('Observed identity coordinates differ')
    if any(row[k] is not False for k in FLAGS):
        raise ValueError('Observation upgraded beyond evidence')
    if row['tool_call_started_utc'] is not None or row['tool_call_completed_utc'] is not None or row['tool_clock_status'] != 'UNKNOWN_NOT_RECORDED':
        raise ValueError('Unknown tool clock must remain unknown')
    if row['accepted_timezone'] != 'UNKNOWN_NOT_IN_WEB_FIELD':
        raise ValueError('Web accepted field has no timezone')
    if row['filing_date'] >= '2023-03-31':
        raise ValueError('Window-prior observation required')


def verify(sources):
    for path, expected in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Source bytes changed')


def build():
    sources = {str(SOURCE): LOADED_SHA}
    verify(sources)
    def read(reference):
        path = Path(reference['path']).resolve()
        expected = reference['sha256']
        if str(path) in sources and sources[str(path)] != expected:
            raise ValueError('Conflicting source hash')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('External artifact/source hash mismatch')
        sources[str(path)] = expected
        return raw
    results = []
    for ticker, expected in ARTIFACTS.items():
        row = json.loads(read({'path': str(BASE / (ticker + '.json')), 'sha256': expected}))
        if row['ticker'] != ticker:
            raise ValueError('Artifact denominator mismatch')
        inspect(row)
        cover = parse_cover(read(row['cover_reference']), row)
        started = json.loads(read(row['failed_http_started_reference']))
        receipt = json.loads(read(row['failed_http_receipt_reference']))
        raw = read(row['failed_http_raw_reference'])
        if any(receipt.get(k) != v for k, v in started.items()):
            raise ValueError('Started/receipt mismatch')
        if (receipt['ticker'], receipt['url'], receipt['final_url'], receipt['status'], receipt['method'], receipt['attempt'], receipt['retries']) != (ticker, row['document_url'], row['document_url'], 403, 'GET', 1, 0):
            raise ValueError('Failed HTTP coordinates mismatch')
        if receipt['identity_admission_changed'] is not False or receipt['error'] is not None:
            raise ValueError('Receipt boundary mismatch')
        if Path(ROOT / receipt['raw_path']).resolve() != Path(row['failed_http_raw_reference']['path']).resolve() or receipt['raw_sha256'] != hashlib.sha256(raw).hexdigest() or receipt['raw_bytes'] != len(raw):
            raise ValueError('Failed-response bytes mismatch')
        times = [datetime.fromisoformat(receipt[k]) for k in ('started_at_utc', 'received_at_utc')]
        if any(d.tzinfo is None or d.utcoffset().total_seconds() != 0 for d in times) or times[1] < times[0]:
            raise ValueError('HTTP receipt clock invalid')
        results.append({'ticker': ticker, 'facts': row, 'parsed_original_cover': cover,
                        'local_http_status': 403, 'evidence_type': 'WEB_TOOL_FACT_TRANSCRIPTION_ONLY'})
    verify(sources)
    return {'schema': 'TWO_SECURITY_WEB_FACT_READBACK_V1', 'rows': results, 'security_count': 2,
            'source_hashes': sources, 'raw_http_original_verified_count': 0,
            'structural_byte_and_cover_readback_only': True, **dict.fromkeys(FLAGS, False)}


def publish(output):
    value = build()
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    verify(value['source_hashes'])
    with Path(output).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    verify(value['source_hashes'])
    if Path(output).read_bytes() != raw:
        raise ValueError('Published bytes differ')
    return {'path': str(Path(output).resolve()), 'sha256': hashlib.sha256(raw).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(publish(args.output)))

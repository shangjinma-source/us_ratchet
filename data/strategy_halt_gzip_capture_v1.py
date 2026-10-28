"""Fresh CBOE HTTP200 wire/entity evidence; unchanged halt eligibility review."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.request import Request, build_opener
from urllib.error import HTTPError

from core.strategy_account_ledger import canonical
from data.strategy_halt_gap_diagnostic_v1 import SOURCE_URL, require
from data.official_rss_gzip_transport_v1 import decode_wire, SAFE_HEADERS
from scripts.current_research_official_alert_capture import NoRedirect, MAX_BYTES

REQUEST_HEADERS = {'User-Agent': 'us-ratchet-halt-observation/1.0', 'Accept-Encoding': 'gzip'}


def fetch_halt_wire():
    try:
        response = build_opener(NoRedirect()).open(Request(SOURCE_URL, headers=REQUEST_HEADERS), timeout=8)
    except HTTPError as error:
        response = error
    with response:
        return dict(url=response.geturl(), status=response.code,
                    headers={key: response.headers.get(key) for key in SAFE_HEADERS},
                    body=response.read(MAX_BYTES + 1))


def aware(value):
    result = datetime.fromisoformat(value)
    require(result.utcoffset() is not None, 'HALT_GZIP_AWARE_CLOCK')
    return result


def validate_halt_encoding(result):
    files, pins = result['files'], result['source_hashes']
    proof_path = result['halt_encoding_proof_path']
    require(proof_path in files and pins.get(proof_path) == sha256(files[proof_path]).hexdigest(), 'HALT_GZIP_PROOF_HASH')
    proof = json.loads(files[proof_path])
    require(proof['schema'] == 'CBOE_HALT_WIRE_ENTITY_PROOF_V1'
            and proof['url'] == proof['response_url'] == SOURCE_URL
            and proof['http_status'] == 200 and proof['request_headers'] == REQUEST_HEADERS
            and set(proof['response_headers']) == set(SAFE_HEADERS)
            and proof['body_semantics'] == 'DECODED_CURRENT_HTTP_200_ENTITY_NOT_WIRE'
            and proof['cached'] is False, 'HALT_GZIP_PROOF_BINDING')
    for key in ('wire', 'decoded', 'receipt'):
        path = proof[key + '_path']
        require(path in files and pins.get(path) == proof[key + '_sha256'] == sha256(files[path]).hexdigest(), 'HALT_GZIP_CLOSURE_HASH')
    wire, entity = files[proof['wire_path']], files[proof['decoded_path']]
    require(len(wire) == proof['wire_bytes'] and len(entity) == proof['decoded_bytes']
            and decode_wire(wire, proof['response_headers']) == entity, 'HALT_GZIP_DECODE_BINDING')
    receipt = json.loads(files[proof['receipt_path']])
    require(result['halt_evidence'] == {'raw_path': proof['decoded_path'], 'receipt_path': proof['receipt_path']}
            and receipt['url'] == SOURCE_URL and receipt['http_status'] == 200
            and receipt['status'] == 'CAPTURED_PENDING_EXECUTION_REVIEW'
            and receipt['raw_sha256'] == proof['decoded_sha256'] and receipt['bytes'] == len(entity), 'HALT_GZIP_RECEIPT_BINDING')
    require(aware(receipt['started_at']) == aware(proof['started_at'])
            <= aware(proof['network_received_at']) == aware(receipt['received_at'])
            <= aware(proof['decoded_at']), 'HALT_GZIP_CLOCK_ORDER')
    return True


class HaltGzipMarketCaptureV1:
    def __init__(self, market, *, fetch=fetch_halt_wire, clock=None):
        self.market, self.fetch = market, fetch
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def capture(self, **kwargs):
        directory = Path(kwargs['output_directory'])
        evidence = directory.with_name(directory.name + '-halts')
        evidence.mkdir(parents=True, exist_ok=False)
        started = self.clock()
        receipt = dict(url=SOURCE_URL, started_at=started.isoformat(), status='FAILED')
        package = None

        def persist(name, raw):
            with (evidence/name).open('xb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            require((evidence/name).read_bytes() == raw, 'HALT_GZIP_READBACK')

        try:
            require(started.utcoffset() is not None, 'HALT_AWARE_CLOCK')
            response = self.fetch()
            received = self.clock()
            headers = {key: response.get('headers', {}).get(key) for key in SAFE_HEADERS}
            wire = response['body']
            require(type(wire) is bytes and 0 < len(wire) <= MAX_BYTES, 'HALT_GZIP_WIRE_BUDGET')
            persist('wire.bin', wire)
            persist('response.json', canonical(dict(url=response['url'], http_status=response['status'], headers=headers, network_received_at=received.isoformat(), request_headers=REQUEST_HEADERS)))
            require(response['url'] == SOURCE_URL and response['status'] == 200, 'HALT_GZIP_HTTP_BINDING')
            entity = decode_wire(wire, headers)
            decoded = self.clock()
            persist('source.raw', entity)
            receipt.update(received_at=received.isoformat(), http_status=200, bytes=len(entity), raw_sha256=sha256(entity).hexdigest(), status='CAPTURED_PENDING_EXECUTION_REVIEW')
            encoded = canonical(receipt)
            proof = dict(schema='CBOE_HALT_WIRE_ENTITY_PROOF_V1', url=SOURCE_URL, response_url=response['url'], http_status=200,
                         request_headers=REQUEST_HEADERS, response_headers=headers, started_at=started.isoformat(),
                         network_received_at=received.isoformat(), decoded_at=decoded.isoformat(),
                         wire_bytes=len(wire), decoded_bytes=len(entity), cached=False,
                         body_semantics='DECODED_CURRENT_HTTP_200_ENTITY_NOT_WIRE')
            package = {'files': {}, 'source_hashes': {}}
            for key, raw in (('wire', wire), ('decoded', entity), ('receipt', encoded)):
                digest = sha256(raw).hexdigest(); path = 'halt-source/' + digest + '.' + key
                proof[key+'_path'], proof[key+'_sha256'] = path, digest
                package['files'][path] = raw; package['source_hashes'][path] = digest
            raw_proof = canonical(proof); digest = sha256(raw_proof).hexdigest(); path = 'halt-source/' + digest + '.encoding.json'
            package['files'][path] = raw_proof; package['source_hashes'][path] = digest
            package['halt_encoding_proof_path'] = path
            package['halt_evidence'] = dict(raw_path=proof['decoded_path'], receipt_path=proof['receipt_path'])
            validate_halt_encoding(package)
            persist('encoding.json', raw_proof)
        except Exception as error:
            package = None
            code = str(error) if isinstance(error, ValueError) else ''
            receipt['status'] = 'FAILED'
            receipt['reason'] = code if code.startswith(('HALT_', 'RSS_')) and code.replace('_', '').isalnum() else 'HALT_CAPTURE_UNAVAILABLE'
        persist('receipt.json', canonical(receipt))
        # Exactly as V1: continue fresh market capture; failure cannot certify no halt.
        result = self.market.capture(**kwargs)
        if package is None:
            result['halt_capture_failure'] = receipt['reason']
            return result
        validate_halt_encoding(package)
        require(not (set(package['files']) & set(result['files'])) and not (set(package['files']) & set(result['source_hashes'])), 'HALT_SOURCE_COLLISION')
        result['files'].update(package['files']); result['source_hashes'].update(package['source_hashes'])
        result['halt_evidence'] = package['halt_evidence']
        result['halt_encoding_proof_path'] = package['halt_encoding_proof_path']
        return result

"""Explicit wire/entity proof for real HTTP200 RSS; no cache or retry."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import zlib
from urllib.request import Request, build_opener
from urllib.error import HTTPError
from scripts.current_research_official_alert_capture import URL, NoRedirect, MAX_BYTES

REQUEST_HEADERS = {'User-Agent': 'us-ratchet-official-alert-research/1.0', 'Accept': 'application/rss+xml,application/xml,text/xml', 'Accept-Encoding': 'gzip'}
SAFE_HEADERS = ('Content-Encoding', 'Content-Length', 'Content-Type', 'Date', 'Last-Modified', 'ETag', 'Cache-Control', 'Vary', 'Connection', 'Location')

def require(condition, reason):
    if not condition:
        raise ValueError(reason)

def decode_wire(wire, headers):
    require(type(wire) is bytes and 0 < len(wire) <= MAX_BYTES, 'RSS_WIRE_BUDGET')
    length = headers.get('Content-Length')
    require(length is None or str(length).isdigit() and int(length) == len(wire), 'RSS_WIRE_LENGTH_MISMATCH')
    encoding = headers.get('Content-Encoding')
    require(encoding in (None, '', 'identity', 'gzip'), 'RSS_ENCODING_UNSUPPORTED')
    if encoding != 'gzip':
        return wire
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        entity = decoder.decompress(wire, MAX_BYTES + 1)
        require(len(entity) <= MAX_BYTES and decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data, 'RSS_GZIP_INVALID_OR_OVERSIZE')
        entity += decoder.flush()
        require(0 < len(entity) <= MAX_BYTES, 'RSS_ENTITY_BUDGET')
        return entity
    except zlib.error as error:
        raise ValueError('RSS_GZIP_INTEGRITY_FAILED') from error

def fetch_wire():
    request = Request(URL, headers=REQUEST_HEADERS)
    try:
        response = build_opener(NoRedirect()).open(request, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        return {'status': response.code, 'url': response.geturl(), 'headers': {key: response.headers.get(key) for key in SAFE_HEADERS}, 'body': response.read(MAX_BYTES+1)}

def validate_proof(proof, wire, entity):
    require(proof.get('schema') == 'RSS_GZIP_WIRE_ENTITY_PROOF_V1', 'RSS_PROOF_SCHEMA')
    require(proof.get('http_status') == 200 and proof.get('url') == URL and proof.get('response_url') == URL, 'RSS_PROOF_HTTP')
    require(proof.get('request_headers') == REQUEST_HEADERS, 'RSS_PROOF_REQUEST')
    require(set(proof['response_headers']) == set(SAFE_HEADERS), 'RSS_PROOF_HEADERS')
    times = [datetime.fromisoformat(proof[key]) for key in ('started_at','network_received_at','decoded_at')]
    require(all(time.utcoffset() is not None for time in times) and times[0] <= times[1] <= times[2], 'RSS_PROOF_CLOCK')
    require(proof.get('wire_sha256') == sha256(wire).hexdigest() and proof.get('wire_bytes') == len(wire), 'RSS_PROOF_WIRE')
    require(proof.get('decoded_sha256') == sha256(entity).hexdigest() and proof.get('decoded_bytes') == len(entity), 'RSS_PROOF_ENTITY')
    require(decode_wire(wire, proof['response_headers']) == entity, 'RSS_PROOF_DECODE_MISMATCH')
    return True

class GzipRssTransport:
    def __init__(self, *, sink, fetch=fetch_wire, clock=None):
        self.sink, self.fetch = sink, fetch
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def __call__(self):
        started = self.clock()
        response = self.fetch()
        received = self.clock()
        require(response.get('status') == 200 and response.get('url') == URL, 'RSS_HTTP_200_SAME_URL_REQUIRED')
        wire = response['body']
        headers = {key: response.get('headers', {}).get(key) for key in SAFE_HEADERS}
        entity = decode_wire(wire, headers)
        proof = dict(schema='RSS_GZIP_WIRE_ENTITY_PROOF_V1', http_status=200, url=URL, response_url=response['url'],
            request_headers=deepcopy(REQUEST_HEADERS), response_headers=headers,
            started_at=started.isoformat(), network_received_at=received.isoformat(), decoded_at=self.clock().isoformat(),
            wire_bytes=len(wire), wire_sha256=sha256(wire).hexdigest(), decoded_bytes=len(entity), decoded_sha256=sha256(entity).hexdigest(),
            body_semantics='DECODED_CURRENT_HTTP_200_ENTITY_NOT_WIRE', cached=False, publication_modified=False)
        validate_proof(proof, wire, entity)
        self.sink(proof, wire, entity)
        return dict(status=200, url=URL, body=entity, headers=headers,
                    body_semantics=proof['body_semantics'], gzip_proof=proof, wire_body=wire)

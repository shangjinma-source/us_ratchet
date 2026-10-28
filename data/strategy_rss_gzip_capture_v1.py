"""Current-source gzip closures; old HTTP200 reviewers remain unchanged."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from core.strategy_account_ledger import canonical
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.strategy_account_action_capture_v6 import StrategyAccountActionCaptureV6
from data.official_rss_gzip_transport_v1 import GzipRssTransport, validate_proof, require

def attach_proof(result, records, *, legacy_timing_path=None):
    require(len(records) == 1, 'RSS_ENCODING_PROOF_REQUIRED')
    proof, wire, entity = records[0]
    validate_proof(proof, wire, entity)
    documents = result['documents'];receipt_path = documents['rss_receipt']
    receipt_raw = result['files'][receipt_path];receipt = json.loads(receipt_raw)
    require(entity == result['files'][documents['rss_raw']] and receipt['http_status'] == 200 and receipt['raw_sha256'] == sha256(entity).hexdigest(), 'RSS_ENCODING_CAPTURE_BINDING')
    proof = dict(proof, entity_receipt_path=receipt_path, entity_receipt_sha256=sha256(receipt_raw).hexdigest(),
                 decoded_path=documents['rss_raw'])
    proof['legacy_timing_path'] = legacy_timing_path
    if legacy_timing_path is not None:
        proof['legacy_timing_sha256'] = sha256(result['files'][legacy_timing_path]).hexdigest()
        proof['legacy_timing_interpretation'] = {
            'transport_received_at': 'DECODED_ADAPTER_RETURN_NOT_WIRE_ARRIVAL',
            'raw_modified_false': 'DECODED_XML_UNCHANGED_BY_LEGACY_VERIFIER',
            'wire_arrival_field': 'network_received_at'}
    wire_path = 'rss-wire/'+sha256(wire).hexdigest()+'.bin'
    proof['wire_path'] = wire_path
    proof_raw = canonical(proof);proof_path = 'rss-wire/'+sha256(proof_raw).hexdigest()+'.json'
    for path, raw in ((wire_path,wire),(proof_path,proof_raw)):
        require(path not in result['files'] or result['files'][path] == raw, 'RSS_ENCODING_PATH_CONFLICT')
        result['files'][path] = raw;result['source_hashes'][path] = sha256(raw).hexdigest()
    require(len(result['files']) <= 2000 and sum(map(len,result['files'].values())) <= 128*1024*1024, 'RSS_ENCODING_PACKAGE_BUDGET')
    result['rss_encoding_proof_path'] = proof_path
    validate_capture(result)
    return result

def validate_capture(result):
    path = result.get('rss_encoding_proof_path')
    require(path in result['files'], 'RSS_ENCODING_CLOSURE_MISSING')
    files=result['files'];pins=result['source_hashes'];proof=json.loads(files[path])
    for name in (path,proof['wire_path'],proof['decoded_path'],proof['entity_receipt_path']):
        require(name in files and pins.get(name)==sha256(files[name]).hexdigest(), 'RSS_ENCODING_CLOSURE_HASH')
    require(proof['decoded_path']==result['documents']['rss_raw'] and proof['entity_receipt_path']==result['documents']['rss_receipt'], 'RSS_ENCODING_DOCUMENT_BINDING')
    receipt_raw=files[proof['entity_receipt_path']];receipt=json.loads(receipt_raw)
    require(sha256(receipt_raw).hexdigest()==proof['entity_receipt_sha256'] and receipt['http_status']==200 and receipt['raw_sha256']==proof['decoded_sha256'], 'RSS_ENCODING_RECEIPT_BINDING')
    from datetime import datetime
    def aware(value):
        parsed = datetime.fromisoformat(value)
        require(parsed.utcoffset() is not None, 'RSS_ENCODING_AWARE_CLOCK')
        return parsed
    require(aware(receipt['started_at']) <= aware(proof['started_at'])
            <= aware(proof['network_received_at']) <= aware(proof['decoded_at'])
            <= aware(receipt['received_at']), 'RSS_ENCODING_RECEIPT_CLOCK')
    timing_path = proof['legacy_timing_path']
    if timing_path is not None:
        require(timing_path in files and pins.get(timing_path) == proof['legacy_timing_sha256']
                == sha256(files[timing_path]).hexdigest(), 'RSS_ENCODING_TIMING_HASH')
        timing = json.loads(files[timing_path])
        require(proof['legacy_timing_interpretation'] == {
            'transport_received_at': 'DECODED_ADAPTER_RETURN_NOT_WIRE_ARRIVAL',
            'raw_modified_false': 'DECODED_XML_UNCHANGED_BY_LEGACY_VERIFIER',
            'wire_arrival_field': 'network_received_at'}, 'RSS_ENCODING_TIMING_SEMANTICS')
        require(timing['schema'] == 'VERIFIED_RSS_TRANSPORT_TIME_V3'
                and timing['status'] == 'VERIFIED_BEFORE_CAPTURE_RETURN'
                and timing['raw_modified'] is False
                and timing['raw_sha256'] == proof['decoded_sha256']
                and timing['original_rss_receipt_path'] == proof['entity_receipt_path']
                and timing['original_rss_receipt_sha256'] == proof['entity_receipt_sha256']
                and timing['capture_received_at'] == receipt['received_at'], 'RSS_ENCODING_TIMING_BINDING')
        require(aware(receipt['started_at']) <= aware(timing['started_at']) <= aware(proof['started_at'])
                and aware(proof['decoded_at']) <= aware(timing['transport_received_at'])
                <= aware(timing['verified_at']) <= aware(receipt['received_at']), 'RSS_ENCODING_TIMING_CLOCK')
    validate_proof(proof,files[proof['wire_path']],files[proof['decoded_path']])
    return True

class GzipPaperActionSources(PaperActionEvidenceSources):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.encoding_records=[]
    def capture(self, request):
        # An instance is single-call; never reuse a cached body/proof as new transport.
        require(not self.encoding_records, 'RSS_ENCODING_CAPTURE_SINGLE_CALL')
        return attach_proof(super().capture(request),self.encoding_records)
    __call__=capture
    def read(self, request):
        return attach_proof(super().read(request),self.encoding_records)

class GzipActionCapture(StrategyAccountActionCaptureV6):
    def capture(self, request, output_directory):
        began=self.clock()
        records=[]
        transport=GzipRssTransport(sink=lambda *values:records.append(values),clock=self.clock)
        inner=StrategyAccountActionCaptureV6(fetch=self.fetch,rss_fetch=transport,clock=self.clock,max_workers=self.workers)
        result=inner.capture(request,output_directory)
        directory=Path(output_directory)
        legacy_complete=json.loads((directory/'complete-v6.json').read_bytes())
        require(legacy_complete['source_hashes'] == result['source_hashes']
                and legacy_complete['documents'] == result['documents'], 'RSS_ENCODING_LEGACY_COMPLETE')
        result=attach_proof(result,records,legacy_timing_path=legacy_complete['rss_timing_path'])
        for path in (result['rss_encoding_proof_path'],json.loads(result['files'][result['rss_encoding_proof_path']])['wire_path']):
            raw=result['files'][path];physical=directory/('gzip-'+result['source_hashes'][path]+'.bin')
            with physical.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            require(physical.read_bytes()==raw,'RSS_ENCODING_READBACK')
        validate_capture(result)
        marker=canonical(dict(schema='ACTION_GZIP_COMPLETE_V1',source_hashes=result['source_hashes'],rss_encoding_proof_path=result['rss_encoding_proof_path'],prior_complete_marker_internal_only=True))
        with (directory/'complete-gzip.pending.json').open('xb') as stream:stream.write(marker);stream.flush();os.fsync(stream.fileno())
        require((directory/'complete-gzip.pending.json').read_bytes()==marker,'RSS_ENCODING_MARKER_READBACK')
        require(0 <= (self.clock()-began).total_seconds() < 120,'RSS_ENCODING_CAPTURE_WINDOW_EXPIRED')
        (directory/'complete-gzip.pending.json').rename(directory/'complete-gzip.json')
        return result

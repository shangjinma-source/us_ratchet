"""Bounded independent single-member gzip / canonical JSON byte inspection.

No producer codec, evaluator, domain, filesystem or network helpers are called.
Any JSON return (including null) is retained; economic schema validation is later.
A successful report authenticates only supplied byte digests, not their provenance.
"""
import hashlib
import io
import json
import math
import re
import zlib

ENCODING=dict(json='UTF8_SORT_KEYS_COMPACT_ENSURE_ASCII_ALLOW_NAN_FALSE',gzip='GZIP_SINGLE_MEMBER',compresslevel=6,mtime=0,filename='')
KEYS={'schema','encoding','compressed_sha256','compressed_byte_count','uncompressed_sha256','uncompressed_byte_count'}
CHUNK_BYTES=65536


def require(ok,message):
    if not ok:raise ValueError(message)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf-8')

def checked_metadata(metadata,max_compressed_bytes,max_uncompressed_bytes,max_json_depth):
    for value in (max_compressed_bytes,max_uncompressed_bytes,max_json_depth):
        require(type(value)is int and value>0,'Explicit positive integer engineering limit')
    require(type(metadata)is dict and set(metadata)==KEYS,'Exact codec metadata fields')
    require(metadata['schema']=='DOUBLE_REPLACEMENT_CANONICAL_GZIP_V1','Codec schema')
    require(canonical(metadata['encoding'])==canonical(ENCODING),'Exact encoding values and types')
    for prefix,limit in (('compressed',max_compressed_bytes),('uncompressed',max_uncompressed_bytes)):
        size=metadata[prefix+'_byte_count'];digest=metadata[prefix+'_sha256']
        require(type(size)is int and 0<size<=limit,'Declared byte size exceeds engineering limit or has invalid type')
        require(type(digest)is str and re.fullmatch('[0-9a-f]{64}',digest),'Explicit original byte SHA256')
    return metadata['compressed_byte_count'],metadata['uncompressed_byte_count']

def depth_check(raw,limit):
    depth=0;quoted=False;escape=False
    for byte in raw:
        if quoted:
            if escape:escape=False
            elif byte==92:escape=True
            elif byte==34:quoted=False
        elif byte==34:quoted=True
        elif byte in (91,123):
            depth+=1;require(depth<=limit,'JSON nesting exceeds declared engineering limit')
        elif byte in (93,125):depth-=1
    # Syntax itself, matching bracket types and unterminated strings are decoded below.

def parse_canonical(raw,max_json_depth):
    depth_check(raw,max_json_depth)
    def unique(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON key including nested objects');result[key]=value
        return result
    def floating(token):
        value=float(token);require(math.isfinite(value),'Nonfinite JSON numeric overflow');return value
    def constant(token):raise ValueError('Nonfinite JSON token '+token)
    value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_float=floating,parse_constant=constant)
    offset=0
    encoder=json.JSONEncoder(sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
    for piece in encoder.iterencode(value):
        block=piece.encode('utf-8')
        require(raw[offset:offset+len(block)]==block,'Original JSON bytes are not canonical')
        offset+=len(block)
    require(offset==len(raw),'Strict canonical JSON EOF')
    return value

def read_gzip_raw(binary_stream,*,metadata,max_compressed_bytes,max_uncompressed_bytes,max_json_depth=128):
    """Read at most the declared compressed bytes plus one trailing-byte probe.

    zlib receives max_length=remaining+1, stopping inflated data before allocation
    can cross the declared raw length by more than one byte. No flush with an
    unbounded output allocation is used. The caller retains failed/partial input.
    """
    compressed_size,raw_size=checked_metadata(metadata,max_compressed_bytes,max_uncompressed_bytes,max_json_depth)
    expected_compressed_sha256=metadata['compressed_sha256'];expected_uncompressed_sha256=metadata['uncompressed_sha256']
    compressed_hash=hashlib.sha256();raw_hash=hashlib.sha256();count=0;output=bytearray();header=bytearray()
    decoder=zlib.decompressobj(16+zlib.MAX_WBITS)
    while True:
        request=min(CHUNK_BYTES,compressed_size-count+1)
        block=binary_stream.read(request)
        require(type(block)is bytes and len(block)<=request,'Bounded binary stream read contract')
        if not block:break
        count+=len(block);require(count<=compressed_size,'Compressed bytes exceed declared bound or trailing bytes')
        require(not decoder.eof,'Second gzip member or trailing garbage')
        compressed_hash.update(block)
        if len(header)<10:header.extend(block[:10-len(header)])
        if len(header)==10:
            require(bytes(header)==b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff','Fixed gzip header: no optional filename, time or flags')
        pending=block
        while pending:
            try:decoded=decoder.decompress(pending,raw_size-len(output)+1)
            except zlib.error as failure:raise ValueError('Invalid gzip stream, CRC or trailer')from failure
            require(len(output)+len(decoded)<=raw_size,'Inflation exceeds declared uncompressed bound')
            output.extend(decoded);raw_hash.update(decoded)
            require(not decoder.unused_data,'Second gzip member or trailing garbage')
            remainder=decoder.unconsumed_tail
            require(not remainder or len(remainder)<len(pending)or decoded,'Decompressor made no progress')
            pending=remainder
    require(count==compressed_size and compressed_hash.hexdigest()==expected_compressed_sha256,'Complete compressed bytes/SHA')
    require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,'Single complete gzip EOF/trailer required')
    require(len(output)==raw_size and raw_hash.hexdigest()==expected_uncompressed_sha256,'Complete uncompressed bytes/SHA')
    value=parse_canonical(output,max_json_depth)
    value_type='null'if value is None else'boolean'if type(value)is bool else'object'if type(value)is dict else'array'if type(value)is list else'string'if type(value)is str else'integer'if type(value)is int else'float'
    return dict(value=value,inspection=dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_RAW_BYTE_INSPECTION_V1',status='PASS_BYTES_ONLY',compressed_sha256=compressed_hash.hexdigest(),compressed_byte_count=count,uncompressed_sha256=raw_hash.hexdigest(),uncompressed_byte_count=len(output),json_top_level_type=value_type,single_gzip_member_verified=True,gzip_crc_and_eof_verified=True,canonical_json_verified=True,duplicate_json_keys_rejected=True,max_compressed_bytes=max_compressed_bytes,max_uncompressed_bytes=max_uncompressed_bytes,max_json_depth=max_json_depth,declared_compression_level=6,compression_level_independently_proven=False,source_bytes_provenance_authenticated=False,producer_codec_called=False,economic_schema_checked=False,economic_evaluation_verified=False,risk_recomputed=False,account_executed=False,orders_executed=False,point_in_time_verified=False,promotion_allowed=False))

def inspect_gzip_raw(*,compressed_bytes,metadata,max_compressed_bytes,max_uncompressed_bytes,max_json_depth=128):
    require(type(compressed_bytes)is bytes,'Original compressed bytes')
    checked_metadata(metadata,max_compressed_bytes,max_uncompressed_bytes,max_json_depth)
    require(len(compressed_bytes)==metadata['compressed_byte_count'],'Exact compressed bytes length')
    return read_gzip_raw(io.BytesIO(compressed_bytes),metadata=metadata,max_compressed_bytes=max_compressed_bytes,max_uncompressed_bytes=max_uncompressed_bytes,max_json_depth=max_json_depth)

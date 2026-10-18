"""Strict saved Sina JSONP parsing and overlap diagnostics; no IO or authority."""
import csv
import hashlib
import io
import json
import re
from datetime import date
from decimal import Decimal

EXACT_BANNER=b"/*<script>location.href='//sina.com';</script>*/\n"
MAX_RAW_BYTES=16*1024*1024
MAX_ROWS=20000
FIELDS=('Open','High','Low','Close','Volume')
KEYS={'Open':'o','High':'h','Low':'l','Close':'c','Volume':'v'}
FLAGS=dict.fromkeys(('observable_csv_derived','provider_basis_compatibility_verified','source_authenticity_verified','historical_source_lineage_verified','candidate_seal_allowed','cohort_registration_allowed','fresh_observation','point_in_time_verified','live_mutation_allowed','oos_recovery_completed'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encode(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def pairs(items):
    out={}
    for k,v in items:
        require(k not in out,'Duplicate JSON key');out[k]=v
    return out

def day(s):
    require(type(s) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}',s) is not None,'Canonical session')
    d=date.fromisoformat(s);require(d.weekday()<5,'Weekday session only');return s

def number(value):
    require(type(value) is str and 0<len(value)<=160,'Original numeric token or string')
    require(re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',value) is not None,'Strict numeric syntax')
    n=Decimal(value);require(n.is_finite() and abs(n.as_tuple().exponent)<=100,'Finite bounded number')
    text=format(n,'f')
    if '.' in text:text=text.rstrip('0').rstrip('.')
    return n,('0' if n==0 else text)

def numeric_row(values):
    parsed={k:number(values[k]) for k in FIELDS};n={k:v[0] for k,v in parsed.items()}
    require(n['Volume']>=0 and n['Volume']==n['Volume'].to_integral_value(),'Nonnegative integer volume')
    valid=all(n[k]>0 for k in FIELDS[:4]) and n['Low']<=min(n['Open'],n['Close'])<=max(n['Open'],n['Close'])<=n['High']
    return {k:v[1] for k,v in parsed.items()},valid

def baseline_rows(raw,scope_start):
    require(type(raw) is bytes and 0<len(raw)<=MAX_RAW_BYTES,'Bounded baseline bytes')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
    require(reader.fieldnames==['Date',*FIELDS],'Exact baseline headers')
    allrows=list(reader);require(0<len(allrows)<=MAX_ROWS,'Bounded baseline rows')
    previous='';scope=[]
    for index,row in enumerate(allrows):
        require(set(row)=={'Date',*FIELDS} and all(type(v) is str for v in row.values()),'Complete baseline row')
        d=day(row['Date']);require(d>previous,'Strict baseline dates');previous=d
        normalized,valid=numeric_row(row)
        if d>=scope_start:
            require(valid,'Required baseline OHLC invalid');scope.append(dict(session=d,original_data_row_index=index,original_row=row,normalized=normalized))
    require(len(scope)==65 and scope[0]['session']==scope_start,'Complete sealed 65-day scope')
    return scope

def inspect_response(*,raw_bytes,ticker,baseline_csv_bytes,scope_start='2026-07-01',target_session='2026-10-02'):
    require(ticker in ('QQQ','SPY'),'Fixed explicit ticker');day(scope_start);day(target_session)
    require(type(raw_bytes) is bytes and 0<len(raw_bytes)<=MAX_RAW_BYTES,'Bounded raw bytes')
    parsing_offset=len(EXACT_BANNER) if raw_bytes.startswith(EXACT_BANNER) else 0
    parsing_bytes=raw_bytes[parsing_offset:]
    text=parsing_bytes.decode('utf-8-sig',errors='strict')
    # This is a deliberately narrow whitelist, not JavaScript evaluation.
    match=re.fullmatch(r'\s*var\s+_\s*=\s*'+ticker+r'_day\s*\((\[.*\])\)\s*;?\s*',text,re.DOTALL)
    require(match is not None,'Unsupported JSONP envelope; retain raw and block')
    rows=json.loads(match.group(1),object_pairs_hook=pairs,parse_int=str,parse_float=str,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON token')))
    require(type(rows) is list and 0<len(rows)<=MAX_ROWS,'Bounded nonempty response rows')
    baseline=baseline_rows(baseline_csv_bytes,scope_start);require(baseline[-1]['session']<target_session,'New target after baseline')
    normalized=[];outside=[];previous=''
    for i,row in enumerate(rows):
        require(type(row) is dict and set(('d','o','h','l','c','v'))<=set(row),'All OHLCV fields mandatory; no imputation')
        d=day(row['d']);require(d>previous,'Unique ascending provider dates');previous=d
        values,valid=numeric_row({k:row[v] for k,v in KEYS.items()})
        if d>=scope_start:require(valid,'Required provider OHLC invalid')
        elif not valid:outside.append(dict(original_row_index=i,session=d,issue='OUTSIDE_REQUIRED_SCOPE_OHLC_INVALID',original_row=row))
        normalized.append(dict(session=d,original_row_index=i,original_row=row,normalized=values,normalized_row_sha256=sha(encode(dict(session=d,values=values)))))
    mapping={r['session']:r for r in normalized};missing=[];differences=[];overlap=[]
    for b in baseline:
        d=b['session']
        if d not in mapping:missing.append(d);continue
        new=mapping[d];fields=[f for f in FIELDS if b['normalized'][f]!=new['normalized'][f]]
        overlap.append(dict(session=d,baseline_row=b,provider_row=new,equal=not fields))
        if fields:differences.append(dict(session=d,fields=fields,baseline=b['normalized'],provider=new['normalized']))
    required_dates=[r['session'] for r in baseline]
    unexpected=[r['session'] for r in normalized if scope_start<=r['session']<=baseline[-1]['session'] and r['session'] not in required_dates]
    suffix=[r['session'] for r in normalized if r['session']>baseline[-1]['session']]
    return dict(schema='SINA_SAVED_DAY_OVERLAP_DIAGNOSTIC_V2',parsing_byte_offset=parsing_offset,parsing_bytes_sha256=sha(parsing_bytes),exact_banner_removed=bool(parsing_offset),banner_handling='ONLY_EXACT_OBSERVED_ASCII_BANNER_PREFIX_NO_SCRIPT_EVALUATION',ascii_only_response=raw_bytes.isascii(),ticker=ticker,target_session=target_session,scope_start=scope_start,raw_sha256=sha(raw_bytes),baseline_sha256=sha(baseline_csv_bytes),decoding='UTF8_STRICT_OPTIONAL_BOM',jsonp_envelope='EXPLICIT_VAR_UNDERSCORE_EQUALS_TICKER_DAY_CALL',raw_rows=rows,normalized_rows=normalized,baseline_scope=baseline,overlap=overlap,missing_baseline_sessions=missing,unexpected_prefix_sessions=unexpected,overlap_differences=differences,outside_scope_ohlc_diagnostics=outside,new_provider_sessions=suffix,target_row=mapping.get(target_session),future_sessions=[d for d in suffix if d>target_session],exact_single_new_target=suffix==[target_session],overlap_numeric_equal=not(missing or unexpected or differences),status='BLOCKED_PROVIDER_BASIS_COMPATIBILITY_NO_BRIDGE_AUTHORIZATION',**FLAGS)

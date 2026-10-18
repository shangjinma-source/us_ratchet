"""Select an original capture by manifest plus absolute raw path/SHA, without names."""
import hashlib,json,re
from pathlib import Path
from types import FunctionType
from backtest import ndx_simple_split_quote_guard_v2_research as previous
nominal=previous.nominal
registry=previous.registry
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(previous.__file__).resolve())}

def raw_identity(row):
    """Reject contradictory aliases; never let a fallback mask another raw binding."""
    paths=[row[k] for k in ('raw_path','response_path') if k in row]
    hashes=[row[k] for k in ('raw_sha256','response_sha256') if k in row]
    if not paths and not hashes:return None
    if not paths or not hashes or any(type(p) is not str or not Path(p).is_absolute() for p in paths):raise ValueError('Original absolute raw binding required')
    resolved={str(Path(p).resolve()) for p in paths}
    if len(resolved)!=1 or len(set(hashes))!=1:raise ValueError('Conflicting original raw path/SHA aliases')
    digest=hashes[0]
    if type(digest) is not str or re.fullmatch('[0-9a-f]{64}',digest) is None:raise ValueError('Original raw SHA required')
    return next(iter(resolved)),digest

def load_capture_by_raw(*,manifest_path,manifest_sha256,raw_path,raw_sha256,sources):
    requested=raw_identity(dict(raw_path=raw_path,raw_sha256=raw_sha256))
    manifest_path=Path(manifest_path).resolve()
    registry.merge_source(sources,manifest_path,manifest_sha256);nominal.verify({str(manifest_path):manifest_sha256})
    report=json.loads(manifest_path.read_bytes(),object_pairs_hook=nominal._unique_pairs)
    arrays=[report[k] for k in ('captures','probes') if k in report]
    if len(arrays)!=1 or type(arrays[0]) is not list:raise ValueError('Unique original capture array required')
    rows=[row for row in arrays[0] if (identity:=raw_identity(row)) is not None and identity[0]==requested[0]]
    if len(rows)!=1 or raw_identity(rows[0])!=requested:raise ValueError('Unique exact raw path/SHA capture required; ticker is not a selector')
    capture=rows[0]
    if capture.get('http_status')!=200:raise ValueError('Successful original provider capture required')
    for p,h in report.get('source_hashes',{}).items():registry.merge_source(sources,p,h)
    for p,h in LOADED.items():registry.merge_source(sources,p,h)
    path,digest=requested;registry.merge_source(sources,path,digest);nominal.verify(sources)
    raw=Path(path).read_bytes();counts=[capture[k] for k in ('raw_bytes','response_bytes') if k in capture]
    if not counts or any(type(n) is not int or n!=len(raw) for n in counts):raise ValueError('Original raw byte denominator differs')
    inferred='response_headers' not in capture
    encoding=('gzip' if raw[:2]==b'\x1f\x8b' else 'identity') if inferred else capture['response_headers'].get('Content-Encoding')
    decoded,evidence=previous.first_guard.decode_bound_raw(raw_path=path,raw_sha256=digest,content_encoding=encoding)
    if 'decoded_sha256' in capture and capture['decoded_sha256']!=evidence['decoded_sha256']:raise ValueError('Original decoded bytes differ')
    evidence['encoding_inferred_from_bytes_missing_original_header']=inferred
    request=dict(capture['request']) if 'request' in capture else dict(method=capture.get('request_method'),url=capture.get('request_url'),credentials_sent=capture.get('credentials_sent'))
    if request.get('url') is None or capture.get('received_at_utc') is None:raise ValueError('Original exact request and receipt required; saved time is not receipt')
    return decoded,capture,request,evidence

def reconstruct_raw_addressed_nominal_quote(*,provider_manifest_path,provider_manifest_sha256,raw_path,raw_sha256,ticker,calendar,quote_field_basis):
    nominal.verify(LOADED);captured_sources=[]
    def locate(*,manifest_path,manifest_sha256,capture_name,sources):
        if capture_name is not None:raise ValueError('Named lookup is not part of this interface')
        captured_sources.append(sources)
        return load_capture_by_raw(manifest_path=manifest_path,manifest_sha256=manifest_sha256,
          raw_path=raw_path,raw_sha256=raw_sha256,sources=sources)
    # Private function globals: no mutation of the sealed v2 module or original manifests.
    function=previous.reconstruct_registry_guarded_nominal_quote
    bound=FunctionType(function.__code__,dict(function.__globals__,load_capture=locate),function.__name__,function.__defaults__,function.__closure__)
    try:
        result=bound(provider_manifest_path=provider_manifest_path,provider_manifest_sha256=provider_manifest_sha256,
          capture_name=None,ticker=ticker,calendar=calendar,quote_field_basis=quote_field_basis)
        result['schema']='ndx_simple_split_quote_guard_research_v3'
        result['original_capture_reference']=dict(manifest_path=str(Path(provider_manifest_path).resolve()),manifest_sha256=provider_manifest_sha256,
          raw_path=str(Path(raw_path).resolve()),raw_sha256=raw_sha256,selector='EXACT_ABSOLUTE_RAW_PATH_AND_SHA_WITHIN_BOUND_MANIFEST')
        result['original_capture_names_synthesized']=False
        result['private_binding_only_replaces_capture_lookup']=True
        return result
    finally:
        nominal.verify(LOADED)
        for sources in captured_sources:nominal.verify(sources)

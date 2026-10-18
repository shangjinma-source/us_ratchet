"""Only the two fixed history-V1 diagnostic files may occur in a source closure.

This helper never loads successful role inputs and never authenticates a failed
run as successful. Its exception is restricted to hash-guarding saved lineage.
"""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'data/cache/research/multidecision_scoring_history_independent_readback_20261003_v1'
PINS={str(DIRECTORY/'started.json'):'83ecfa1d364bf61076201f2d2f3ff2d899face05d299786450eba84dbc796190',str(DIRECTORY/'failure.json'):'5ca4968e8e86fa903d4062e22cab2ac57159ecb684969b363995840f83c69b0b'}
AUDIT=ROOT/'data/cache/research/multidecision_scoring_history_independent_readback_20261003_v2/independent_readback.json'
AUDIT_SHA='a338dbbdfa4bc7ffdc6e83ee93bc6e55802201dd7f18049d398ae394029a5b1a'
READER_SHA='6ae5ca2c757badd0ebfa2fa35bf3550584b4a989155e44e7d7fd120ca61f6703'
OLD_READER_SHA='0a4366d7bc4c933cac030818efccb8d963b0b15dfe7482dc7775d524642ee1be'

def require(ok,message):
    if not ok:raise ValueError(message)
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def read_bound(path,digest):
    raw=Path(path).read_bytes();require(hashlib.sha256(raw).hexdigest()==digest,'Fixed history lineage bytes changed');return json.loads(raw)

def diagnostic_members(sources):
    require(type(sources) is dict,'Explicit source closure')
    present=set(sources)&set(PINS)
    if not present:return frozenset()
    require(present==set(PINS) and all(sources[path]==digest for path,digest in PINS.items()),'Both exact diagnostic file bindings required')
    require(sources.get(str(AUDIT))==AUDIT_SHA,'Successful history-V2 audit must anchor diagnosis')
    require(not (AUDIT.parent/'failure.json').exists(),'History V2 successful role failed')
    require({p.name for p in DIRECTORY.iterdir()}=={'started.json','failure.json'} and all(p.is_file() and not p.is_symlink() for p in DIRECTORY.iterdir()),'Exact immutable two-file diagnostic namespace')
    started=read_bound(DIRECTORY/'started.json',PINS[str(DIRECTORY/'started.json')]);failure=read_bound(DIRECTORY/'failure.json',PINS[str(DIRECTORY/'failure.json')]);audit=read_bound(AUDIT,AUDIT_SHA)
    require(audit['schema']=='MULTIDECISION_SCORING_HISTORY_INDEPENDENT_READBACK_V2' and audit['status']=='PASS' and audit['reader_sha256']==READER_SHA and audit['previous_failed_counts_reused'] is False,'Diagnostic-only lineage in successful V2')
    for role in ('started','failure'):
        path=str(DIRECTORY/(role+'.json'));require(audit['previous_failed_attempt_references'][role]==dict(path=path,sha256=PINS[path]),'V2 anchors exact diagnostic roles')
        require(audit['source_hashes'].get(path)==PINS[path],'Successful audit covers diagnostics')
    expected=dict(completed_channel_count=6,remaining_channel_count=71,error='Reference',error_type='ValueError',retry_allowed=False,status='FAILED_DO_NOT_CONSUME')
    require(encode(failure)==encode(expected),'Failure semantics unchanged')
    require(started['schema']=='MULTIDECISION_SCORING_HISTORY_READBACK_STARTED_V1' and started['reader_sha256']==OLD_READER_SHA and started['retry_allowed'] is False,'Original failed reader identity')
    require(started['index_reference']==audit['index_reference'] and started['publication_reference']==audit['publication_reference'],'Same original history references')
    return frozenset(PINS)

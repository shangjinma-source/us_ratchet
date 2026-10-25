"""Immutable research observations with copied source bytes, never trade P&L."""
from hashlib import sha256
import json
from pathlib import Path
from core.strategy_account_ledger import require
from data.strategy_daily_advice_journal_v1 import encoded


def _safe(path):
    require(not path.is_symlink() and not any(p.is_symlink() for p in path.parents),'FOLLOWUP_STORE_SYMLINK')


def _save(path,raw):
    _safe(path);path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('xb') as stream:stream.write(raw)
    except FileExistsError:
        require(path.stat().st_size<=64*1024*1024 and path.read_bytes()==raw,'FOLLOWUP_STORE_CONFLICT')


def publish(directory, *, rows, sources):
    directory=Path(directory).absolute();_safe(directory)
    require(0<len(rows)<=1000 and 0<len(sources)<=5000,'FOLLOWUP_STORE_DOMAIN')
    require(all(type(body)is bytes for body in sources.values()) and sum(map(len,sources.values()))<=64*1024*1024,
            'FOLLOWUP_STORE_SOURCE_BUDGET')
    pins={name:sha256(body).hexdigest() for name,body in sources.items()}
    source_hashes=set(pins.values());ids=[]
    for row in rows:
        key=row['observation_id']
        require(type(key)is str and len(key)==64 and all(c in '0123456789abcdef' for c in key),'FOLLOWUP_STORE_KEY')
        require(row['status']=='CONDITIONAL_PRICE_OBSERVATION' and row['actual_fill_inferred'] is False and
            row['performance_computed'] is False,'FOLLOWUP_STORE_NOT_TRADES')
        require(row['daily_sha256'] in source_hashes and row['official_sha256'] in source_hashes,'FOLLOWUP_STORE_RAW_SOURCE_MISSING')
        ids.append(key)
    require(len(ids)==len(set(ids)),'FOLLOWUP_STORE_DUPLICATE')
    manifest=dict(schema='DAILY_FOLLOWUP_REVIEW_ARCHIVE_V1',rows=sorted(rows,key=lambda row:row['observation_id']),
        sources=pins,performance_computed=False)
    raw=encoded(manifest);digest=sha256(raw).hexdigest();folder=directory/'bundles'/digest
    # Check conflicts before publishing anything. Same price under a different
    # source capture still needs an explicit reconciliation, never replacement.
    for key in ids:
        index=directory/'index'/(key+'.json');_safe(index)
        if index.exists():require(index.read_bytes()==encoded(dict(manifest_sha256=digest)),'FOLLOWUP_OBSERVATION_ALREADY_PUBLISHED')
    for name,body in sources.items():_save(directory/'sources'/(pins[name]+'.bin'),body)
    _save(folder/'manifest.json',raw)
    _save(folder/'complete.json',encoded(dict(manifest_sha256=digest,observations=len(rows))))
    for key in ids:_save(directory/'index'/(key+'.json'),encoded(dict(manifest_sha256=digest)))
    return dict(status='RESEARCH_OBSERVATIONS_ARCHIVED',manifest_sha256=digest,observations=len(rows),account_writes=False)


def read_observation(directory, observation_id):
    directory=Path(directory).absolute();_safe(directory)
    require(type(observation_id)is str and len(observation_id)==64 and all(c in '0123456789abcdef' for c in observation_id),'FOLLOWUP_STORE_KEY')
    def read(path,limit):
        _safe(path);require(path.stat().st_size<=limit,'FOLLOWUP_STORE_SIZE');return path.read_bytes()
    index=json.loads(read(directory/'index'/(observation_id+'.json'),4096));digest=index['manifest_sha256']
    require(type(digest)is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'FOLLOWUP_STORE_HASH')
    folder=directory/'bundles'/digest;raw=read(folder/'manifest.json',4*1024*1024)
    require(sha256(raw).hexdigest()==digest,'FOLLOWUP_STORE_MANIFEST_CHANGED')
    manifest=json.loads(raw);complete=json.loads(read(folder/'complete.json',4096))
    require(complete==dict(manifest_sha256=digest,observations=len(manifest['rows'])),'FOLLOWUP_STORE_INCOMPLETE')
    total=0
    for pin in set(manifest['sources'].values()):
        require(type(pin)is str and len(pin)==64 and all(c in '0123456789abcdef' for c in pin),'FOLLOWUP_STORE_SOURCE_HASH')
        body=read(directory/'sources'/(pin+'.bin'),64*1024*1024);total+=len(body)
        require(total<=64*1024*1024 and sha256(body).hexdigest()==pin,'FOLLOWUP_STORE_SOURCE_CHANGED')
    found=[row for row in manifest['rows'] if row['observation_id']==observation_id]
    require(len(found)==1,'FOLLOWUP_STORE_ROW_MISSING')
    return found[0]

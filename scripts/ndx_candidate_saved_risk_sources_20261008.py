"""Read-only candidate account source closure; no financial projection imports."""
import hashlib,json,os,re,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
LINEAGE=ROOT/'backtest/ndx_history_failed_lineage_guard_20261008.py'
LINEAGE_SHA='fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
INDICES=(8,10,12,14)


def safe(path):
    path=Path(path)
    for item in (path,*path.parents):
        if item.is_symlink()or getattr(item,'is_junction',lambda:False)():raise ValueError('No linked source or output')
    return path

def require(value, message):
    if not value:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def exact(left, right):
    require(encode(left) == encode(right), 'Exact saved evidence')


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def reference(path, digest):
    require(type(digest) is str and re.fullmatch('[a-f0-9]{64}', digest), 'Pending source pin')
    require(type(path) is str and Path(path).is_absolute(), 'Absolute source path')
    return dict(path=path, sha256=digest)


def merge(sources, item):
    require(type(item) is dict and set(item) == {'path', 'sha256'}, 'Exact reference fields')
    reference(item['path'], item['sha256'])
    require(item['path'] not in sources or sources[item['path']] == item['sha256'], 'Conflicting source SHA')
    sources[item['path']] = item['sha256']


def decode(blob):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(blob, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def load(item, sources, *, body=True):
    merge(sources, item)
    path = safe(item['path'])
    require(not (path.parent / 'failure.json').exists(), 'Failed successful-role source')
    blob = path.read_bytes()
    require(sha(blob) == item['sha256'], 'Consumed source bytes')
    return decode(blob) if body else blob


def private_module(path, blob):
    module = types.ModuleType('_private_presentation_' + Path(path).stem)
    module.__file__ = str(path)
    exec(compile(blob, str(path), 'exec'), module.__dict__)
    return module


def guard(sources, inventories, helper):
    require(sha(SOURCE.read_bytes()) == LOADED, 'Loaded publisher drift')
    diagnostics = helper.diagnostic_members(sources)
    for name, digest in sources.items():
        path = safe(name)
        require(name in diagnostics or not (path.parent / 'failure.json').exists(), 'Failed source closure')
        actual = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1048576), b''):
                actual.update(block)
        require(actual.hexdigest() == digest, 'Source closure drift: ' + name)
    for directory, expected in inventories.items():
        actual = {str(safe(p).resolve()) for p in Path(directory).rglob('*') if p.is_file()}
        require(actual == set(expected), 'Exact source inventory: ' + directory)

def save(path, value):
    blob = encode(value)
    with path.open('xb') as stream:
        stream.write(blob)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == blob, 'Durable output bytes')
    return reference(str(path), sha(blob))


def prepare(refs):
    require(set(refs)=={stage+suffix for stage in ('inputs','execution')for suffix in ('','_publication','_audit','_reader')},'Exact eight candidate source roles')
    sources={str(SOURCE):LOADED};inventories={};audit_starts=[]
    helper=private_module(LINEAGE,load(reference(str(LINEAGE),LINEAGE_SHA),sources,body=False))
    docs={key:load(item,sources,body=not key.endswith('_reader'))for key,item in refs.items()}
    selected={};blocked=[]
    for stage in ('inputs','execution'):
        doc,pub,audit=(docs[stage+suffix]for suffix in ('','_publication','_audit'))
        role='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS'if stage=='inputs'else'MULTIDECISION_ACCOUNT_EXECUTION'
        key='inputs_reference'if stage=='inputs'else'result_reference'
        require(pub['schema']==role+'_PUBLICATION_V1'and audit['schema']==role+'_INDEPENDENT_READBACK_V1','Original source roles')
        require(doc['schema']==role+('_DOCUMENT_V1'if stage=='inputs'else'_RESULT_V1'),'Original input/result document role')
        require(pub['status']==('PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS'if stage=='inputs'else'PUBLISHED_CONDITIONAL_ACCOUNT_RETURNS_PENDING_INDEPENDENT_READBACK'),'Original publication boundary')
        require(audit['status']=='PASS'and audit['reader_sha256']==refs[stage+'_reader']['sha256'],'Original independent PASS')
        exact(pub[key],refs[stage]);exact(audit[key],refs[stage]);exact(audit['publication_reference'],refs[stage+'_publication'])
        exact(pub['source_hashes'],doc['source_hashes'])
        for item in (doc,pub,audit):
            require(item['point_in_time_verified']is False and item['promotion_allowed']is False,'No parent promotion')
            for name,digest in item['source_hashes'].items():merge(sources,reference(name,digest))
            for directory,names in item.get('source_inventories',{}).items():
                require(directory not in inventories or set(inventories[directory])==set(names),'Consistent upstream inventory')
                inventories[directory]=names
        for item in (refs[stage],refs[stage+'_publication'],refs[stage+'_reader']):
            require(audit['source_hashes'].get(item['path'])==item['sha256'],'Audited direct source')
        parent=Path(refs[stage]['path']).parent
        expected={str(parent/name)for name in (Path(refs[stage]['path']).name,'publication.json','started.json')}
        startref=pub['started_reference'];exact(startref['path'],str(parent/'started.json'))
        start=load(startref,sources);exact(start['source_hashes'],doc['source_hashes'])
        auditroot=Path(refs[stage+'_audit']['path']).parent;path=auditroot/'started.json'
        observed=reference(str(path),sha(safe(path).read_bytes()));audit_starts.append(observed)
        auditstart=load(observed,sources);exact(auditstart[key],refs[stage]);exact(auditstart['publication_reference'],refs[stage+'_publication'])
        inventories[str(auditroot)]=[str(auditroot/name)for name in ('started.json','independent_readback.json')]
        if stage=='execution':
            wanted=dict(inputs=refs['inputs'],publication=refs['inputs_publication'],readback=refs['inputs_audit'],reader=refs['inputs_reader'])
            exact(doc['input_references'],wanted);exact(pub['input_references'],wanted)
            require(doc['failure']is None and len(doc['rows'])==len(audit['rows'])==16,'All sixteen original track positions')
            for index,(entry,checked)in enumerate(zip(doc['rows'],audit['rows'])):
                exact(entry['track_index'],index);exact(checked['track_index'],index)
                exact(checked['coordinate'],[entry['fx_mode'],entry['lane'],entry['track']]);exact(checked['outcome'],entry['outcome'])
                if entry['outcome']=='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT':
                    require(entry['call_invoked']is False and entry['raw_reference']is None and type(entry['returned_call_count'])is int and entry['returned_call_count']==0,'Blocked track has no fabricated RAW');blocked.append(index)
                loaded={}
                for name,filename in (('started_reference','started.json'),('postcheck_reference','postcheck.json'),('raw_reference','raw_result.json')):
                    item=entry[name];exact(checked['saved_references'][name],item)
                    if item is None:
                        require(name=='raw_reference'and index in blocked,'Only blocked RAW absence');continue
                    exact(item['path'],str(parent/'tracks'/f'{index:02d}'/filename))
                    require(audit['source_hashes'].get(item['path'])==item['sha256'],'Original audited track SHA')
                    expected.add(item['path']);merge(sources,item)
                    # Only four requested RAW bodies are materialized; every
                    # other original track file remains SHA/inventory guarded.
                    if index in INDICES:loaded[name]=load(item,sources)
                if index in INDICES:
                    require(entry['track']=='CONTINUOUS'and entry['call_invoked']is True and type(entry['returned_call_count'])is int and entry['returned_call_count']==1,'Original returned continuous path')
                    require(checked['inspection']['status']=='PASS','Original saved account independent PASS')
                    raw=loaded['raw_reference'];require(raw['error']is None and raw['returned']is True and raw['original_return_is_json']is True,'Original successful JSON return')
                    exact(raw['started_reference'],entry['started_reference'])
                    selected[index]=dict(entry=entry,raw=raw)
        inventories[str(parent)]=sorted(expected)
    require(len(blocked)==8 and set(selected)==set(INDICES),'Exact four diagnostic paths and eight blocked tracks')
    require(len(docs['inputs']['inputs']['rows'])==8,'Original eight input coordinates')
    arguments=[]
    for index in INDICES:
        entry=selected[index]['entry'];row=docs['inputs']['inputs']['rows'][index//2];track=row['tracks'][0]
        exact([row['fx_mode'],row['lane'],track['track']],[entry['fx_mode'],entry['lane'],'CONTINUOUS'])
        arguments.append(dict(track_index=index,coordinate=[entry['fx_mode'],entry['lane'],entry['track']],
            raw_reference=entry['raw_reference'],started_reference=entry['started_reference'],postcheck_reference=entry['postcheck_reference'],
            stateful_input_reference=refs['inputs'],stateful_input_tokens=['inputs','rows',index//2,'tracks',0,'stateful_input'],
            raw_daily_base_tokens=['result'],stateful_input=track['stateful_input'],daily=selected[index]['raw']['result']['daily']))
    guard(sources,inventories,helper)
    return dict(references=refs,sources=sources,inventories=inventories,lineage_helper=helper,
                paths=arguments,blocked_track_indices=blocked,observed_audit_started_references=audit_starts)


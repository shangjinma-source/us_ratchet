"""Read-only complete byte closure for two independently audited projections."""
import hashlib,json,os,re,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
LINEAGE=ROOT/'backtest/ndx_history_failed_lineage_guard_20261008.py'
LINEAGE_SHA='fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'


def require(value,message):
    if not value:raise ValueError(message)


def sha(blob):return hashlib.sha256(blob).hexdigest()


def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def exact(a,b):require(encode(a)==encode(b),'Exact original evidence')


def reference(path,digest):
    require(type(path)is str and Path(path).is_absolute(),'Absolute source path')
    require(type(digest)is str and re.fullmatch('[0-9a-f]{64}',digest),'Pending immutable source pin')
    return dict(path=path,sha256=digest)


def merge(sources,ref):
    require(type(ref)is dict and set(ref)=={'path','sha256'},'Exact reference fields')
    reference(ref['path'],ref['sha256']);require(ref['path']not in sources or sources[ref['path']]==ref['sha256'],'Conflicting source SHA')
    sources[ref['path']]=ref['sha256']


def decode(blob):
    def pairs(items):
        out={}
        for key,value in items:require(key not in out,'Duplicate JSON key');out[key]=value
        return out
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def safe(path):
    path=Path(path)
    require(not any(p.is_symlink()or(p.exists()and p.stat().st_file_attributes&1024)for p in (path,*path.parents)),'No symlink/reparse source')
    return path


def load(ref,sources,body=True):
    merge(sources,ref);path=safe(ref['path']);require(not(path.parent/'failure.json').exists(),'Failed successful-role source')
    blob=path.read_bytes();require(sha(blob)==ref['sha256'],'Bound source bytes');return decode(blob)if body else blob


def module(path,blob):
    result=types.ModuleType('_chain_'+Path(path).stem);result.__file__=str(path)
    exec(compile(blob,str(path),'exec'),result.__dict__);return result


def guard(sources,inventories,helper):
    require(sha(SOURCE.read_bytes())==LOADED,'Loaded IO source drift');diagnostics=helper.diagnostic_members(sources)
    for name,digest in sources.items():
        path=safe(name);require(name in diagnostics or not(path.parent/'failure.json').exists(),'Failed source closure')
        with path.open('rb')as stream:
            checksum=hashlib.file_digest(stream,'sha256').hexdigest()
        require(checksum==digest,'Source closure drift: '+name)
    for directory,expected in inventories.items():
        actual={str(safe(p).resolve())for p in safe(directory).rglob('*')if p.is_file()}
        require(actual==set(expected),'Exact source inventory: '+directory)


def prepare(refs):
    require(set(refs)=={r+s for r in ('supplement','diagnostics')for s in ('','_publication','_audit','_reader')},'Exact eight source roles')
    for item in refs.values():reference(item['path'],item['sha256'])
    sources={str(SOURCE):LOADED};inventories={};documents={};observed=[]
    helper=module(LINEAGE,load(reference(str(LINEAGE),LINEAGE_SHA),sources,False))
    specifications=[('supplement','MULTIDECISION_HOLDINGS_SUPPLEMENT','PASS_SAVED_HOLDINGS_PROJECTION','PUBLISHED_SAVED_HOLDINGS_PENDING_INDEPENDENT_READBACK'),('diagnostics','CANDIDATE_SAVED_RISK_DIAGNOSTIC','PASS','PUBLISHED_DERIVED_DIAGNOSTIC_NOT_ORIGINAL_RISK_PENDING_READBACK')]
    for role,prefix,status,published in specifications:
        doc=load(refs[role],sources);pub=load(refs[role+'_publication'],sources);audit=load(refs[role+'_audit'],sources)
        load(refs[role+'_reader'],sources,False)
        require(doc['schema']==prefix+'_DOCUMENT_V1'and pub['schema']==prefix+'_PUBLICATION_V1','Exact document roles')
        require(pub['status']==published and audit['schema']==prefix+'_INDEPENDENT_READBACK_V1'and audit['status']==status,'Successful independent audit required')
        exact(pub[role+'_reference'],refs[role]);exact(audit[role+'_reference'],refs[role]);exact(audit['publication_reference'],refs[role+'_publication'])
        exact(audit['reader_sha256'],refs[role+'_reader']['sha256'])
        for value in (doc,pub,audit):
            require(value['point_in_time_verified']is False and value['promotion_allowed']is False,'Original authority boundary')
            for name,digest in value['source_hashes'].items():merge(sources,reference(name,digest))
            for directory,names in value.get('source_inventories',{}).items():
                require(directory not in inventories or set(inventories[directory])==set(names),'Conflicting source inventory');inventories[directory]=names
        for key in (role,role+'_publication',role+'_reader'):
            require(audit['source_hashes'].get(refs[key]['path'])==refs[key]['sha256'],'Audited direct source identity')
        parent=Path(refs[role]['path']).parent;exact(doc['started_reference'],pub['started_reference'])
        exact(doc['started_reference']['path'],str(parent/'started.json'));start=load(doc['started_reference'],sources)
        exact(start['source_hashes'],doc['source_hashes']);exact(start['input_references'],doc['input_references'])
        inventories[str(parent)]=[str(parent/name)for name in ('started.json',role+'.json','publication.json')]
        audit_parent=Path(refs[role+'_audit']['path']).parent
        auditstart=reference(str(audit_parent/'started.json'),sha((audit_parent/'started.json').read_bytes()))
        started=load(auditstart,sources);observed.append(auditstart)
        if role=='supplement':
            exact(started['artifact_references'][role],refs[role]);exact(started['artifact_references']['publication'],refs[role+'_publication'])
        else:
            exact(audit['started_reference'],auditstart);exact(started['diagnostics_reference'],refs[role]);exact(started['publication_reference'],refs[role+'_publication'])
        inventories[str(audit_parent)]=[str(audit_parent/name)for name in ('started.json','independent_readback.json')]
        documents[role]=doc
    guard(sources,inventories,helper)
    return dict(documents=documents,sources=sources,inventories=inventories,helper=helper,observed_audit_starts=observed)


def save(path,value):
    with safe(path).open('xb')as stream:stream.write(encode(value));stream.flush();os.fsync(stream.fileno())
    return reference(str(path),sha(path.read_bytes()))

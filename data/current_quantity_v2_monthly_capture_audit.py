"""Append-only local capture evidence. No execution authority or source fetching."""
from datetime import timezone
from hashlib import sha256
from pathlib import Path
from uuid import UUID,uuid4
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_service import document
from data.current_quantity_v2_difference_plan import require,stamp
from data.current_research_intraday_journal import _publish

LIMIT=4*1024*1024
EVENT_LIMIT=64*1024
TOTAL_LIMIT=128*1024*1024
EVENT_TOTAL_LIMIT=8*1024*1024


def safe_reason(error):
    known={'CAPTURE_SUPERSEDED','REGISTERED_SOURCE_CHANGED','SAVED_PACKAGE_CHANGED',
           'RAW_QUOTE_BYTES_REQUIRED','MONTHLY_REVIEW_DOCUMENT_FIELDS','DECISION_BINDING_MISMATCH'}
    if isinstance(error,ValueError) and str(error) in known:return str(error)
    for kind,code in ((TimeoutError,'CAPTURE_TIMEOUT'),(OSError,'CAPTURE_IO_ERROR'),
                      (ValueError,'CAPTURE_VALIDATION_FAILED'),(KeyError,'CAPTURE_FIELD_MISSING'),
                      (TypeError,'CAPTURE_TYPE_INVALID')):
        if isinstance(error,kind):return code
    return 'CAPTURE_INTERNAL_FAILURE'


def checked(root,path):
    root=Path(root).absolute()
    require(not root.is_symlink(),'STORAGE_SYMLINK')
    require(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),'STORAGE_PATH_ESCAPE')
    # Reject interior symlinks even when their target remains inside storage.
    for parent in path.parents:
        if parent==root:break
        require(not parent.is_symlink(),'STORAGE_SYMLINK')
    return path


def bounded(path,limit=LIMIT):
    require(path.stat().st_size<=limit,'CAPTURE_AUDIT_SIZE_LIMIT')
    with path.open('rb') as source:raw=source.read(limit+1)
    require(len(raw)<=limit,'CAPTURE_AUDIT_SIZE_LIMIT')
    return raw


def publish_blob(root,raw,limit):
    """Reuse verified immutable bytes; missing blobs retain durable create-only writes."""
    require(type(raw)is bytes and len(raw)<=limit,'CAPTURE_AUDIT_SIZE_LIMIT')
    digest=sha256(raw).hexdigest()
    target=checked(root,Path(root)/'blobs'/digest)
    if target.exists():
        require(bounded(target,limit)==raw,'OBSERVATION_CREATE_ONLY_CONFLICT')
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        # _publish compares exact bytes if another writer wins this creation.
        _publish(target,raw)
    return digest


def validate_genesis_context(binding,context):
    require(type(context)is dict and set(context)=={'capital_decision','account_state','genesis_declaration'},'GENESIS_AUDIT_CONTEXT_REQUIRED')
    decision=context['capital_decision'];account=context['account_state'];genesis=context['genesis_declaration']
    require(decision['decision_id']==genesis['decision_id']==binding['decision_id']
        and decision['research_id']==genesis['research_id']==binding['research_id']
        and account['account_id']==genesis['account_id']==binding['account_id']
        and account['revision']==decision['state_revision']==genesis['capital_origin_revision']==binding['state_revision']
        and account['cash']==decision['available_cash']==genesis['initial_cash_exact']==binding['initial_cash_exact']
        and account['shares']=={} and account['open_orders']==[] and account['reserved_cash']=='0'
        and account['reserved_shares']=={} and account['pending_rights']==[]
        and genesis['purpose']=='PAPER_INITIALIZATION_NOT_BROKER_BALANCE','GENESIS_AUDIT_CONTEXT_MISMATCH')


def validate_chain_context(scope,state,package):
    from data.current_quantity_v2_paper_chain import review_chain
    checked_state=review_chain(state);ledger=checked_state['ledger']
    require(ledger['account_id']==scope['account_id'] and ledger['revision']==scope['state_revision']
        and sha256(canonical(checked_state)).hexdigest()==scope['chain_sha256'],'CHAIN_AUDIT_CONTEXT_MISMATCH')
    original=ledger.get('active_monthly_acceptance',ledger['acceptance'])['proposal']
    decision=document(package['files'][package['documents']['capital_decision']])
    require(decision==original['causal_inputs']['capital_decision'],'CHAIN_AUDIT_DECISION_MISMATCH')
    needed={sid for mapping in (ledger['shares'],ledger['target_quantities']) for sid,q in mapping.items() if q}
    require(set(package['documents']['quote_receipts'])==needed,'CHAIN_AUDIT_QUOTE_DOMAIN_MISMATCH')


class CaptureAudit:
    def __init__(self,root,state,now,*,genesis_binding=None,state_context_required=False):
        self.root=Path(root).absolute();self.identifier=str(uuid4());self.sequence=0;self.previous=None;self.raw_total=0;self.event_total=0
        self.folder=checked(self.root,self.root/'captures'/'audit'/self.identifier)
        self.folder.mkdir(parents=True)
        self.stage='FETCH';self.genesis_binding=genesis_binding
        if genesis_binding is None:
            self.scope=dict(account_id=state['ledger']['account_id'],state_revision=state['ledger']['revision'],
                chain_sha256=sha256(canonical(state)).hexdigest(),binding_kind='REVIEWED_PAPER_CHAIN',binding_sha256=None)
        else:
            require(state is None and genesis_binding['scope']=='DECLARED_EMPTY_GENESIS','GENESIS_AUDIT_SCOPE_REQUIRED')
            self.scope=dict(account_id=genesis_binding['account_id'],state_revision=genesis_binding['state_revision'],
                chain_sha256=None,binding_kind='DECLARED_EMPTY_GENESIS',binding_sha256=sha256(canonical(genesis_binding)).hexdigest())
        self.scope['state_context_required']=bool(state_context_required)
        self.append('STARTED',dict(scope='AFTER_BASE_AND_EXPECTED_IDENTITY_CHECKS_ONLY',genesis_binding=genesis_binding),now)

    def append(self,kind,payload,now):
        event=dict(capture_id=self.identifier,sequence=self.sequence,previous_sha256=self.previous,
                   recorded_at=stamp(now).astimezone(timezone.utc).isoformat(),kind=kind,
                   **self.scope,payload=payload)
        raw=canonical(event);require(len(raw)<=EVENT_LIMIT and self.sequence<2002 and self.event_total+len(raw)<=EVENT_TOTAL_LIMIT,'CAPTURE_AUDIT_SIZE_LIMIT')
        path=checked(self.root,self.folder/f'{self.sequence:04d}.json');_publish(path,raw)
        self.previous=sha256(raw).hexdigest();self.sequence+=1;self.event_total+=len(raw)

    def raw(self,raw,sid,ticker,captured,now):
        require(type(raw)is bytes and len(raw)<=LIMIT,'RAW_QUOTE_BYTES_REQUIRED')
        require(self.sequence<2001 and self.raw_total+len(raw)<=TOTAL_LIMIT,'CAPTURE_AUDIT_RAW_TOTAL_LIMIT')
        digest=publish_blob(self.root,raw,LIMIT)
        self.append('RAW',dict(security_id=sid,ticker=ticker,raw_sha256=digest,
                              captured_at=stamp(captured).isoformat(),bytes=len(raw)),now)
        self.raw_total+=len(raw)

    def package(self,package,*,audit_context=None):
        context_size=0
        require(not self.scope['state_context_required'] or audit_context is not None,'CHAIN_AUDIT_CONTEXT_REQUIRED')
        if self.genesis_binding is not None:validate_genesis_context(self.genesis_binding,audit_context)
        if audit_context is not None and self.genesis_binding is None:
            require(set(audit_context)=={'verified_state'},'CHAIN_AUDIT_CONTEXT_REQUIRED')
            validate_chain_context(self.scope,audit_context['verified_state'],package)
            state_raw=canonical(audit_context['verified_state']);require(len(state_raw)<=16*1024*1024,'CAPTURE_AUDIT_SIZE_LIMIT')
            context_size=len(state_raw)
            digest=publish_blob(self.root,state_raw,16*1024*1024)
            audit_context=dict(verified_state_source_sha256=digest)
        total=context_size
        require(len(package['files'])<=2000 and set(package['files'])==set(package['source_hashes']),'SOURCE_BYTES_LIMIT')
        for name,raw in package['files'].items():
            total+=len(raw)
            require(type(raw)is bytes and len(raw)<=32*1024*1024 and total<=TOTAL_LIMIT,'SOURCE_BYTES_LIMIT')
            digest=package['source_hashes'][name]
            require(sha256(raw).hexdigest()==digest,'CAPTURE_AUDIT_PACKAGE_CHANGED')
            publish_blob(self.root,raw,32*1024*1024)
        raw=canonical(dict(documents=package['documents'],source_hashes=package['source_hashes'],audit_context=audit_context))
        require(len(raw)<=LIMIT,'CAPTURE_AUDIT_SIZE_LIMIT')
        path=checked(self.root,self.root/'captures'/(self.identifier+'.json'));_publish(path,raw)
        return dict(root=str(self.root.resolve()),path=str(path),sha256=sha256(raw).hexdigest())

    def finish(self,status,now,reason=None,receipt=None):
        self.append('TERMINAL',dict(status=status,stage=self.stage,reason=reason,receipt=receipt),now)


def read_capture(root,capture_id,account_id):
    require(type(capture_id)is str and str(UUID(capture_id))==capture_id,'INVALID_CAPTURE_ID')
    require(type(account_id)is str and bool(account_id.strip()),'INVALID_ACCOUNT_ID')
    root=Path(root).absolute();folder=checked(root,root/'captures'/'audit'/capture_id)
    require(folder.is_dir(),'CAPTURE_AUDIT_UNAVAILABLE')
    paths=sorted(folder.iterdir());require(0<len(paths)<=2002,'CAPTURE_AUDIT_COUNT_LIMIT')
    previous=None;events=[];raw_files={};scope=None;terminal=False;raw_total=0;event_total=0
    for index,path in enumerate(paths):
        require(path.name==f'{index:04d}.json' and not terminal,'CAPTURE_AUDIT_SEQUENCE')
        raw=bounded(checked(root,path),EVENT_LIMIT);event_total+=len(raw)
        require(event_total<=EVENT_TOTAL_LIMIT,'CAPTURE_AUDIT_SIZE_LIMIT');event=document(raw)
        require(event['capture_id']==capture_id and event['sequence']==index
                and event['previous_sha256']==previous,'CAPTURE_AUDIT_CHAIN_CHANGED')
        current={k:event[k] for k in ('account_id','state_revision','chain_sha256')}
        current.update(binding_kind=event.get('binding_kind','REVIEWED_PAPER_CHAIN'),binding_sha256=event.get('binding_sha256'),state_context_required=event.get('state_context_required',False))
        require(event['account_id']==account_id,'CAPTURE_AUDIT_ACCOUNT_MISMATCH')
        if scope is None:
            scope=current
            if current['binding_kind']=='DECLARED_EMPTY_GENESIS':
                binding=event['payload']['genesis_binding']
                require(current['chain_sha256'] is None and binding['scope']=='DECLARED_EMPTY_GENESIS'
                    and binding['account_id']==account_id and binding['state_revision']==current['state_revision']
                    and sha256(canonical(binding)).hexdigest()==current['binding_sha256'],'GENESIS_AUDIT_BINDING_CHANGED')
            else:require(current['binding_kind']=='REVIEWED_PAPER_CHAIN','UNKNOWN_CAPTURE_BINDING_KIND')
        require(current==scope and event['account_id']==account_id,'CAPTURE_AUDIT_ACCOUNT_MISMATCH')
        stamp(event['recorded_at'])
        require((index==0 and event['kind']=='STARTED') or (index>0 and event['kind'] in ('RAW','TERMINAL')),'CAPTURE_AUDIT_EVENT_KIND')
        if event['kind']=='RAW':
            value=event['payload'];digest=value['raw_sha256']
            require(type(digest)is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'CAPTURE_AUDIT_HASH_INVALID')
            blob=bounded(checked(root,root/'blobs'/digest));raw_total+=len(blob)
            require(raw_total<=TOTAL_LIMIT,'CAPTURE_AUDIT_RAW_TOTAL_LIMIT')
            require(sha256(blob).hexdigest()==digest and len(blob)==value['bytes'],'CAPTURE_AUDIT_RAW_CHANGED')
            stamp(value['captured_at']);raw_files[digest]=blob
        terminal=event['kind']=='TERMINAL';events.append(event);previous=sha256(raw).hexdigest()
    if terminal and events[-1]['payload']['status']=='CAPTURED':
        receipt=events[-1]['payload']['receipt']
        require(Path(receipt['root']).resolve()==root.resolve(),'CAPTURE_AUDIT_RECEIPT_ROOT')
        manifest_path=Path(receipt['path'])
        require(manifest_path.parent.resolve()==(root/'captures').resolve()
                and manifest_path.suffix=='.json' and str(UUID(manifest_path.stem))==manifest_path.stem,
                'CAPTURE_AUDIT_RECEIPT_PATH')
        saved=bounded(checked(root,manifest_path))
        require(sha256(saved).hexdigest()==receipt['sha256'],'CAPTURE_AUDIT_RECEIPT_CHANGED')
        manifest=document(saved);require(len(manifest['source_hashes'])<=2000,'SOURCE_BYTES_LIMIT')
        if scope['binding_kind']=='DECLARED_EMPTY_GENESIS':
            validate_genesis_context(events[0]['payload']['genesis_binding'],manifest.get('audit_context'))
        total=0;package_files={}
        for name,digest in manifest['source_hashes'].items():
            require(type(digest)is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'CAPTURE_AUDIT_HASH_INVALID')
            blob=bounded(checked(root,root/'blobs'/digest),32*1024*1024);total+=len(blob)
            require(total<=128*1024*1024 and sha256(blob).hexdigest()==digest,'CAPTURE_AUDIT_PACKAGE_CHANGED')
            package_files[name]=blob
        context=manifest.get('audit_context')
        require(not scope['state_context_required'] or context is not None,'CHAIN_AUDIT_CONTEXT_REQUIRED')
        if scope['binding_kind']=='REVIEWED_PAPER_CHAIN' and context is not None:
            require(set(context)=={'verified_state_source_sha256'},'CHAIN_AUDIT_CONTEXT_REQUIRED')
            digest=context['verified_state_source_sha256']
            require(digest==scope['chain_sha256'],'CHAIN_AUDIT_CONTEXT_MISMATCH')
            state_raw=bounded(checked(root,root/'blobs'/digest),16*1024*1024)
            require(total+len(state_raw)<=TOTAL_LIMIT,'SOURCE_BYTES_LIMIT')
            require(sha256(state_raw).hexdigest()==digest,'CHAIN_AUDIT_CONTEXT_MISMATCH')
            validate_chain_context(scope,document(state_raw),dict(files=package_files,documents=manifest['documents']))
    return dict(capture_id=capture_id,account_id=account_id,events=events,raw_files=raw_files,
        status=events[-1]['payload']['status'] if terminal else 'UNFINISHED_OR_TRUNCATED',
        binding_scope=scope,audit_only=True,execution_blocked=True,selected_for_current_account=False,
        worker_liveness='UNKNOWN',coverage='AFTER_BASE_AND_EXPECTED_IDENTITY_CHECKS_ONLY',
        external_anti_rollback_verified=False)

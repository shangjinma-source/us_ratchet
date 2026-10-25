"""Registered paper cap path with explicit creation and fail-closed reopen.

The unchanged V2 store owns numeric rules and complete raw-evidence replay.
Missing/partial namespaces require recovery; opening never invents a new cap.
"""
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import json
import msvcrt
import os
from pathlib import Path
import stat
import sqlite3
from contextlib import closing
from uuid import uuid4
from core.strategy_account_ledger import canonical
from backtest.current_strategy_prospective_paper_book_v2 import replay,_context
from data.strategy_paper_application_descriptor_v2 import require
from data.strategy_halt_aware_pullback_cap_store_v2 import PullbackCapStore,resolve_parameters
from data.strategy_halt_aware_pullback_cap_store_v1 import encoded
from data.strategy_halt_aware_pullback_entry_v1 import digest,stamp
from data.strategy_halt_aware_pullback_sources_v1 import candidate_from_yahoo_bytes
from data.strategy_paper_execution_preview_v1 import _local_import_closure

CODE_PATHS=_local_import_closure({'data/strategy_prospective_paper_cap_store_v2.py'})


def checked(path, *, required=False):
    for parent in (path,*path.parents):
        if parent.exists():
            info=parent.lstat()
            require(not parent.is_symlink() and not getattr(info,'st_file_attributes',0)&0x400,
                'PAPER_CAP_REPARSE_REFUSED')
    if not path.exists():
        require(not required,'PAPER_CAP_NAMESPACE_RECOVERY_REQUIRED');return None
    info=path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink==1,'PAPER_CAP_FILE_NOT_PRIVATE')
    return info.st_dev,info.st_ino


class ProspectivePersistentCaps:
    storage_kind='DURABLE_REGISTERED_PAPER_CAP_V1'

    def __init__(self,*,root,book,authority,admitted_decisions,clock,admitted_settlements=None,
            initialize=False,recover_pending=False,max_history_rows=10000,max_history_bytes=128*1024*1024):
        app=_context(authority,clock())
        require(CODE_PATHS<=set(app['code_sha256']),'PAPER_CAP_CODE_SCOPE')
        verified=replay(book,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
        self.account_id=verified['account_id'];self.registration=verified['registration_sha256']
        self.descriptor=verified['descriptor_sha256'];self.clock=clock;self.proofs=[];self.closed=False
        self.root=Path(root).absolute();self.path=self.root/app['storage']['caps']
        require(self.path.is_relative_to(self.root),'PAPER_CAP_PATH_ESCAPE')
        self.owner=self.path.with_name(self.path.name+'.owner.json')
        self.lock=self.path.with_name(self.path.name+'.lock')
        self.marker=self.path.with_name(self.path.name+'.initializing')
        self.checkpoint=self.path.with_name(self.path.name+'.checkpoint.json')
        self.pending=self.path.with_name(self.path.name+'.pending.json')
        self.expected=dict(schema='PROSPECTIVE_PAPER_CAP_NAMESPACE_V1',account_id=self.account_id,
            registration_sha256=self.registration,descriptor_sha256=self.descriptor,
            relative_path=app['storage']['caps'],legacy_migration_allowed=False,
            max_history_rows=max_history_rows,max_history_bytes=max_history_bytes)
        for path in (self.path,self.owner,self.lock,self.marker,self.checkpoint,self.pending):checked(path)
        if initialize:
            require(not any(p.exists() for p in (self.path,self.owner,self.lock,self.marker,self.checkpoint,self.pending)),
                'PAPER_CAP_NAMESPACE_ALREADY_EXISTS')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            checked(self.path)
            with self.marker.open('xb') as stream:
                stream.write(canonical(self.expected));stream.flush();os.fsync(stream.fileno())
            with self.lock.open('xb') as stream:
                stream.write(b'1');stream.flush();os.fsync(stream.fileno())
            self.store=PullbackCapStore(self.path,clock=clock,max_history_rows=max_history_rows,
                max_history_bytes=max_history_bytes,legacy_path=None)
            owner=dict(self.expected,namespace_id='paper-durable-cap:'+str(uuid4()))
            with self.owner.open('xb') as stream:
                stream.write(canonical(owner));stream.flush();os.fsync(stream.fileno())
            with self.checkpoint.open('xb') as stream:
                stream.write(canonical(dict(owner_sha256=sha256(self.owner.read_bytes()).hexdigest(),
                    database_sha256=sha256(self.path.read_bytes()).hexdigest())));stream.flush();os.fsync(stream.fileno())
            # Only a completely created namespace clears its own creation marker.
            self.marker.unlink()
        self._identities={p:checked(p,required=True) for p in (self.path,self.owner,self.lock,self.checkpoint)}
        require(not self.marker.exists(),'PAPER_CAP_NAMESPACE_RECOVERY_REQUIRED')
        self.owner_bytes=self.owner.read_bytes()
        owner=json.loads(self.owner_bytes)
        require({k:v for k,v in owner.items() if k!='namespace_id'}==self.expected and
            type(owner.get('namespace_id')) is str and owner['namespace_id'].startswith('paper-durable-cap:'),
            'PAPER_CAP_OWNER_MISMATCH')
        self.namespace_id=owner['namespace_id']
        with self._locked():
            if recover_pending:
                self._recover_pending()
            self._validate_checkpoint()
            self.store=PullbackCapStore(self.path,clock=clock,max_history_rows=max_history_rows,
                max_history_bytes=max_history_bytes,legacy_path=None)
            self._validate_files()

    def _heads(self):
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as c:
            return {binding:dict(count=count,head=c.execute(
                'SELECT record_hash FROM halt_cap_records_v2 WHERE binding=? ORDER BY ordinal DESC LIMIT 1',
                (binding,)).fetchone()[0]) for binding,count in c.execute(
                'SELECT binding,COUNT(*) FROM halt_cap_records_v2 GROUP BY binding')}

    @staticmethod
    def _intent(parameters):
        normalized=dict(parameters)
        raw=normalized.pop('raw');halt=normalized.pop('halt_raw',None)
        normalized.setdefault('halt_receipt',None)
        return dict(parameters=normalized,raw_blob=dict(sha256=sha256(raw).hexdigest(),bytes=len(raw)),
            halt_blob=None if halt is None else dict(sha256=sha256(halt).hexdigest(),bytes=len(halt)))

    def _audit_rows(self):
        records=[];used=set()
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as c:
            budget=object.__new__(PullbackCapStore);budget.max_history_bytes=self.expected['max_history_bytes']
            budget._budget(c)
            for (binding,) in c.execute('SELECT DISTINCT binding FROM halt_cap_records_v2 ORDER BY binding'):
                prior=None;parent='';observed=None
                rows=c.execute('SELECT ordinal,parameters,result,previous_hash,record_hash FROM halt_cap_records_v2 WHERE binding=? ORDER BY ordinal',(binding,)).fetchall()
                require(len(rows)<=self.expected['max_history_rows'],'PAPER_CAP_RECOVERY_BUDGET')
                for index,(ordinal,p,r,previous,record_hash) in enumerate(rows):
                    require(ordinal==index and previous==parent,'PAPER_CAP_RECOVERY_CHAIN')
                    parameters=json.loads(p);raw,decoded,legacy=resolve_parameters(c,parameters)
                    require(legacy==[],'PAPER_CAP_RECOVERY_FOREIGN_LEGACY')
                    result=candidate_from_yahoo_bytes(raw=raw,previous_cap=prior,**decoded)
                    require(encoded(result['candidate']['binding'])==binding and encoded(result)==r and
                        digest(dict(ordinal=index,parameters=parameters,result=result,previous_hash=previous))==record_hash,
                        'PAPER_CAP_RECOVERY_REPLAY')
                    at=stamp(decoded['captured_at'])
                    require(observed is None or at>observed,'PAPER_CAP_RECOVERY_TIME')
                    for name in ('raw_blob','halt_blob','legacy_blob'):
                        if parameters[name] is not None:used.add(parameters[name]['sha256'])
                    records.append(dict(binding=binding,ordinal=ordinal,parameters=parameters,record_hash=record_hash))
                    prior=result['candidate']['cap_declaration'];parent=record_hash;observed=at
            require(used=={row[0] for row in c.execute('SELECT digest FROM cap_evidence_blobs')},'PAPER_CAP_RECOVERY_ORPHAN_BLOB')
        return records

    def _validate_files(self):
        require(not self.closed and not self.marker.exists(),'PAPER_CAP_NAMESPACE_RECOVERY_REQUIRED')
        for path,identity in self._identities.items():
            require(checked(path,required=True)==identity,'PAPER_CAP_FILE_REPLACED')
        for suffix in ('-journal','-wal','-shm'):checked(Path(str(self.path)+suffix))
        require(self.owner.read_bytes()==self.owner_bytes,'PAPER_CAP_OWNER_CHANGED')

    def _validate_checkpoint(self):
        require(not self.pending.exists(),'PAPER_CAP_NAMESPACE_RECOVERY_REQUIRED')
        checkpoint=json.loads(self.checkpoint.read_bytes())
        require(checkpoint==dict(owner_sha256=sha256(self.owner_bytes).hexdigest(),
            database_sha256=sha256(self.path.read_bytes()).hexdigest()),'PAPER_CAP_CHECKPOINT_CHANGED')
        return checkpoint

    def _recover_pending(self):
        """Audit an exact intended append, never recompute a fresh quote or order."""
        checked(self.pending,required=True)
        raw=self.pending.read_bytes();intent=json.loads(raw)
        require(intent.get('schema')=='PAPER_CAP_APPEND_INTENT_V1','PAPER_CAP_RECOVERY_INTENT_REQUIRED')
        recovery_start=stamp(self.clock())
        require(recovery_start>=stamp(intent['started_at']),'PAPER_CAP_RECOVERY_CLOCK_REVERSED')
        before=intent['checkpoint'];current_hash=sha256(self.path.read_bytes()).hexdigest()
        owner_hash=sha256(self.owner_bytes).hexdigest()
        require(before['owner_sha256']==owner_hash,'PAPER_CAP_RECOVERY_OWNER')
        current_checkpoint=json.loads(self.checkpoint.read_bytes())
        updated=dict(owner_sha256=owner_hash,database_sha256=current_hash)
        require(current_checkpoint in (before,updated),'PAPER_CAP_RECOVERY_CHECKPOINT')
        records=self._audit_rows();heads=self._heads()
        if current_hash==before['database_sha256']:
            require(heads==intent['heads'],'PAPER_CAP_RECOVERY_PREVIOUS_HEADS')
            action='NO_CAP_COMMIT_CONFIRMED'
        else:
            binding=intent['binding'];prior=intent['heads'].get(binding,dict(count=0,head=''))
            require(binding in heads and heads[binding]['count']==prior['count']+1,'PAPER_CAP_RECOVERY_APPEND_COUNT')
            prior_heads=dict(heads)
            if prior['count']:prior_heads[binding]=prior
            else:prior_heads.pop(binding)
            require(prior_heads==intent['heads'],'PAPER_CAP_RECOVERY_OTHER_HEADS_CHANGED')
            rows=[r for r in records if r['binding']==binding]
            require((rows[-2]['record_hash'] if len(rows)>1 else '')==prior['head'],'PAPER_CAP_RECOVERY_PREFIX_CHANGED')
            stored=dict(rows[-1]['parameters']);wanted=intent['request'];expected=dict(wanted['parameters'])
            require(stored.pop('raw_blob')==wanted['raw_blob'] and stored.pop('halt_blob')==wanted['halt_blob'],
                'PAPER_CAP_RECOVERY_SOURCE_CHANGED')
            stored.pop('legacy_blob')  # Full replay above requires exactly the empty paper legacy snapshot.
            actual_time=stamp(stored.pop('now'));request_time=stamp(expected.pop('now'))
            require(stored==expected and request_time<=actual_time and stamp(intent['started_at'])<=actual_time<=recovery_start,
                'PAPER_CAP_RECOVERY_REQUEST_CHANGED')
            action='INTENDED_CAP_COMMIT_REPLAYED'
        self._validate_files()
        require(self.pending.read_bytes()==raw and sha256(self.path.read_bytes()).hexdigest()==current_hash,
            'PAPER_CAP_RECOVERY_INPUT_CHANGED')
        recovery_end=stamp(self.clock())
        require(recovery_end>=recovery_start,'PAPER_CAP_RECOVERY_CLOCK_REVERSED')
        report=dict(schema='PROSPECTIVE_PAPER_CAP_RECOVERY_V1',action=action,namespace_id=self.namespace_id,
            intent_sha256=sha256(raw).hexdigest(),intent=intent,checkpoint_before=before,checkpoint_after=updated,
            verified_rows=len(records),review_started_at=recovery_start.isoformat(),reviewed_at=recovery_end.isoformat(),orders_created=False,
            reference_reissued=False)
        report_path=self.path.with_name(self.path.name+'.recovery-'+uuid4().hex+'.json')
        with report_path.open('xb') as stream:
            stream.write(canonical(report));stream.flush();os.fsync(stream.fileno())
        temporary=self.checkpoint.with_name(self.checkpoint.name+'.'+uuid4().hex+'.tmp')
        with temporary.open('xb') as stream:
            stream.write(canonical(updated));stream.flush();os.fsync(stream.fileno())
        self._validate_files();os.replace(temporary,self.checkpoint)
        self._identities[self.checkpoint]=checked(self.checkpoint,required=True)
        archived=self.pending.with_name(self.pending.name+'.resolved-'+uuid4().hex)
        os.replace(self.pending,archived)  # Preserve the original failure intent verbatim.
        self.recovery_report=dict(report,path=str(report_path),preserved_intent_path=str(archived))

    @contextmanager
    def _locked(self):
        self._validate_files()
        with self.lock.open('r+b') as stream:
            try:
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as error:
                raise ValueError('PAPER_CAP_BUSY') from error
            try:
                self._validate_files();yield
            finally:
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)

    def validate(self,book):
        require(book['account_id']==self.account_id and book['registration_sha256']==self.registration and
            book['descriptor_sha256']==self.descriptor,'PAPER_CAP_ACCOUNT_BINDING')
        self._validate_files()

    def candidate(self,**parameters):
        with self._locked():
            checkpoint=self._validate_checkpoint()
            initial=candidate_from_yahoo_bytes(previous_cap=None,**parameters)
            intent=dict(schema='PAPER_CAP_APPEND_INTENT_V1',checkpoint=checkpoint,heads=self._heads(),
                binding=encoded(initial['candidate']['binding']),request=self._intent(parameters),
                started_at=stamp(self.clock()).isoformat())
            with self.pending.open('xb') as stream:
                stream.write(canonical(intent));stream.flush();os.fsync(stream.fileno())
            try:
                result=self.store.candidate(**parameters)
                self._validate_files()
                updated=dict(owner_sha256=sha256(self.owner_bytes).hexdigest(),
                    database_sha256=sha256(self.path.read_bytes()).hexdigest())
                temporary=self.checkpoint.with_name(self.checkpoint.name+'.'+uuid4().hex+'.tmp')
                with temporary.open('xb') as stream:
                    stream.write(canonical(updated));stream.flush();os.fsync(stream.fileno())
                self._validate_files()
                os.replace(temporary,self.checkpoint)
                self._identities[self.checkpoint]=checked(self.checkpoint,required=True)
                self.pending.unlink()
                self.proofs.append(deepcopy(result))
                return result
            except Exception:
                # Clear only this attempt when bytes prove no cap commit occurred.
                self._validate_files()
                if sha256(self.path.read_bytes()).hexdigest()==checkpoint['database_sha256']:
                    archived=self.pending.with_name(self.pending.name+'.no-commit-'+uuid4().hex)
                    os.replace(self.pending,archived)
                raise

    def close(self):
        self.closed=True

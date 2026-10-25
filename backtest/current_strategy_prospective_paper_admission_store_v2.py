"""Server-owned producer admission archive, not a client result/hash importer.

Lock order is coordinator -> admission SQLite -> cap store. Producers never
call the coordinator or an admission loader. Loading only validates saved bytes
and the registration journal; it never reruns a producer or appends cap records.
Construct/reopen cap instances before entering admission; their constructor
releases its lock before returning. New daily-load failures may leave only a
started directory; any unregistered directory blocks automatic retry regardless
of whether a failed marker or a complete manifest was written.
The server-controlled registration DB is the trust anchor, not public evidence
authenticity or protection against an administrator rewriting the entire store.
"""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import sqlite3
import stat

from core.strategy_account_ledger import canonical
from backtest.current_strategy_prospective_paper_book_v2 import _context
from data.strategy_paper_application_descriptor_v2 import require,stamp
from data.strategy_prospective_paper_decision_v2 import produce_prospective_decision
from data.strategy_prospective_paper_settlement_v2 import produce_prospective_settlement
from data.strategy_prospective_paper_cap_store_v2 import ProspectivePersistentCaps
from data.strategy_prospective_paper_daily_capture_v2 import load_prospective_daily_archive
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_prospective_paper_selection_v2 import select_prospective_target, verify_prospective_target

SOURCE='backtest/current_strategy_prospective_paper_admission_store_v2.py'
MAX_BYTES=256*1024*1024


def digest(raw):return sha256(raw).hexdigest()


def admit_daily_source(*,authority,daily_arguments,directory,trusted_complete_sha256,clock):
    require(daily_arguments['authority']==authority,'PAPER_ADMISSION_AUTHORITY_CHANGED')
    loaded=load_prospective_daily_archive(directory=directory,
        trusted_complete_sha256=trusted_complete_sha256,daily_arguments=daily_arguments,clock=clock)
    require(loaded['status']=='DAILY_SIGNAL_READY','PAPER_ADMISSION_DAILY_NOT_READY')
    args=loaded['daily_arguments']
    return dict(status='DAILY_SOURCE_REGISTERED_NOT_ORDER',receipt_bytes=args['receipt_bytes'],
                files=args['files'],account_mutated=False,orders_created=False)


class ProspectivePaperAdmissionStore:
    def __init__(self,*,root,authority,clock=None,timeout_seconds=2,fault=None):
        self.clock=clock or (lambda:datetime.now(timezone.utc));self.authority=deepcopy(authority)
        app=_context(self.authority,self.clock())
        require({SOURCE,'data/strategy_prospective_paper_daily_capture_v2.py'}<=set(app['code_sha256']),
                'PAPER_ADMISSION_CODE_REQUIRED')
        self.root=Path(root).absolute();self.directory=self.root/app['storage']['evidence']/'admissions'
        require(self.root.is_dir() and self.directory.is_relative_to(self.root),'PAPER_ADMISSION_ROOT')
        require(type(timeout_seconds) in (int,float) and 0<timeout_seconds<=10,'PAPER_ADMISSION_TIMEOUT')
        self.path=self.directory/'registry.sqlite3';self.timeout=timeout_seconds
        self.fault=fault or (lambda phase:None)
        self.owner=dict(schema='PROSPECTIVE_PAPER_ADMISSION_REGISTRY_V1',account_id=app['account_id'],
            descriptor_sha256=authority['descriptor_arguments']['trusted_descriptor_sha256'],
            registration_sha256=authority['trusted_registration_sha256'])
        self._paths()

    def _paths(self):
        for p in [self.directory,*self.directory.parents]:
            if p.exists() or p.is_symlink():
                require(not p.is_symlink() and not getattr(p.lstat(),'st_file_attributes',0)&0x400,'PAPER_ADMISSION_LINK')
        identity=None
        for p in [self.path,*[Path(str(self.path)+s) for s in ('-journal','-wal','-shm')]]:
            if p.exists() or p.is_symlink():
                info=p.lstat()
                require(not p.is_symlink() and stat.S_ISREG(info.st_mode) and info.st_nlink==1 and
                    not getattr(info,'st_file_attributes',0)&0x400,'PAPER_ADMISSION_LINK')
                if p==self.path:identity=(info.st_dev,info.st_ino)
        return identity

    def _read(self,path,maximum=MAX_BYTES):
        for p in [path,*path.parents]:
            require(not p.is_symlink() and (not p.exists() or not getattr(p.lstat(),'st_file_attributes',0)&0x400),'PAPER_ADMISSION_LINK')
        info=path.stat();require(stat.S_ISREG(info.st_mode) and info.st_nlink==1,'PAPER_ADMISSION_LINK')
        with path.open('rb') as stream:raw=stream.read(maximum+1)
        require(len(raw)<=maximum,'PAPER_ADMISSION_BYTE_BUDGET')
        return raw

    @staticmethod
    def _save(path,raw):
        with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())

    def _schema(self,connection):
        require(connection.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()==
            [('admission_owner','table'),('admissions','table')],'PAPER_ADMISSION_SCHEMA')
        rows=connection.execute('SELECT owner,count,head FROM admission_owner').fetchall()
        require(len(rows)==1 and rows[0][0]==canonical(self.owner).decode(),'PAPER_ADMISSION_OWNER')
        require(connection.execute('PRAGMA quick_check').fetchall()==[('ok',)],'PAPER_ADMISSION_DATABASE_INTEGRITY')
        return rows[0]

    def initialize(self):
        require(not self.directory.exists(),'PAPER_ADMISSION_EXISTS_OR_RECOVERY_REQUIRED')
        self.directory.mkdir(parents=True,exist_ok=False);self._paths()
        self._save(self.directory/'initializing',canonical(self.owner))
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('PRAGMA synchronous=FULL');connection.execute('BEGIN EXCLUSIVE')
            connection.execute('CREATE TABLE admission_owner(owner TEXT NOT NULL,count INTEGER NOT NULL,head TEXT NOT NULL)')
            connection.execute('INSERT INTO admission_owner VALUES(?,?,?)',(canonical(self.owner).decode(),0,digest(canonical(self.owner))))
            connection.execute('CREATE TABLE admissions(ordinal INTEGER PRIMARY KEY,operation_id TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,request_hash TEXT NOT NULL,manifest_hash TEXT NOT NULL,previous_hash TEXT NOT NULL,record_hash TEXT NOT NULL)')
            connection.commit()
        (self.directory/'initializing').unlink()

    def _pack(self,value,blobs):
        if isinstance(value,bytes):
            hashed=digest(value)
            if hashed not in blobs:
                require(len(value)<=32*1024*1024 and sum(map(len,blobs.values()))+len(value)<=MAX_BYTES,'PAPER_ADMISSION_BYTE_BUDGET')
                blobs[hashed]=value
            return {'$bytes':hashed}
        if type(value) is dict:
            require(all(type(k) is str for k in value) and set(value)!={'$bytes'},'PAPER_ADMISSION_INPUT_KEYS')
            return {k:self._pack(v,blobs) for k,v in value.items()}
        if type(value) in (list,tuple):return [self._pack(v,blobs) for v in value]
        require(value is None or type(value) in (str,int,float,bool),'PAPER_ADMISSION_NON_SERIALIZABLE_INPUT')
        return value

    def _unpack(self,value,blobs):
        if type(value) is dict:
            if set(value)=={'$bytes'}:return blobs[value['$bytes']]
            return {k:self._unpack(v,blobs) for k,v in value.items()}
        if type(value) is list:return [self._unpack(v,blobs) for v in value]
        return value

    def _entry(self,operation_id,manifest_hash):
        directory=self.directory/digest(operation_id.encode())
        require(not (directory/'failed.json').exists(),'PAPER_ADMISSION_FAILED_REQUIRES_RECOVERY')
        raw=self._read(directory/'complete.json',4*1024*1024)
        require(digest(raw)==manifest_hash,'PAPER_ADMISSION_MANIFEST_CHANGED')
        value=json.loads(raw)
        require(value['owner']==self.owner and value['operation_id']==operation_id,'PAPER_ADMISSION_BINDING')
        blobs={};total=0
        for hashed,size in value['blobs'].items():
            require(type(hashed) is str and len(hashed)==64 and all(c in '0123456789abcdef' for c in hashed),'PAPER_ADMISSION_BLOB_NAME')
            blob=self._read(directory/'blobs'/hashed,32*1024*1024);total+=len(blob)
            require(len(blob)==size and digest(blob)==hashed and total<=MAX_BYTES,'PAPER_ADMISSION_BLOB_CHANGED')
            blobs[hashed]=blob
        inputs=self._unpack(value['inputs'],blobs)
        require(digest(canonical(value['inputs']))==value['request_hash'],'PAPER_ADMISSION_REQUEST_CHANGED')
        require(inputs['authority']==self.authority,'PAPER_ADMISSION_AUTHORITY_CHANGED')
        if value['kind'] in ('DECISION','DAILY_SOURCE'):
            anchor=inputs['daily_archive'];source=self.root/anchor['directory']
            require(source.is_relative_to(self.root) and not (source/'failed.json').exists(),'PAPER_ADMISSION_DAILY_FAILED')
            complete_raw=self._read(source/'complete.json',4*1024*1024)
            require(complete_raw==anchor['complete_bytes'] and digest(complete_raw)==anchor['trusted_complete_sha256'],
                    'PAPER_ADMISSION_DAILY_COMPLETE_CHANGED')
            complete=json.loads(complete_raw);daily=inputs['arguments']['daily_arguments']
            require(complete['status']=='DAILY_SIGNAL_READY' and
                complete['receipt_sha256']==digest(daily['receipt_bytes']) and
                complete['source_sha256']=={p:digest(b) for p,b in daily['files'].items()},'PAPER_ADMISSION_DAILY_CLOSURE')
        result=self._unpack(value['result'],blobs)
        if value['kind']=='DAILY_SOURCE':
            require(result['status']=='DAILY_SOURCE_REGISTERED_NOT_ORDER' and
                result['receipt_bytes']==daily['receipt_bytes'] and result['files']==daily['files'],
                'PAPER_ADMISSION_DAILY_RESULT_CHANGED')
            return value,result
        if value['kind']=='SELECTION':
            verified=verify_prospective_target(result,**inputs['arguments'])
            require(verified['target_id']==result['decision_id'],'PAPER_ADMISSION_SELECTION_CHANGED')
            return value,result
        key='decision' if value['kind']=='DECISION' else 'settlement'
        if result.get(key+'_bytes') is not None:
            require(digest(result[key+'_bytes'])==result[key+'_sha256'],'PAPER_ADMISSION_RESULT_CHANGED')
            evidence=json.loads(result[key+'_bytes'])
            require(all(evidence[k]==self.owner[k] for k in ('account_id','descriptor_sha256','registration_sha256')),
                    'PAPER_ADMISSION_RESULT_BINDING')
        return value,result

    def _load(self,connection):
        _,count,head=self._schema(connection)
        require(0<=count<=10000,'PAPER_ADMISSION_RECORD_BUDGET')
        result={'decisions':{},'settlements':{}};rows=[];previous=digest(canonical(self.owner))
        for row in connection.execute('SELECT ordinal,operation_id,kind,request_hash,manifest_hash,previous_hash,record_hash FROM admissions ORDER BY ordinal'):
            ordinal,oid,kind,request_hash,manifest_hash,prior,hashed=row
            require(kind in ('DECISION','SETTLEMENT','SELECTION','DAILY_SOURCE'),'PAPER_ADMISSION_KIND')
            require(ordinal==len(rows)+1 and prior==previous and digest(canonical(list(row[:-1])))==hashed,'PAPER_ADMISSION_CHAIN')
            manifest,produced=self._entry(oid,manifest_hash)
            require(manifest['kind']==kind and manifest['request_hash']==request_hash,'PAPER_ADMISSION_INDEX_BINDING')
            if kind in ('DECISION','SETTLEMENT'):
                key='decision' if kind=='DECISION' else 'settlement'
                if produced.get(key+'_bytes') is not None:result[key+'s'][produced[key+'_sha256']]=produced[key+'_bytes']
            rows.append(row);previous=hashed
        require(len(rows)==count and previous==head,'PAPER_ADMISSION_HEAD_CHANGED')
        return result,rows

    def load(self):
        require(self.path.exists() and not (self.directory/'initializing').exists(),'PAPER_ADMISSION_RECOVERY_REQUIRED')
        identity=self._paths();_context(self.authority,self.clock())
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=self.timeout,isolation_level=None)) as connection:
            connection.execute('BEGIN')
            try:result,_=self._load(connection)
            finally:connection.rollback()
        require(self._paths()==identity,'PAPER_ADMISSION_DATABASE_REPLACED')
        return result

    def produce_and_archive_decision(self,operation_id,arguments,*,daily_archive):
        """daily_archive is a server-retained successful capture return reference."""
        return self._produce(operation_id,'DECISION',arguments,daily_archive=daily_archive)

    def produce_and_archive_settlement(self,operation_id,arguments):
        return self._produce(operation_id,'SETTLEMENT',arguments)

    def produce_and_archive_selection(self,operation_id,arguments):
        return self._produce(operation_id,'SELECTION',arguments)

    def register_daily_source(self,operation_id,*,daily_arguments,directory,trusted_complete_sha256):
        return self._produce(operation_id,'DAILY_SOURCE',dict(authority=self.authority,
            daily_arguments=daily_arguments,directory=str(Path(directory).absolute()),
            trusted_complete_sha256=trusted_complete_sha256),daily_archive=dict(
                directory=str(Path(directory).absolute()),trusted_complete_sha256=trusted_complete_sha256))

    def latest_daily_parent(self,security_id,*,before_session):
        require(self.path.exists() and not (self.directory/'initializing').exists(),'PAPER_ADMISSION_RECOVERY_REQUIRED')
        identity=self._paths();_context(self.authority,self.clock());found=None;latest=None
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=self.timeout)) as connection:
            connection.execute('BEGIN');_,rows=self._load(connection)
            for row in rows:
                if row[2]!='DAILY_SOURCE':continue
                _,result=self._entry(row[1],row[4]);receipt=json.loads(result['receipt_bytes'])
                day=receipt['execution_session']['date'];reference=receipt.get('security_packets',{}).get(security_id)
                if reference is None or day>=before_session or (latest is not None and day<latest):continue
                raw=result['files'][reference['path']]
                require(digest(raw)==reference['sha256'],'PAPER_ADMISSION_PARENT_HASH')
                parent=json.loads(raw);files={name:result['files'][name] for name in parent['source_sha256']}
                require(all(digest(body)==parent['source_sha256'][name] for name,body in files.items()),
                        'PAPER_ADMISSION_PARENT_CLOSURE')
                inputs=json.loads(files[parent['normalized_inputs_path']])
                require(security_id in inputs['histories'] and parent['execution_session']['date']==day,
                        'PAPER_ADMISSION_PARENT_SECURITY')
                found=dict(receipt_bytes=raw,trusted_parent_sha256=reference['sha256'],files=files,
                           source_operation_id=row[1],session=day)
                latest=day
            connection.rollback()
        require(self._paths()==identity,'PAPER_ADMISSION_DATABASE_REPLACED')
        return found

    def validate_risk_store(self,risk_store,admitted):
        require(type(risk_store) is MonthlyPeakExitStore and
            risk_store.path.absolute()==self.directory.parent/'risk.sqlite3' and
            risk_store.path.is_file(),'PAPER_ADMISSION_RISK_NAMESPACE')
        self._read(risk_store.path)
        for decision_raw in admitted['decisions'].values():
            risk=json.loads(decision_raw)['risk_projection']
            if risk.get('projection_kind') == 'ZERO_MONTHLY_TARGET_EXIT':
                require(not any(risk['monthly_cap_view']['target_quantities'].values()) and
                    all(type(q) is int and q == 0 for q in risk['account_target_quantities'].values()),
                    'PAPER_ZERO_TARGET_PROJECTION_INVALID')
                # Earlier admitted peak decisions are still checked below in this loop.
                continue
            saved=risk_store.read(risk['risk_namespace'])
            require(saved is not None,'PAPER_RISK_STATE_RECOVERY_REQUIRED')
            old=risk['state']
            require(saved['decision_date']>=old['decision_date'] and
                saved['session_date']>=old['session_date'],'PAPER_RISK_STATE_ROLLBACK')
            if saved['decision_date']==old['decision_date']:
                require(set(saved['exited'])>=set(old['exited']), 'PAPER_RISK_EXIT_RECORD_LOST')

    def _produce(self,operation_id,kind,arguments,daily_archive=None):
        require(type(operation_id) is str and 0<len(operation_id)<=200,'PAPER_ADMISSION_OPERATION_ID')
        require('clock' not in arguments,'PAPER_ADMISSION_SERVER_CLOCK_ONLY')
        require(self.path.exists() and not (self.directory/'initializing').exists(),'PAPER_ADMISSION_RECOVERY_REQUIRED')
        authority=arguments['daily_arguments']['authority'] if kind=='DECISION' else arguments['authority']
        require(authority==self.authority,'PAPER_ADMISSION_AUTHORITY_CHANGED')
        copied=dict(arguments);caps=copied.pop('caps',None)
        risk_store=copied.pop('risk_store',None)
        risk_path=None
        if kind=='DECISION':
            require(type(risk_store) is MonthlyPeakExitStore,'PAPER_ADMISSION_RISK_STORE_REQUIRED')
            risk_path=risk_store.path.absolute()
            expected=self.directory.parent/'risk.sqlite3'
            require(risk_path==expected and risk_path.is_file(),'PAPER_ADMISSION_RISK_NAMESPACE')
            self._read(risk_path)
        if kind=='DECISION':require(type(caps) is ProspectivePersistentCaps,'PAPER_ADMISSION_DURABLE_CAP_REQUIRED')
        anchor=None
        if kind in ('DECISION','DAILY_SOURCE'):
            require(type(daily_archive) is dict and set(daily_archive)=={'directory','trusted_complete_sha256'},'PAPER_ADMISSION_DAILY_ANCHOR_REQUIRED')
            directory=Path(daily_archive['directory']).absolute()
            require(directory.is_relative_to(self.root),'PAPER_ADMISSION_DAILY_PATH')
            require(not (directory/'failed.json').exists(),'PAPER_ADMISSION_DAILY_FAILED')
            complete_raw=self._read(directory/'complete.json',4*1024*1024)
            require(digest(complete_raw)==daily_archive['trusted_complete_sha256'],'PAPER_ADMISSION_DAILY_COMPLETE_CHANGED')
            anchor=dict(directory=directory.relative_to(self.root).as_posix(),
                trusted_complete_sha256=daily_archive['trusted_complete_sha256'],complete_bytes=complete_raw)
        blobs={};inputs=self._pack(dict(arguments=deepcopy(copied),authority=self.authority,
            cap_namespace_id=caps.namespace_id if caps else None,daily_archive=anchor,
            risk_path=risk_path.relative_to(self.root).as_posix() if risk_path else None),blobs)
        request_hash=digest(canonical(inputs));identity=self._paths()
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=self.timeout,isolation_level=None)) as connection:
            try:
                connection.execute('PRAGMA synchronous=FULL');connection.execute('BEGIN EXCLUSIVE')
                admitted,rows=self._load(connection)
                for row in rows:
                    if row[1]==operation_id:
                        require(row[2]==kind and row[3]==request_hash,'PAPER_ADMISSION_OPERATION_CONFLICT')
                        return self._entry(operation_id,row[4])[1]
                if kind=='DECISION':
                    self.validate_risk_store(risk_store,admitted)
                directory=self.directory/digest(operation_id.encode())
                require(not directory.exists(),'PAPER_ADMISSION_PARTIAL_REQUIRES_RECOVERY')
                directory.mkdir();(directory/'blobs').mkdir()
                self._save(directory/'started.json',canonical(dict(owner=self.owner,request_hash=request_hash)))
                started=stamp(self.clock());_context(self.authority,started)
                call=deepcopy(copied)
                if kind=='DECISION':
                    loaded=load_prospective_daily_archive(directory=self.root/anchor['directory'],
                        trusted_complete_sha256=anchor['trusted_complete_sha256'],
                        daily_arguments=call['daily_arguments'],clock=self.clock)
                    require(loaded['status']=='DAILY_SIGNAL_READY','PAPER_ADMISSION_DAILY_NOT_READY')
                    original_daily=deepcopy(call['daily_arguments']);checked_daily=deepcopy(loaded['daily_arguments'])
                    original_daily.pop('now',None);checked_daily.pop('now',None)
                    require(original_daily==checked_daily,'PAPER_ADMISSION_DAILY_INPUT_CHANGED')
                    call['daily_arguments']=loaded['daily_arguments'];call['caps']=caps
                    call['risk_store']=risk_store
                producer={'DECISION':produce_prospective_decision,'SETTLEMENT':produce_prospective_settlement,
                          'SELECTION':select_prospective_target,'DAILY_SOURCE':admit_daily_source}[kind]
                try:
                    produced=producer(**call,clock=self.clock)
                    encoded=self._pack(produced,blobs)
                    for hashed,raw in blobs.items():self._save(directory/'blobs'/hashed,raw)
                    _context(self.authority,self.clock());finished=stamp(self.clock())
                    require(finished>=started,'PAPER_ADMISSION_CLOCK_ROLLBACK')
                    manifest=dict(owner=self.owner,operation_id=operation_id,kind=kind,request_hash=request_hash,
                        inputs=inputs,result=encoded,started_at=started.isoformat(),finished_at=finished.isoformat(),
                        blobs={h:len(b) for h,b in blobs.items()})
                    raw=canonical(manifest);require(len(raw)<=4*1024*1024,'PAPER_ADMISSION_MANIFEST_BUDGET')
                    self._save(directory/'complete.json',raw);self.fault('after_archive')
                    self._entry(operation_id,digest(raw))
                    prior=rows[-1][-1] if rows else digest(canonical(self.owner))
                    record=[len(rows)+1,operation_id,kind,request_hash,digest(raw),prior];hashed=digest(canonical(record))
                    connection.execute('INSERT INTO admissions VALUES(?,?,?,?,?,?,?)',(*record,hashed))
                    connection.execute('UPDATE admission_owner SET count=?,head=?',(len(rows)+1,hashed))
                    self.fault('before_commit');require(self._paths()==identity,'PAPER_ADMISSION_DATABASE_REPLACED')
                    connection.commit();self.fault('after_commit')
                    return produced
                except Exception as error:
                    if not (directory/'complete.json').exists():
                        self._save(directory/'failed.json',canonical(dict(error=type(error).__name__,message=str(error))))
                    raise
            except BaseException:
                connection.rollback();raise

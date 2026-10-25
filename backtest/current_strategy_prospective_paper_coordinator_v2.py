"""Single server-owned lock for registered paper target publication and acceptance.

Every writer in this namespace must use this coordinator. The lock spans target
read, formal ledger validation and SQLite commit; callers cannot supply a target
reader. This is not a scheduler or a source-admission implementation.
"""
from contextlib import contextmanager, closing
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import msvcrt
import os
import sqlite3
import stat
import time

from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v2 import require, stamp, sessions
from backtest.current_strategy_prospective_paper_book_v2 import _context, digest
from backtest.current_strategy_prospective_paper_store_v2 import ProspectivePaperStore

SOURCE='backtest/current_strategy_prospective_paper_coordinator_v2.py'


class ProspectivePaperCoordinator:
    def __init__(self, *, root, authority, admission_loader, target_verifier,
                 clock=None, timeout_seconds=2, fault=None):
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.authority=deepcopy(authority)
        app=_context(self.authority,self.clock())
        require(SOURCE in app['code_sha256'],'PAPER_COORDINATOR_CODE_REQUIRED')
        require(callable(target_verifier),'PAPER_TARGET_VERIFIER_REQUIRED')
        require(type(timeout_seconds) in (int,float) and 0<timeout_seconds<=10,'PAPER_COORDINATOR_TIMEOUT')
        self.root=Path(root).absolute();self.path=self.root/app['storage']['targets']
        require(self.root.is_dir() and self.path.is_relative_to(self.root),'PAPER_COORDINATOR_ROOT')
        self.lock=self.path.with_name(self.path.name+'.coordinator.lock')
        self.marker=self.path.with_name(self.path.name+'.initializing')
        self.owner=canonical(dict(schema='PROSPECTIVE_PAPER_COORDINATOR_V1',
            descriptor_sha256=authority['descriptor_arguments']['trusted_descriptor_sha256'],
            registration_sha256=authority['trusted_registration_sha256'],account_id=app['account_id']))
        self.timeout=timeout_seconds;self.target_verifier=target_verifier
        self.admission_loader=admission_loader;self.fault=fault or (lambda phase:None)
        self._held=False
        self._check_paths()

    def _check_paths(self):
        for p in [self.path.parent,*self.path.parent.parents]:
            if p.exists() or p.is_symlink():
                info=p.lstat()
                require(not p.is_symlink() and not getattr(info,'st_file_attributes',0)&0x400,'PAPER_COORDINATOR_LINK')
        result={}
        for p in [self.path,self.lock,self.marker,*[Path(str(self.path)+s) for s in ('-journal','-wal','-shm')]]:
            require(not p.is_symlink(),'PAPER_COORDINATOR_LINK')
            if p.exists():
                info=p.lstat()
                require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and
                        not getattr(info,'st_file_attributes',0)&0x400,'PAPER_COORDINATOR_LINK')
                result[p]=(info.st_dev,info.st_ino)
        return result

    @contextmanager
    def _locked(self, initializing=False):
        identities=self._check_paths()
        require(self.lock in identities and (initializing or not self.marker.exists()),'PAPER_COORDINATOR_RECOVERY_REQUIRED')
        with self.lock.open('r+b',buffering=0) as stream:
            deadline=time.monotonic()+self.timeout
            while True:
                try:
                    stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1);break
                except OSError:
                    require(time.monotonic()<deadline,'PAPER_COORDINATOR_LOCK_TIMEOUT')
                    time.sleep(.01)
            try:
                stream.seek(0)
                require(stream.read(4096)==self.owner,'PAPER_COORDINATOR_OWNER_CHANGED')
                require(self._check_paths().get(self.lock)==identities[self.lock],'PAPER_COORDINATOR_LOCK_REPLACED')
                require(not self._held,'PAPER_COORDINATOR_REENTRY')
                self._held=True
                yield
                require(self._check_paths().get(self.lock)==identities[self.lock],'PAPER_COORDINATOR_LOCK_REPLACED')
            finally:
                self._held=False;stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)

    def _store(self):
        require(self._held,'PAPER_COORDINATOR_LOCK_REQUIRED')
        return ProspectivePaperStore(root=self.root,authority=self.authority,admission_loader=self.admission_loader,
            target_reader=self._current_id,clock=self.clock,timeout_seconds=self.timeout,fault=self.fault)

    def _load_targets(self, connection):
        require(connection.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()==
                [('paper_target_owner','table'),('paper_targets','table')],'PAPER_TARGET_SCHEMA')
        owner=connection.execute('SELECT value,count,head FROM paper_target_owner').fetchall()
        require(len(owner)==1 and owner[0][0]==self.owner.decode(),'PAPER_TARGET_OWNER')
        count,total=connection.execute('SELECT count(*),coalesce(sum(length(CAST(payload AS BLOB))),0) FROM paper_targets').fetchone()
        require(count==owner[0][1] and count<=10000 and total<=128*1024*1024,'PAPER_TARGET_BUDGET')
        previous=sha256(self.owner).hexdigest();result=[]
        for ordinal,target_id,payload,prior,hashed in connection.execute('SELECT ordinal,target_id,payload,previous_hash,record_hash FROM paper_targets ORDER BY ordinal'):
            value=json.loads(payload)
            require(ordinal==len(result)+1 and prior==previous and canonical(value).decode()==payload and
                digest(dict(ordinal=ordinal,target_id=target_id,payload=value,previous_hash=prior))==hashed,'PAPER_TARGET_CHAIN')
            verified=self.target_verifier(deepcopy(value))
            binding=value['payload']['input_binding']
            require(verified['status']=='VERIFIED_SELECTION_ONLY' and verified['target_id']==target_id and
                binding['paper_application_sha256']==self.authority['descriptor_arguments']['trusted_descriptor_sha256'] and
                binding['registration_sha256']==self.authority['trusted_registration_sha256'], 'PAPER_TARGET_REPLAY')
            result.append(value);previous=hashed
        require(len(result)==count and previous==owner[0][2],'PAPER_TARGET_COUNT_OR_HEAD')
        return result,previous

    def _current_id(self):
        require(self._held,'PAPER_COORDINATOR_LOCK_REQUIRED')
        require(self.path in self._check_paths(),'PAPER_TARGET_DATABASE_MISSING')
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=self.timeout)) as connection:
            targets,_=self._load_targets(connection)
        return targets[-1]['decision_id'] if targets else None

    def initialize(self):
        require(not self.lock.exists() and not self.path.exists() and not self.marker.exists(),'PAPER_COORDINATOR_ALREADY_OR_PARTIALLY_CREATED')
        self.path.parent.mkdir(parents=True,exist_ok=True);self._check_paths()
        with self.marker.open('xb') as stream:
            stream.write(self.owner);stream.flush();os.fsync(stream.fileno())
        with self.lock.open('xb') as stream:
            stream.write(self.owner);stream.flush();os.fsync(stream.fileno())
        with self._locked(initializing=True):
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute('PRAGMA synchronous=FULL')
                connection.execute('BEGIN EXCLUSIVE')
                connection.execute('CREATE TABLE paper_target_owner(value TEXT NOT NULL,count INTEGER NOT NULL,head TEXT NOT NULL)')
                connection.execute('INSERT INTO paper_target_owner VALUES(?,?,?)',
                    (self.owner.decode(),0,sha256(self.owner).hexdigest()))
                connection.execute('CREATE TABLE paper_targets(ordinal INTEGER PRIMARY KEY,target_id TEXT UNIQUE NOT NULL,payload TEXT NOT NULL,previous_hash TEXT NOT NULL,record_hash TEXT NOT NULL)')
                connection.commit()
            book=self._store().initialize()
            self.marker.unlink()
        return book

    def read(self):
        with self._locked():return self._store().read()

    def current_target_id(self):
        with self._locked():return self._current_id()

    def publish_target(self,result,*,expected_book_revision,previous_target_id):
        chunks=[];size=0
        for chunk in json.JSONEncoder(sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).iterencode(result):
            size+=len(chunk.encode('utf8'))
            require(size<=16*1024*1024,'PAPER_TARGET_BUDGET')
            chunks.append(chunk)
        result=json.loads(''.join(chunks));encoded=canonical(result)
        with self._locked():
            verified=self.target_verifier(deepcopy(result))
            book=self._store().read()
            target_identity=self._check_paths().get(self.path)
            require(target_identity is not None,'PAPER_TARGET_DATABASE_MISSING')
            with closing(sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=self.timeout,isolation_level=None)) as connection:
                try:
                    connection.execute('PRAGMA synchronous=FULL');connection.execute('BEGIN EXCLUSIVE')
                    targets,head=self._load_targets(connection)
                    for old in targets:
                        if old['decision_id']==result['decision_id']:
                            require(old==result,'PAPER_TARGET_ID_CONFLICT');return old
                    current=targets[-1]['decision_id'] if targets else None
                    require(current==previous_target_id,'PAPER_TARGET_CAS')
                    require(book['revision']==expected_book_revision==verified['account_revision'] and
                        book['account_id']==verified['account_id'],'PAPER_TARGET_ACCOUNT_CAS')
                    binding=result['payload']['input_binding']
                    require(verified['status']=='VERIFIED_SELECTION_ONLY' and
                        binding['paper_application_sha256']==book['descriptor_sha256'] and
                        binding['registration_sha256']==book['registration_sha256'], 'PAPER_TARGET_AUTHORITY')
                    ordinal=len(targets)+1
                    hashed=digest(dict(ordinal=ordinal,target_id=result['decision_id'],payload=result,previous_hash=head))
                    connection.execute('INSERT INTO paper_targets VALUES(?,?,?,?,?)',
                        (ordinal,result['decision_id'],encoded.decode(),head,hashed))
                    connection.execute('UPDATE paper_target_owner SET count=?,head=?',(ordinal,hashed))
                    self.fault('target_before_commit')
                    require(self._check_paths().get(self.path)==target_identity,'PAPER_TARGET_DATABASE_REPLACED')
                    require(self._store().read()['revision']==expected_book_revision,'PAPER_TARGET_ACCOUNT_CAS')
                    app=_context(self.authority,self.clock());now=stamp(self.clock())
                    payload=result['payload'];marks=payload['input_binding']['marks']
                    current_session=next((r for r in sessions(
                        self.authority['descriptor_arguments']['calendar_bytes'],app['calendar_sha256'])
                        if stamp(r['open'])<=now<stamp(r['close'])),None)
                    require(current_session is not None and
                        app['plan']['first_session']['date']<=current_session['date']<=app['plan']['terminal_session']['date'],
                        'PAPER_TARGET_OUTSIDE_REGISTERED_STUDY')
                    require(payload['target_month']==current_session['date'][:7], 'PAPER_TARGET_MONTH_MISMATCH')
                    require(stamp(payload['computation_finished_at'])<=now and
                        all(0<=(now-stamp(m['observed_at'])).total_seconds()<=120 for m in marks.values()),
                        'PAPER_TARGET_PUBLICATION_EXPIRED')
                    connection.commit()
                except BaseException:
                    connection.rollback();raise
            return result

    def apply(self,request):
        with self._locked():return self._store().apply(request)

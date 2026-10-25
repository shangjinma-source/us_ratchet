"""Read only registered evidence, never discover trusted results by directory scan."""
from contextlib import closing
from hashlib import sha256
import sqlite3

from backtest.current_strategy_prospective_paper_admission_store_v2 import ProspectivePaperAdmissionStore
from backtest.current_strategy_prospective_paper_book_v2 import _context
from data.strategy_paper_application_descriptor_v2 import require

SOURCE='backtest/current_strategy_prospective_paper_admission_reader_v2.py'


def registered_evidence(store, *, operation_id=None, decision_sha256=None, target_id=None):
    require(type(store) is ProspectivePaperAdmissionStore,'PAPER_EVIDENCE_STORE_TYPE')
    require(sum(value is not None for value in (operation_id,decision_sha256,target_id))==1,'PAPER_EVIDENCE_EXACT_LOOKUP')
    app=_context(store.authority,store.clock())
    require(SOURCE in app['code_sha256'],'PAPER_EVIDENCE_READER_PIN_REQUIRED')
    require(store.path.exists() and not (store.directory/'initializing').exists(),'PAPER_ADMISSION_RECOVERY_REQUIRED')
    identity=store._paths(); matches=[]
    with closing(sqlite3.connect(store.path.as_uri()+'?mode=ro',uri=True,
                                timeout=store.timeout,isolation_level=None)) as connection:
        connection.execute('BEGIN')
        try:
            _,rows=store._load(connection)
            for row in rows:
                if operation_id is not None and row[1]!=operation_id:continue
                manifest,result=store._entry(row[1],row[4])
                if decision_sha256 is not None and result.get('decision_sha256')!=decision_sha256:continue
                if target_id is not None and (row[2]!='SELECTION' or result.get('decision_id')!=target_id):continue
                directory=store.directory/sha256(row[1].encode()).hexdigest()
                blobs={h:store._read(directory/'blobs'/h,32*1024*1024) for h in manifest['blobs']}
                require(all(sha256(raw).hexdigest()==h and len(raw)==manifest['blobs'][h]
                            for h,raw in blobs.items()),'PAPER_EVIDENCE_CHANGED_DURING_READ')
                matches.append(dict(operation_id=row[1],kind=row[2],record_sha256=row[6],
                    manifest_sha256=row[4],result=result,inputs=store._unpack(manifest['inputs'],blobs)))
        finally:connection.rollback()
    require(store._paths()==identity,'PAPER_ADMISSION_DATABASE_REPLACED')
    require(len(matches)<=1,'PAPER_EVIDENCE_AMBIGUOUS')
    return matches[0] if matches else None


def registered_selection(store, target_id):
    record=registered_evidence(store,target_id=target_id)
    require(record is not None,'PAPER_SELECTION_NOT_REGISTERED')
    return dict(selection_result=record['result'],selection_arguments=record['inputs']['arguments'])

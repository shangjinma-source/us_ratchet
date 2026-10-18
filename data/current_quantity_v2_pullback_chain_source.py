"""Read-only bounded prefixes from the fixed local cap database, never orders."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from data.current_quantity_v2_pullback_cap_store import encoded

DATABASE='data/quantity_v2_pullback/entry_caps.sqlite3'
MAX_ROWS=256
MAX_PREFIX_BYTES=16*1024*1024
MAX_EXPORT_BYTES=128*1024*1024


def read_pullback_chain_sources(*,repository_root,event_raws):
    """Only server-selected original event bytes; no caller-supplied DB path.

    A read transaction provides one snapshot. Appended rows after a requested
    record do not invalidate its prefix. Returned source bytes can be frozen by
    the caller; this helper never writes exports or opens the mutating store.
    """
    from data.current_quantity_v2_pullback_chain_review import verify_chain
    def require(ok,reason):
        if not ok:raise ValueError(reason)
    require(type(event_raws)is list and len(event_raws)<=50,'EVENT_BATCH_LIMIT')
    require(all(type(raw)is bytes and len(raw)<=1024*1024 for raw in event_raws)
        and sum(map(len,event_raws))<=16*1024*1024,'EVENT_BYTE_LIMIT')
    requests={};unavailable=[]
    for raw in event_raws:
        event_hash=sha256(raw).hexdigest()
        try:
            event=json.loads(raw);require(event['schema']=='V2_GENERATED_PREVIEW_OBSERVATION_V1','EVENT_SCHEMA')
            require(type(event.get('rows'))is list and len(event['rows'])<=100,'EVENT_ROW_LIMIT')
            pending={}
            for row in event.get('rows',[]):
                pullback=row.get('reference',{}).get('pullback')
                if pullback is None:continue
                record=pullback['cap_record_hash'];require(type(record)is str and re.fullmatch('[a-f0-9]{64}',record),'RECORD_HASH')
                sid=row['security_id'];ticker=row['ticker']
                require(pullback['binding']['security_id']==sid and pullback['binding']['ticker']==ticker,'EVENT_SECURITY_BINDING')
                quotes=[c for c in event['captures'] if c.get('role')=='ORIGINAL_QUOTE' and c.get('security_id')==sid and c.get('ticker')==ticker]
                require(len(quotes)==1 and row['limit_price']==pullback['limit_price'],'EVENT_QUOTE_BINDING')
                request=dict(binding=encoded(pullback['binding']),record_hash=record,pullback=pullback,quote_hash=quotes[0]['sha256'])
                require(record not in requests or requests[record]==request,'CONFLICTING_EVENT_RECORD')
                pending[record]=request
            require(len(set(requests)|set(pending))<=100,'RECORD_BATCH_LIMIT')
            requests.update(pending)
        except (ValueError,KeyError,TypeError,AttributeError):
            unavailable.append(dict(event_sha256=event_hash,reason='INVALID_EVENT_CHAIN_BINDING'))
    files={};pins={};paths={};root=Path(repository_root).resolve();database=root/DATABASE
    if not requests:return dict(files=files,source_hashes=pins,record_paths=paths,unavailable=unavailable,external_authentication=False,local_prefix_replayed=False,database_writes=False)
    try:
        require(database.is_file() and not database.is_symlink() and database.resolve().is_relative_to(root),'PULLBACK_DATABASE_UNAVAILABLE')
        with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)) as connection:
            connection.execute('PRAGMA query_only=ON');connection.execute('BEGIN')
            steps=[0]
            def budget():
                steps[0]+=1
                return 1 if steps[0]>10000 else 0
            connection.set_progress_handler(budget,1000)
            cache={};total=0
            for record,request in requests.items():
                try:
                    matches=connection.execute('SELECT ordinal FROM pullback_caps WHERE binding=? AND record_hash=? LIMIT 2',(request['binding'],record)).fetchall()
                    require(len(matches)==1 and type(matches[0][0])is int and 0<=matches[0][0]<MAX_ROWS,'PULLBACK_PREFIX_UNAVAILABLE')
                    ordinal=matches[0][0];key=(request['binding'],ordinal)
                    count,size=connection.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(raw)+LENGTH(CAST(parameters AS BLOB))+LENGTH(CAST(result AS BLOB))),0) FROM pullback_caps WHERE binding=? AND ordinal<=?',key).fetchone()
                    require(count==ordinal+1 and size<=MAX_PREFIX_BYTES,'PULLBACK_PREFIX_LIMIT_OR_GAP')
                    if key not in cache:
                        rows=connection.execute('SELECT ordinal,raw,parameters,result,previous_hash,record_hash FROM pullback_caps WHERE binding=? AND ordinal<=? ORDER BY ordinal',key).fetchall()
                        export=[dict(binding=json.loads(request['binding']),ordinal=n,raw_hex=quote.hex(),parameters=json.loads(parameters),result=json.loads(result),previous_hash=parent,record_hash=h) for n,quote,parameters,result,parent,h in rows]
                        chain=encoded(dict(schema='LOCAL_PULLBACK_CHAIN_EXPORT_V1',rows=export)).encode()
                        require(len(chain)<=32*1024*1024,'PULLBACK_EXPORT_LIMIT')
                        cache[key]=(chain,rows[-1][1])
                    chain,quote=cache[key];require(sha256(quote).hexdigest()==request['quote_hash'],'PULLBACK_QUOTE_CHANGED')
                    verify_chain(chain,record,quote,request['pullback'])
                    digest=sha256(chain).hexdigest();path='pullback-chain/'+digest+'.json'
                    if path not in files:
                        total+=len(chain);require(total<=MAX_EXPORT_BYTES,'PULLBACK_BATCH_BYTE_LIMIT');files[path]=chain;pins[path]=digest
                    paths[record]=dict(path=path,sha256=digest)
                except (ValueError,KeyError,TypeError,AttributeError,sqlite3.Error):
                    unavailable.append(dict(record_hash=record,reason='PULLBACK_PREFIX_UNVERIFIED'))
    except (OSError,ValueError,sqlite3.Error):
        unavailable.extend(dict(record_hash=record,reason='PULLBACK_DATABASE_UNAVAILABLE') for record in requests if record not in paths)
    return dict(files=files,source_hashes=pins,record_paths=paths,unavailable=unavailable,
        external_authentication=False,local_prefix_replayed=bool(paths),database_writes=False)

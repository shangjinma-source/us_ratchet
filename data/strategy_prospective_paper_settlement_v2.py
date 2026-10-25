"""Saved completed-session bytes to prospective paper settlement admission.

No fetching, ledger writes or implied vendor authentication. Capture adapters use
current_quantity_v2_completed_session_minutes.capture and BoundedLateUnitReview;
their original bytes must be retained and supplied here before admitting a hash.
"""
from copy import deepcopy
from hashlib import sha256
import json
from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v2 import require,stamp,sessions,SCOPE
from backtest.current_strategy_prospective_paper_book_v2 import replay,_context,SETTLEMENT_SCHEMA
from data.current_quantity_v2_completed_session_minutes import decode,request_url
from data.current_quantity_v2_late_unit_review import replay as replay_units
from data.strategy_account_mark_reference import decode_current_mark
from data.strategy_paper_execution_preview_v1 import _local_import_closure

CODE_PATHS=_local_import_closure({'data/strategy_prospective_paper_settlement_v2.py'})


def digest(value):return sha256(canonical(value)).hexdigest()


def _files(files,pins):
    require(type(files) is dict and type(pins) is dict and set(files)==set(pins)
            and 0<len(files)<=2000,'PROSPECTIVE_SETTLEMENT_SOURCE_DOMAIN')
    total=0
    for name,raw in files.items():
        require(type(name) is str and name and type(raw) is bytes and len(raw)<=4*1024*1024,
                'PROSPECTIVE_SETTLEMENT_SOURCE_BUDGET')
        total+=len(raw)
        require(total<=128*1024*1024 and sha256(raw).hexdigest()==pins[name],
                'PROSPECTIVE_SETTLEMENT_SOURCE_CHANGED')


def accepted_references(*,book,authority,admitted_decisions,files,source_hashes,now,admitted_settlements=None):
    """Derive immutable unit-review anchors from accepted decisions, not callers."""
    _files(files,source_hashes)
    app=_context(authority,now)
    require(CODE_PATHS<=set(app['code_sha256']),'PROSPECTIVE_SETTLEMENT_CODE_SCOPE')
    state=replay(book,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
    calendar={r['date']:r for r in sessions(authority['descriptor_arguments']['calendar_bytes'],app['calendar_sha256'])}
    result={}
    for oid,order in state['orders'].items():
        if order['closed'] is not None:continue
        decision=json.loads(admitted_decisions[order['decision_sha256']])
        sid=order['security_id'];limit=decision['limits'][sid];row=calendar[decision['session_date']]
        require(order['session_close']==row['close'] and limit['security_id']==sid,
                'PROSPECTIVE_SETTLEMENT_ORDER_IDENTITY')
        pins=limit['source_hashes']
        require(pins and all(source_hashes.get(p)==h for p,h in pins.items()),'PROSPECTIVE_SETTLEMENT_ORIGIN_CHANGED')
        # Halt and market captures both use *.receipt.json in production.
        # Select the unique market receipt by its bound structure, never by
        # excluding a particular halt-directory spelling.
        receipts=[]
        for p in pins:
            if not p.endswith('.receipt.json'):continue
            value=json.loads(files[p])
            if (type(value) is dict and value.get('security_id')==sid and
                    value.get('ticker')==limit['ticker'] and
                    type(value.get('captured_at')) is str and
                    value.get('raw_path') in pins and
                    value.get('raw_sha256')==pins[value['raw_path']]):
                receipts.append(p)
        require(len(receipts)==1,'PROSPECTIVE_SETTLEMENT_ORIGIN_RECEIPT')
        path=receipts[0];receipt=json.loads(files[path]);rawpath=receipt['raw_path']
        require(rawpath in pins and receipt['raw_sha256']==pins[rawpath] and
                receipt['security_id']==sid and receipt['ticker']==limit['ticker'],
                'PROSPECTIVE_SETTLEMENT_ORIGIN_RECEIPT')
        decoded=decode_current_mark(files[rawpath],ticker=limit['ticker'],captured_at=stamp(receipt['captured_at']),
                                    now=stamp(decision['available_at']))
        require(decoded['session']==row['date'] and decoded['last_at']==limit['observed_at'] and
                stamp(decoded['session_open'])==stamp(row['open']) and stamp(decoded['session_close'])==stamp(row['close']),
                'PROSPECTIVE_SETTLEMENT_ORIGIN_CALENDAR')
        result[oid]=dict(security_id=sid,ticker=limit['ticker'],price_basis=limit['price_basis'],
            captured_at=receipt['captured_at'],source_hashes={p:pins[p] for p in (path,rawpath)})
    require(result,'PROSPECTIVE_SETTLEMENT_NO_PENDING')
    return result


def produce_prospective_settlement(*,book,authority,admitted_decisions,captures,unit_reviews,
        files,source_hashes,clock,admitted_settlements=None):
    """Return bytes only after raw decode, bounded unit replay and final clock checks.

    captures[order_id] has raw/receipt/started/minutes logical file keys. An
    UNKNOWN decoder result is preserved; the book handles incomplete batches.
    """
    original=deepcopy((book,authority,admitted_decisions,captures,unit_reviews,files,source_hashes,admitted_settlements))
    state,auth,decisions,cap,units,blobs,pins,settlements=deepcopy(original)
    started=stamp(clock());app=_context(auth,started)
    verified=replay(state,authority=auth,admitted_decisions=decisions,admitted_settlements=settlements)
    require(started>=stamp(verified['last_available_at']),'PROSPECTIVE_SETTLEMENT_CLOCK')
    references=accepted_references(book=state,authority=auth,admitted_decisions=decisions,
        files=blobs,source_hashes=pins,now=started,admitted_settlements=settlements)
    require(set(cap)==set(units)==set(references),'PROSPECTIVE_SETTLEMENT_PENDING_DOMAIN')
    calendar={r['date']:r for r in sessions(auth['descriptor_arguments']['calendar_bytes'],app['calendar_sha256'])}
    minutes={};decoded_rows={};observed=[];available=[stamp(verified['last_available_at'])]
    for oid,ref in references.items():
        order=verified['orders'][oid];decision=json.loads(decisions[order['decision_sha256']]);row=calendar[decision['session_date']]
        paths=cap[oid]
        require(type(paths) is dict and set(paths)=={'raw','receipt','started','minutes'}
                and all(p in blobs for p in paths.values()),'PROSPECTIVE_SETTLEMENT_CAPTURE_PATHS')
        receipt=json.loads(blobs[paths['receipt']]);begin=json.loads(blobs[paths['started']]);raw=blobs[paths['raw']]
        identity=dict(security_id=ref['security_id'],ticker=ref['ticker'],session=row['date'],
                      session_open=row['open'],session_close=row['close'])
        for value in (receipt,begin):
            require(all(value[k]==v for k,v in identity.items()) and
                value['calendar_source_reference']=='sha256:'+app['calendar_sha256'] and
                value['request_url']==request_url(ref['ticker'],stamp(row['open']),stamp(row['close'])),
                'PROSPECTIVE_SETTLEMENT_CAPTURE_BINDING')
        require(receipt['started_at']==begin['started_at'] and
            stamp(row['close'])<=stamp(begin['started_at'])<=stamp(receipt['captured_at'])<=started and
            receipt['raw_sha256']==sha256(raw).hexdigest(),'PROSPECTIVE_SETTLEMENT_CAPTURE_TIME_OR_HASH')
        decoded=decode(raw,**identity,captured_at=receipt['captured_at'])
        decoded['source_reference']='sha256:'+receipt['raw_sha256']
        require(decoded==json.loads(blobs[paths['minutes']]) and receipt['status']==decoded['status'],
                'PROSPECTIVE_SETTLEMENT_DECODE_CHANGED')
        review=json.loads(blobs[units[oid]])
        replay_units(review,reference=ref,capture_raw_sha256=receipt['raw_sha256'],
                     captured_at=receipt['captured_at'],observed_at=started,read=blobs.__getitem__)
        minutes[oid]=decoded['minutes'];decoded_rows[oid]=dict(status=decoded['status'],missing_minute_starts=decoded['missing_minute_starts'])
        observed.append(stamp(receipt['captured_at']));available.append(stamp(review['reviewed_at']))
    _context(auth,started)
    require((book,authority,admitted_decisions,captures,unit_reviews,files,source_hashes,admitted_settlements)==original,
            'PROSPECTIVE_SETTLEMENT_INPUT_CHANGED')
    final=stamp(clock());require(final>=started and final>=max(available),'PROSPECTIVE_SETTLEMENT_CLOCK')
    review=dict(scope='PROSPECTIVE_PAPER_MINUTE_SOURCE_REVIEW_V1',source_sha256=pins,
        captures=cap,unit_reviews=units,decoded=decoded_rows,source_authenticated=False,coverage_complete=False,
        timestamp_basis='ACTUAL_LATER_CAPTURE_NOT_HISTORICAL_RECEIVED_TIME')
    review_raw=canonical(review)
    evidence=dict(schema=SETTLEMENT_SCHEMA,scope=SCOPE,status='VERIFIED_PROSPECTIVE_PAPER_SETTLEMENT_EVIDENCE',
        descriptor_sha256=verified['descriptor_sha256'],registration_sha256=verified['registration_sha256'],
        account_id=verified['account_id'],account_revision=verified['revision'],
        pending_orders_sha256=digest({oid:o for oid,o in verified['orders'].items() if o['closed'] is None}),
        observed_through=max(observed).isoformat(),available_at=final.isoformat(),minutes=minutes,
        source_review=dict(review,receipt_sha256=sha256(review_raw).hexdigest()))
    raw=canonical(evidence);tail=stamp(clock())
    require(tail>=final,'PROSPECTIVE_SETTLEMENT_CLOCK')
    require((book,authority,admitted_decisions,captures,unit_reviews,files,source_hashes,admitted_settlements)==original,
            'PROSPECTIVE_SETTLEMENT_INPUT_CHANGED')
    return dict(settlement_bytes=raw,settlement_sha256=sha256(raw).hexdigest(),review_bytes=review_raw,
                evidence=evidence,orders_created=False,account_mutated=False)
